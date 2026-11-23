import base64
import hashlib
import os
import secrets
import uuid
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from core.models import TimeStampedModel
from typing import Optional

def validate_profile_photo(file_obj):
    max_bytes = 2 * 1024 * 1024  # 2 MB limit
    if file_obj.size > max_bytes:
        raise ValidationError("Profile photo size must not exceed 2 MB.")
    ext = os.path.splitext(file_obj.name or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValidationError("Profile photo must be a JPG, PNG, or WebP image.")


def user_photo_upload_path(instance, filename):
    ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
    tenant_segment = str(instance.tenant_id) if instance.tenant_id else "platform"
    return f"tenants/{tenant_segment}/users/{instance.id}/profile_{uuid.uuid4().hex[:8]}{ext}"


class UserRole(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Platform Super Admin"
    HOSPITAL_OWNER = "HOSPITAL_OWNER", "Hospital Owner"
    HOSPITAL_ADMIN = "HOSPITAL_ADMIN", "Hospital Administrator"
    BRANCH_MANAGER = "BRANCH_MANAGER", "Branch Manager"
    DOCTOR = "DOCTOR", "Doctor"
    RECEPTIONIST = "RECEPTIONIST", "Receptionist"
    NURSE = "NURSE", "Nurse"
    PHARMACIST = "PHARMACIST", "Pharmacist"
    LAB_TECHNICIAN = "LAB_TECHNICIAN", "Lab Technician"
    LAB_MANAGER = "LAB_MANAGER", "Lab Manager"
    ACCOUNTANT = "ACCOUNTANT", "Accountant"
    HR_MANAGER = "HR_MANAGER", "HR Manager"
    INVENTORY_MANAGER = "INVENTORY_MANAGER", "Inventory Manager"
    PATIENT = "PATIENT", "Patient"


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    primary_branch_id = models.UUIDField(null=True, blank=True, db_index=True)
    role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.RECEPTIONIST, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, db_index=True)
    profile_photo = models.ImageField(
        upload_to=user_photo_upload_path,
        validators=[validate_profile_photo],
        null=True,
        blank=True,
    )
    two_factor_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, blank=True)
    totp_verified = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    @property
    def is_account_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def ensure_totp_secret(self) -> str:
        if not self.totp_secret:
            # Base32 secret compatible with standard TOTP authenticator apps
            raw = secrets.token_bytes(20)
            self.totp_secret = base64.b32encode(raw).decode("utf-8").rstrip("=")
            self.save(update_fields=["totp_secret"])
        return self.totp_secret


class UserDevice(TimeStampedModel):
    """
    Tracks browser/mobile devices for Facebook-style new-device login alerts & approvals.
    """
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    device_fingerprint = models.CharField(max_length=64, db_index=True)
    device_label = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_trusted = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "device_fingerprint")]

    @staticmethod
    def build_fingerprint(user_agent: str, ip_address: Optional[str] = None) -> str:
        seed = f"{(user_agent or '').strip()}|{(ip_address or '').strip()}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()


class WhatsAppOTPChallenge(TimeStampedModel):
    """
    Stores hashed 2FA/verification OTP challenges dispatched via WhatsApp provider
    (mock provider in development, WhatsApp Business API provider in production).
    """
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="whatsapp_otp_challenges")
    phone_number = models.CharField(max_length=20)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    provider_mode = models.CharField(max_length=24, default="mock")

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None