from datetime import timedelta
from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, UserRole
from clinic.services import register_patient
from ipd.models import AdmissionStatus, BedStatus, WardType
from ipd.services import (
    add_ipd_billing_item,
    admit_patient_to_bed,
    create_ward_with_beds,
    discharge_ipd_patient,
)
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_ipd_bed_locking_and_discharge_billing():
    tenant = provision_tenant(name="City General Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    ward, beds = create_ward_with_beds(
        tenant_id=tenant.id,
        code="GEN",
        name="General Ward",
        ward_type=WardType.GENERAL,
        daily_charge=Decimal("1000.00"),
        bed_count=1,
    )
    bed = beds[0]

    p1, _ = register_patient(tenant_id=tenant.id, full_name="Suresh Patel", phone_number="+919844444444")
    p2, _ = register_patient(tenant_id=tenant.id, full_name="Anita Desai", phone_number="+919855555555")

    adm1 = admit_patient_to_bed(
        tenant_id=tenant.id,
        patient=p1,
        bed_id=bed.id,
        admission_reason="Acute fever observation",
    )
    bed.refresh_from_db()
    assert bed.status == BedStatus.OCCUPIED

    # Second patient cannot take an already occupied bed
    with pytest.raises(ValueError):
        admit_patient_to_bed(
            tenant_id=tenant.id,
            patient=p2,
            bed_id=bed.id,
            admission_reason="Observation",
        )

    add_ipd_billing_item(
        tenant_id=tenant.id,
        admission_id=adm1.id,
        description="Nursing & IV procedure",
        quantity=1,
        unit_rate=Decimal("500.00"),
    )
    discharged = discharge_ipd_patient(
        tenant_id=tenant.id,
        admission_id=adm1.id,
        discharge_summary="Recovered and stable",
        discharged_at=adm1.admitted_at + timedelta(days=2),
    )
    bed.refresh_from_db()
    assert discharged.status == AdmissionStatus.DISCHARGED
    assert discharged.total_amount == Decimal("2500.00")
    assert bed.status == BedStatus.AVAILABLE


@pytest.mark.django_db
def test_ipd_cross_tenant_isolation():
    tenant_a = provision_tenant(name="Hospital A", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    tenant_b = provision_tenant(name="Hospital B", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    create_ward_with_beds(tenant_id=tenant_a.id, code="W-A", name="Ward A", bed_count=2)

    nurse_b = User.objects.create_user(
        username="nurse_b",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.NURSE,
    )
    client = Client()
    client.force_login(nurse_b)
    resp = client.get(reverse("api-ipd-beds"))
    assert resp.status_code == 200
    assert resp.json() == []