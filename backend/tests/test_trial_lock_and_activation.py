from __future__ import annotations
import base64
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import hmac
import json
import time
import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, UserRole
from core.audit import AuditLog
from licensing.models import InstallationLicense, LicenseStatus
from licensing.services import activate_signed_license, get_or_start_installation_license
from tenants.models import DeploymentPreset, ModuleCode
from tenants.services import is_module_enabled, provision_tenant


def make_signed_token(secret: str, payload: dict) -> str:
    json_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(json_bytes).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


@pytest.mark.django_db
def test_new_tenant_starts_7_day_trial_with_audit_log():
    tenant = provision_tenant(name="Apex Medical Center", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    lic = get_or_start_installation_license(tenant_id=tenant.id)

    assert lic.status == LicenseStatus.TRIAL
    assert lic.installation_id is not None
    assert lic.is_write_allowed is True
    # 7-day trial verification
    diff_days = (lic.trial_expires_at - lic.trial_started_at).days
    assert diff_days == 7

    # Audit log check
    audit = AuditLog.objects.filter(tenant_id=tenant.id, action="license.trial.started").first()
    assert audit is not None
    assert str(lic.installation_id) in audit.metadata.get("installation_id", "")


@pytest.mark.django_db
def test_expired_trial_enters_restricted_mode_and_blocks_operational_writes():
    tenant = provision_tenant(name="Global Health Clinic", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    owner = User.objects.create_user(
        username="global_owner",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.HOSPITAL_OWNER,
    )
    lic = get_or_start_installation_license(tenant_id=tenant.id)

    # Simulate 8 days have passed (past the 7-day trial)
    lic.trial_expires_at = timezone.now() - timedelta(days=1)
    lic.save(update_fields=["trial_expires_at"])

    # Re-evaluating license status triggers automatic restricted mode
    lic_refreshed = get_or_start_installation_license(tenant_id=tenant.id)
    assert lic_refreshed.status == LicenseStatus.RESTRICTED
    assert lic_refreshed.is_write_allowed is False

    client = Client()
    client.force_login(owner)

    # Safe read remains allowed for patient safety
    read_resp = client.get(reverse("api-tenants-branches"))
    assert read_resp.status_code == 200

    # Operational write is blocked with HTTP 403
    write_resp = client.post(
        reverse("api-tenants-branches"),
        {"name": "South Campus", "code": "SOUTH"},
        content_type="application/json",
    )
    assert write_resp.status_code == 403


@pytest.mark.django_db
def test_expired_trial_redirects_web_requests_to_licensing_status():
    tenant = provision_tenant(name="Care Clinic", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    owner = User.objects.create_user(
        username="care_owner",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.HOSPITAL_OWNER,
    )
    lic = get_or_start_installation_license(tenant_id=tenant.id)
    lic.status = LicenseStatus.RESTRICTED
    lic.save(update_fields=["status"])

    client = Client()
    client.force_login(owner)

    # Protected web route should redirect to licensing status
    web_resp = client.get(reverse("tenants-overview"))
    assert web_resp.status_code == 302
    assert "/licensing/status/" in web_resp.url


@pytest.mark.django_db
def test_clock_rollback_triggers_restricted_mode_and_audit_log():
    tenant = provision_tenant(name="Time Warp Hospital", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    lic = get_or_start_installation_license(tenant_id=tenant.id)

    # Simulate recorded monotonic time is in the future compared to system time
    future_epoch = int(time.time()) + 10000  # 10,000 seconds ahead
    lic.last_seen_monotonic_ts = future_epoch
    lic.save(update_fields=["last_seen_monotonic_ts"])

    # Backend check detects rollback (> 300s difference)
    lic_check = get_or_start_installation_license(tenant_id=tenant.id)
    assert lic_check.status == LicenseStatus.RESTRICTED

    audit = AuditLog.objects.filter(tenant_id=tenant.id, action="license.clock_rollback_detected").first()
    assert audit is not None


@pytest.mark.django_db
def test_1_year_signed_license_activation_via_api():
    tenant = provision_tenant(name="Metro Life Hospital", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    owner = User.objects.create_user(
        username="metro_admin",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.HOSPITAL_OWNER,
    )
    lic = get_or_start_installation_license(tenant_id=tenant.id)
    lic.status = LicenseStatus.RESTRICTED
    lic.save(update_fields=["status"])

    # Create signed 1-year token (365 days)
    now = datetime.now(dt_timezone.utc)
    expiry = now + timedelta(days=365)
    secret = "dev-secret-key"

    payload = {
        "client_name": "Metro Life Hospital",
        "tenant_id": str(tenant.id),
        "installation_id": str(lic.installation_id),
        "issued_at": now.isoformat(),
        "expires_at": expiry.isoformat(),
        "modules": [ModuleCode.CLINIC_OPD, ModuleCode.PHARMACY, ModuleCode.BILLING],
    }
    signed_token = make_signed_token(secret, payload)

    client = Client()
    client.force_login(owner)

    act_resp = client.post(
        reverse("api-licensing-activate"),
        {"signed_token": signed_token},
        content_type="application/json",
    )
    assert act_resp.status_code == 200

    lic.refresh_from_db()
    assert lic.status == LicenseStatus.ACTIVE
    assert lic.is_write_allowed is True
    assert lic.license_expires_at is not None

    # Verify audit log was recorded
    audit = AuditLog.objects.filter(tenant_id=tenant.id, action="license.activated").first()
    assert audit is not None


@pytest.mark.django_db
def test_invalid_installation_binding_is_rejected():
    tenant = provision_tenant(name="Bound Hospital", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    lic = get_or_start_installation_license(tenant_id=tenant.id)

    # Token signed with a DIFFERENT installation ID
    payload = {
        "tenant_id": str(tenant.id),
        "installation_id": "00000000-0000-0000-0000-000000000000",
        "expires_at": (timezone.now() + timedelta(days=365)).isoformat(),
        "modules": [ModuleCode.CLINIC_OPD],
    }
    signed_token = make_signed_token("dev-secret-key", payload)

    ok, msg, _ = activate_signed_license(tenant_id=tenant.id, signed_token=signed_token)
    assert ok is False
    assert "installation ID" in msg
