import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserRole
from tenants.models import DeploymentPreset, ModuleCode, Tenant


@pytest.mark.django_db
def test_setup_wizard_creates_tenant_branch_staff_and_export_csv():
    super_admin = User.objects.create_user(
        username="owner_root",
        password="StrongPassword123!",
        role=UserRole.SUPER_ADMIN,
        is_superuser=True,
        is_staff=True,
    )
    client = Client()
    client.force_login(super_admin)

    resp = client.post(
        reverse("tenants-setup-wizard"),
        {
            "action": "create_tenant",
            "name": "Apex Care Group",
            "deployment_preset": DeploymentPreset.FULL_HOSPITAL,
        },
    )
    assert resp.status_code == 200
    tenant = Tenant.objects.get(name="Apex Care Group")

    branch_resp = client.post(
        reverse("tenants-setup-wizard"),
        {
            "action": "add_branch",
            "tenant_id": str(tenant.id),
            "branch_name": "North Wing",
            "branch_code": "NORTH",
            "address": "Main Road",
        },
    )
    assert branch_resp.status_code == 200
    assert tenant.branches.filter(code="NORTH").exists()

    staff_resp = client.post(
        reverse("tenants-setup-wizard"),
        {
            "action": "create_staff",
            "tenant_id": str(tenant.id),
            "username": "dr_apex",
            "password": "StrongPassword123!",
            "role": UserRole.DOCTOR,
        },
    )
    assert staff_resp.status_code == 200
    assert User.objects.filter(username="dr_apex", tenant_id=tenant.id).exists()

    mod_resp = client.post(
        reverse("tenants-setup-wizard"),
        {
            "action": "set_module",
            "tenant_id": str(tenant.id),
            "module_code": ModuleCode.PHARMACY,
            "is_enabled": "true",
        },
    )
    assert mod_resp.status_code == 200

    csv_resp = client.get(reverse("tenants-reports") + "?export=summary_csv")
    assert csv_resp.status_code == 200
    assert "Patients Registered" in csv_resp.content.decode("utf-8")