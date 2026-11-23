from __future__ import annotations
from datetime import datetime, timedelta
import time
from typing import Optional, Tuple
from django.conf import settings
from django.utils import timezone
from core.audit import record_audit_log
from tenants.models import ModuleCode, ModuleEntitlement
from .models import InstallationLicense, LicenseStatus
from .providers import get_licensing_provider


def get_or_start_installation_license(*, tenant_id=None, request=None) -> InstallationLicense:
    """
    Retrieves or initializes the 7-day trial installation license for a tenant.
    Enforces server-side clock rollback checks and automatic trial/license expiration.
    """
    now = timezone.now()
    now_epoch = int(time.time())
    provider_mode = getattr(settings, "LICENSE_PROVIDER", "development")

    lic = InstallationLicense.objects.filter(tenant_id=tenant_id).first()
    if lic is None:
        lic = InstallationLicense.objects.create(
            tenant_id=tenant_id,
            provider_mode=provider_mode,
            status=LicenseStatus.TRIAL,
            trial_started_at=now,
            trial_expires_at=now + timedelta(days=7),
            last_verified_at=now,
            last_seen_monotonic_ts=now_epoch,
        )
        record_audit_log(
            action="license.trial.started",
            resource_type="InstallationLicense",
            resource_id=lic.id,
            tenant_id=tenant_id,
            request=request,
            metadata={
                "installation_id": str(lic.installation_id),
                "provider_mode": provider_mode,
                "trial_days": 7,
                "trial_expires_at": lic.trial_expires_at.isoformat(),
            },
        )
        return lic

    # Server-side clock rollback detection: system clock wound back by > 5 minutes (300s)
    if now_epoch + 300 < lic.last_seen_monotonic_ts:
        if lic.status != LicenseStatus.RESTRICTED:
            lic.status = LicenseStatus.RESTRICTED
            lic.save(update_fields=["status", "updated_at"])
            record_audit_log(
                action="license.clock_rollback_detected",
                resource_type="InstallationLicense",
                resource_id=lic.id,
                tenant_id=tenant_id,
                request=request,
                metadata={"now_epoch": now_epoch, "last_seen_monotonic_ts": lic.last_seen_monotonic_ts},
            )
        return lic

    # Update monotonic timestamp if moving forward
    lic.last_seen_monotonic_ts = max(lic.last_seen_monotonic_ts, now_epoch)

    # Check 7-day trial / 1-year license expiry
    expiry = lic.license_expires_at if lic.status == LicenseStatus.ACTIVE else lic.trial_expires_at
    if expiry and now >= expiry and lic.status != LicenseStatus.RESTRICTED:
        lic.status = LicenseStatus.RESTRICTED
        record_audit_log(
            action="license.restricted_mode.entered",
            resource_type="InstallationLicense",
            resource_id=lic.id,
            tenant_id=tenant_id,
            request=request,
            metadata={"reason": "trial_or_license_expired", "expired_at": expiry.isoformat()},
        )

    lic.save(update_fields=["status", "last_seen_monotonic_ts", "updated_at"])
    return lic


def activate_signed_license(*, tenant_id, signed_token: str, actor=None, request=None) -> Tuple[bool, str, Optional[InstallationLicense]]:
    """
    Activates a cryptographically signed license key (typically 1 year / 365 days).
    Validates signature, tenant/installation binding, and expiration date.
    Unlocks operational features and updates module entitlements upon successful validation.
    """
    lic = get_or_start_installation_license(tenant_id=tenant_id, request=request)
    provider = get_licensing_provider()
    payload = provider.verify_signed_token(signed_token)
    if not payload:
        record_audit_log(
            action="license.activation.failed",
            resource_type="InstallationLicense",
            resource_id=lic.id,
            actor=actor,
            tenant_id=tenant_id,
            request=request,
            metadata={"reason": "invalid_or_tampered_signature"},
        )
        return False, "Invalid or tampered license token signature.", lic

    # Binding check: tenant_id
    token_tenant = payload.get("tenant_id")
    if token_tenant and str(token_tenant) != str(tenant_id):
        return False, "License token belongs to a different tenant.", lic

    # Binding check: installation_id
    token_installation = payload.get("installation_id")
    if token_installation and str(token_installation) != str(lic.installation_id):
        return False, "License token belongs to a different installation ID.", lic

    expires_raw = payload.get("expires_at")
    if not expires_raw:
        return False, "License token missing expiry timestamp.", lic

    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (ValueError, TypeError):
        return False, "Invalid expiry date format in license token.", lic

    if timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())

    if expires_at <= timezone.now():
        return False, "License token is already expired.", lic

    modules = payload.get("modules") or []
    lic.status = LicenseStatus.ACTIVE
    lic.license_expires_at = expires_at
    lic.last_verified_at = timezone.now()
    lic.signed_token = signed_token
    lic.licensed_modules = modules
    lic.save()

    if modules:
        for code in ModuleCode.values:
            ModuleEntitlement.objects.update_or_create(
                tenant_id=tenant_id,
                module_code=code,
                defaults={"is_enabled": code in modules},
            )

    record_audit_log(
        action="license.activated",
        resource_type="InstallationLicense",
        resource_id=lic.id,
        actor=actor,
        tenant_id=tenant_id,
        request=request,
        metadata={
            "expires_at": expires_at.isoformat(),
            "modules": modules,
            "installation_id": str(lic.installation_id),
        },
    )
    return True, "License activated successfully.", lic
