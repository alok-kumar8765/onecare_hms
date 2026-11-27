import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User, UserRole
from clinic.models import OPDEncounter, Prescription
from clinic.services import register_patient
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_cross_tenant_prescription_access_isolated():
    tenant_a = provision_tenant(name="Hospital Alpha", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    tenant_b = provision_tenant(name="Hospital Beta", deployment_preset=DeploymentPreset.FULL_HOSPITAL)

    doctor_a = User.objects.create_user(
        username="dr_alpha",
        password="StrongPassword123!",
        tenant_id=tenant_a.id,
        role=UserRole.DOCTOR,
    )
    admin_b = User.objects.create_user(
        username="admin_beta",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.HOSPITAL_ADMIN,
    )

    patient_a, _ = register_patient(
        tenant_id=tenant_a.id,
        full_name="Aarav Verma",
        phone_number="+919811111111",
    )
    encounter_a = OPDEncounter.objects.create(
        tenant_id=tenant_a.id,
        patient=patient_a,
        doctor=doctor_a,
        chief_complaint="Fever",
    )
    rx_a = Prescription.objects.create(
        tenant_id=tenant_a.id,
        encounter=encounter_a,
        patient=patient_a,
        prescribed_by=doctor_a,
        advice="Hydrate",
    )

    client_b = Client()
    client_b.force_login(admin_b)

    resp = client_b.get(reverse("clinic-prescription-print", args=[rx_a.id]))
    assert resp.status_code in (400, 403, 404)