from datetime import date, timedelta
import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserRole
from clinic.services import (
    create_opd_encounter_with_prescription,
    filter_encounters_queryset,
    register_patient,
)
from tenants.models import DeploymentPreset, ModuleCode
from tenants.services import provision_tenant, set_tenant_module_state


@pytest.mark.django_db
def test_duplicate_patient_detection_and_cross_tenant_isolation():
    tenant_a = provision_tenant(name="Apollo Clinic A", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    tenant_b = provision_tenant(name="Fortis Clinic B", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)

    p_a, _ = register_patient(
        tenant_id=tenant_a.id,
        full_name="Ramesh Verma",
        phone_number="+919811111111",
    )

    with pytest.raises(ValueError):
        register_patient(
            tenant_id=tenant_a.id,
            full_name="Ramesh Verma",
            phone_number="+919811111111",
        )

    staff_b = User.objects.create_user(
        username="staff_b",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.RECEPTIONIST,
    )
    client = Client()
    client.force_login(staff_b)

    resp = client.get(reverse("api-clinic-patients"))
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert str(p_a.id) not in ids


@pytest.mark.django_db
def test_period_filter_and_module_entitlement_guard():
    tenant = provision_tenant(name="City Care", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    doc = User.objects.create_user(
        username="dr_mehta",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.DOCTOR,
    )
    patient, _ = register_patient(tenant_id=tenant.id, full_name="Suman Rao", phone_number="+919822222222")
    enc, _ = create_opd_encounter_with_prescription(
        tenant_id=tenant.id,
        patient=patient,
        doctor=doc,
        chief_complaint="Fever and cough",
        diagnosis="Viral URI",
        items=[{"medicine_name": "Paracetamol 500mg", "dosage": "1 tab", "frequency": "SOS", "duration": "3 days"}],
    )
    enc.encounter_date = date.today() - timedelta(days=400)
    enc.save(update_fields=["encounter_date"])

    prev_year_qs = filter_encounters_queryset(tenant_id=tenant.id, period="previous_year", doctor_id=str(doc.id))
    assert prev_year_qs.filter(id=enc.id).exists()

    # Disable CLINIC_OPD and verify API returns 403
    set_tenant_module_state(tenant_id=tenant.id, module_code=ModuleCode.CLINIC_OPD, is_enabled=False)
    client = Client()
    client.force_login(doc)
    blocked = client.get(reverse("api-clinic-patients"))
    assert blocked.status_code == 403