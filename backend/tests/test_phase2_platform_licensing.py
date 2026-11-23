import base64
from datetime import timedelta
import json
import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, UserRole
from licensing.models import LicenseStatus
from licensing.services import get_or_start_installation_license
from tenants.models import DeploymentPreset, ModuleCode
from tenants.services import is_module_enabled, provision_tenant


@pytest.mark.django_db
def test_super_admin_module_activation_without_reinstall():
    super_admin = User.objects.create_user(
        username="platform_root",
        password="StrongPassword123!",
        role=UserRole.SUPER_ADMIN,
    )
    tenant = provision_tenant(name="Sunrise Clinic", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    assert is_module_enabled(tenant.id, ModuleCode.PHARMACY) is False

    client = Client()
    client.force_login(super_admin)
    url = reverse("api-platform-tenant-modules", kwargs={"tenant_id": tenant.id})
    resp = client.post(url, {"module_code": ModuleCode.PHARMACY, "is_enabled": True}, content_type="application/json")
    assert resp.status_code == 200
    assert is_module_enabled(tenant.id, ModuleCode.PHARMACY) is True


@pytest.mark.django_db
def test_restricted_mode_blocks_writes_but_allows_reads_and_renewal():
    tenant = provision_tenant(name="Metro Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    owner = User.objects.create_user(
        username="metro_owner",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.HOSPITAL_OWNER,
    )
    lic = get_or_start_installation_license(tenant_id=tenant.id)
    lic.status = LicenseStatus.RESTRICTED
    lic.save(update_fields=["status"])

    client = Client()
    client.force_login(owner)

    # Read remains allowed in Patient-Data-Safe Restricted Mode
    read_resp = client.get(reverse("api-tenants-branches"))
    assert read_resp.status_code == 200

    # Operational write is blocked until renewal
    write_resp = client.post(
        reverse("api-tenants-branches"),
        {"name": "North Wing", "code": "NORTH"},
        content_type="application/json",
    )
    assert write_resp.status_code == 403

    # Renewal via signed token restores write access
    payload = {
        "tenant_id": str(tenant.id),
        "expires_at": (timezone.now() + timedelta(days=365)).isoformat(),
        "modules": [ModuleCode.CLINIC_OPD, ModuleCode.BILLING],
    }
    dev_token = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    act_resp = client.post(
        reverse("api-licensing-activate"),
        {"signed_token": dev_token},
        content_type="application/json",
    )
    assert act_resp.status_code == 200

    write_after = client.post(
        reverse("api-tenants-branches"),
        {"name": "North Wing", "code": "NORTH"},
        content_type="application/json",
    )
    assert write_after.status_code == 201