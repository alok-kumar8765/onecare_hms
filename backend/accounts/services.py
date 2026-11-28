import base64
from typing import Optional, Union
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from core.audit import record_audit_log
from .models import User, UserDevice, WhatsAppOTPChallenge


def _generate_totp_code(secret_b32: str, for_time: Optional[float] = None, step: int = 30, digits: int = 6) -> str:
    padded = secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int((for_time if for_time is not None else time.time()) // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** digits)).zfill(digits)


def verify_totp_code(secret_b32: str, code: str, window: int = 1) -> bool:
    if not secret_b32 or not code or not code.strip().isdigit():
        return False
    cleaned = code.strip()
    now_ts = time.time()
    for offset in range(-window, window + 1):
        candidate = _generate_totp_code(secret_b32, for_time=now_ts + (offset * 30))
        if hmac.compare_digest(candidate, cleaned):
            return True
    return False


def _hash_otp(code: str) -> str:
    salted = f"{settings.SECRET_KEY}:{code.strip()}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def issue_whatsapp_otp(user: User, request=None, provider_mode: str = "mock") -> tuple[WhatsAppOTPChallenge, str]:
    """
    Creates a short-lived 6-digit OTP challenge for WhatsApp 2FA.
    Returns (challenge, plain_otp) so a mock/dev provider or test can inspect it
    without persisting plaintext OTPs in the database.
    """
    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = WhatsAppOTPChallenge.objects.create(
        tenant_id=user.tenant_id,
        user=user,
        phone_number=user.phone_number,
        code_hash=_hash_otp(otp_code),
        expires_at=timezone.now() + timedelta(minutes=5),
        provider_mode=provider_mode,
    )
    record_audit_log(
        action="auth.whatsapp_otp.issued",
        resource_type="User",
        resource_id=user.id,
        actor=user,
        tenant_id=user.tenant_id,
        request=request,
        metadata={"challenge_id": str(challenge.id), "provider_mode": provider_mode},
    )
    return challenge, otp_code


# def verify_whatsapp_otp(challenge: WhatsAppOTPChallenge, code: str, request=None) -> bool:
#     if challenge.is_consumed or challenge.is_expired or challenge.attempts >= 5:
#         return False
#     challenge.attempts += 1
#     if hmac.compare_digest(challenge.code_hash, _hash_otp(code or "")):
#         challenge.consumed_at = timezone.now()
#         challenge.save(update_fields=["attempts", "consumed_at", "updated_at"])
#         record_audit_log(
#             action="auth.whatsapp_otp.verified",
#             resource_type="User",
#             resource_id=challenge.user_id,
#             actor=challenge.user,
#             tenant_id=challenge.tenant_id,
#             request=request,
#             metadata={"challenge_id": str(challenge.id)},
#         )
#         return True
#     challenge.save(update_fields=["attempts", "updated_at"])
#     return False


@transaction.atomic
def verify_whatsapp_otp(challenge: WhatsAppOTPChallenge, code: str, request=None,) -> bool:
    """
    Verifies OTP atomically.
    Prevents concurrent requests from consuming the same challenge.
    """
    locked_challenge = (WhatsAppOTPChallenge.objects.select_for_update().filter(pk=challenge.pk).select_related("user").first())

    if not locked_challenge:
        return False

    if (locked_challenge.is_consumed or locked_challenge.is_expired or locked_challenge.attempts >= 5):
        return False

    locked_challenge.attempts += 1

    valid_code = (isinstance(code, str) and len(code.strip()) == 6 and code.strip().isdigit())

    if valid_code and hmac.compare_digest(locked_challenge.code_hash, _hash_otp(code),):
        locked_challenge.consumed_at = timezone.now()
        locked_challenge.save(update_fields=["attempts", "consumed_at", "updated_at"])

        record_audit_log(action="auth.whatsapp_otp.verified", resource_type="User", resource_id=locked_challenge.user_id, actor=locked_challenge.user, tenant_id=locked_challenge.tenant_id, request=request, metadata={"challenge_id": str(locked_challenge.id)},)
        return True

    locked_challenge.save(update_fields=["attempts", "updated_at"])
    return False


@transaction.atomic
def evaluate_login_attempt(*, username: str, password: str, user_agent: str = "", ip_address: Optional[str] = None, request=None) -> dict:
    """
    Evaluates credentials, enforces account lockout on repeated failures,
    detects new/untrusted devices (Facebook-style login alert), and checks 2FA requirement.
    """
    user = User.objects.select_for_update().filter(username=username).first()
    if user and user.is_account_locked:
        record_audit_log(
            action="auth.login.locked",
            resource_type="User",
            resource_id=user.id,
            actor=user,
            tenant_id=user.tenant_id,
            request=request,
            metadata={"ip_address": ip_address},
        )
        return {"ok": False, "status": "locked", "message": "Account temporarily locked due to repeated failed login attempts."}

    authenticated_user = authenticate(request=request, username=username, password=password)
    if authenticated_user is None:
        if user:
            user.failed_login_attempts += 1
            max_attempts = getattr(settings, "MAX_FAILED_LOGIN_ATTEMPTS", 5)
            lockout_mins = getattr(settings, "LOGIN_LOCKOUT_MINUTES", 15)
            if user.failed_login_attempts >= max_attempts:
                user.locked_until = timezone.now() + timedelta(minutes=lockout_mins)
                user.failed_login_attempts = 0
                user.save(update_fields=["failed_login_attempts", "locked_until"])
            else:
                user.save(update_fields=["failed_login_attempts"])

            record_audit_log(
                action="auth.login.failed",
                resource_type="User",
                resource_id=user.id,
                actor=user,
                tenant_id=user.tenant_id,
                request=request,
                metadata={"ip_address": ip_address},
            )
        return {"ok": False, "status": "invalid_credentials", "message": "Invalid username or password."}

    authenticated_user.failed_login_attempts = 0
    authenticated_user.locked_until = None
    authenticated_user.save(update_fields=["failed_login_attempts", "locked_until"])

    fp = UserDevice.build_fingerprint(user_agent=user_agent, ip_address=ip_address)
    device, created = UserDevice.objects.get_or_create(
        user=authenticated_user,
        device_fingerprint=fp,
        defaults={
            "tenant_id": authenticated_user.tenant_id,
            "device_label": (user_agent or "Unknown Device")[:200],
            "ip_address": ip_address,
            "is_trusted": False,
        },
    )
    if not created:
        device.ip_address = ip_address
        device.save(update_fields=["ip_address", "last_seen_at"])

    new_device_alert = created or not device.is_trusted
    if new_device_alert:
        record_audit_log(
            action="auth.login.new_device_alert",
            resource_type="UserDevice",
            resource_id=device.id,
            actor=authenticated_user,
            tenant_id=authenticated_user.tenant_id,
            request=request,
            metadata={"device_label": device.device_label, "ip_address": ip_address, "is_new": created},
        )

    requires_2fa = bool(authenticated_user.two_factor_enabled and authenticated_user.totp_verified)
    record_audit_log(
        action="auth.login.credentials_ok",
        resource_type="User",
        resource_id=authenticated_user.id,
        actor=authenticated_user,
        tenant_id=authenticated_user.tenant_id,
        request=request,
        metadata={"requires_2fa": requires_2fa, "new_device_alert": new_device_alert},
    )

    return {
        "ok": True,
        "status": "2fa_required" if requires_2fa else "authenticated",
        "user": authenticated_user,
        "device": device,
        "new_device_alert": new_device_alert,
        "requires_2fa": requires_2fa,
    }


def approve_user_device(*, user: User, device_id, request=None) -> Optional[UserDevice]:
    device = UserDevice.objects.filter(id=device_id, user=user, tenant_id=user.tenant_id,).first()
    if not device:
        return None
    device.is_trusted = True
    device.approved_at = timezone.now()
    device.save(update_fields=["is_trusted", "approved_at", "last_seen_at"])
    record_audit_log(
        action="auth.device.approved",
        resource_type="UserDevice",
        resource_id=device.id,
        actor=user,
        tenant_id=user.tenant_id,
        request=request,
        metadata={"device_label": device.device_label},
    )
    return device