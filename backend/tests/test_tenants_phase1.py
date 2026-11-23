import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserRole
from tenants.models import DeploymentPreset, ModuleCode
from tenants.services import is_module_enabled, provision_tenant


@pytest.mark.django_db
def test_tenant_provisioning_and_module_entitlements():
    clinic = provision_tenant(
        name="CarePlus Clinic",
        deployment_preset=DeploymentPreset.STANDALONE_CLINIC,
    )
    assert clinic.branches.filter(is_main=True).count() == 1
    assert is_module_enabled(clinic.id, ModuleCode.CLINIC_OPD) is True
    assert is_module_enabled(clinic.id, ModuleCode.PHARMACY) is False
    assert is_module_enabled(clinic.id, ModuleCode.LABORATORY) is False


@pytest.mark.django_db
def test_current_tenant_api_scopes_to_authenticated_user_tenant():
    tenant_a = provision_tenant(name="Alpha Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    tenant_b = provision_tenant(name="Beta Clinic", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)

    user_a = User.objects.create_user(
        username="admin_a",
        password="StrongPassword123!",
        tenant_id=tenant_a.id,
        role=UserRole.HOSPITAL_ADMIN,
    )
    assert tenant_b.id != tenant_a.id

    client = Client()
    client.force_login(user_a)
    resp = client.get(reverse("api-tenants-current"))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(tenant_a.id)
    assert resp.json()["name"] == "Alpha Hospital"