from datetime import timedelta
from decimal import Decimal
import importlib
import os
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from accounts.models import User, UserRole
from clinic.models import OPDEncounter, Prescription, PrescriptionItem
from clinic.services import register_patient
from core.linked_workflows import (
    create_invoice_from_ipd_admission,
    create_invoice_from_lab_order,
    dispense_prescription_to_pharmacy_sale,
    summarize_gst_breakup,
)
from ipd.services import admit_patient_to_bed, create_ward_with_beds, discharge_ipd_patient
from laboratory.services import create_lab_order, create_lab_test
from pharmacy.services import add_medicine_and_batch
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_linked_opd_lab_ipd_to_pharmacy_and_billing_and_gst_summary():
    tenant = provision_tenant(name="Integrated Care Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    doc = User.objects.create_user(
        username="dr_int",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.DOCTOR,
    )
    patient, _ = register_patient(tenant_id=tenant.id, full_name="Rohan Kulkarni", phone_number="+919866666666")

    # 1. Pharmacy stock + OPD Prescription -> FEFO PharmacySale
    med, batch = add_medicine_and_batch(
        tenant_id=tenant.id,
        brand_name="Dolo 650",
        salt_composition="Paracetamol 650mg",
        batch_number="DL-01",
        expiry_date=timezone.localdate() + timedelta(days=180),
        quantity=30,
        unit_price=Decimal("20.00"),
        gst_rate_percent=Decimal("12.00"),
    )
    encounter = OPDEncounter.objects.create(
        tenant_id=tenant.id,
        patient=patient,
        doctor=doc,
        chief_complaint="Fever",
        diagnosis="Viral Pyrexia",
    )
    rx = Prescription.objects.create(
    tenant_id=tenant.id,
    encounter=encounter,
    patient=patient,
    prescribed_by=doc,
    )

    PrescriptionItem.objects.create(
    prescription=rx,
    medicine_name="Dolo 650",
    dosage="1 tab",
    frequency="BD",
    )
    sale = dispense_prescription_to_pharmacy_sale(
        tenant_id=tenant.id,
        prescription_id=rx.id,
        default_quantity=5,
        actor=doc,
    )
    batch.refresh_from_db()
    assert batch.quantity_on_hand == 25
    assert sale.subtotal_amount == Decimal("100.00")
    assert sale.gst_amount == Decimal("12.00")

    # 2. Lab Order -> Billing Invoice
    test = create_lab_test(
        tenant_id=tenant.id,
        code="LFT",
        name="Liver Function Test",
        price=Decimal("800.00"),
        gst_rate_percent=Decimal("0.00"),
    )
    lab_order = create_lab_order(tenant_id=tenant.id, patient=patient, test_ids=[str(test.id)], actor=doc)
    lab_inv = create_invoice_from_lab_order(tenant_id=tenant.id, lab_order_id=lab_order.id, actor=doc)
    assert lab_inv.total_amount == Decimal("800.00")

    # 3. Discharged IPD Admission -> Billing Invoice
    _, beds = create_ward_with_beds(
        tenant_id=tenant.id,
        code="PVT",
        name="Private Room",
        daily_charge=Decimal("2000.00"),
        bed_count=1,
    )
    adm = admit_patient_to_bed(
        tenant_id=tenant.id,
        patient=patient,
        bed_id=beds[0].id,
        admission_reason="Observation",
        actor=doc,
    )
    discharged = discharge_ipd_patient(
        tenant_id=tenant.id,
        admission_id=adm.id,
        discharged_at=adm.admitted_at + timedelta(hours=12),
        actor=doc,
    )
    ipd_inv = create_invoice_from_ipd_admission(tenant_id=tenant.id, admission_id=discharged.id, actor=doc)
    assert ipd_inv.total_amount == Decimal("2000.00")

    # 4. Indian GST CGST/SGST Summary
    gst = summarize_gst_breakup(tenant_id=tenant.id)
    assert gst["total_taxable_value"] == Decimal("2900.00")
    assert gst["total_gst"] == Decimal("12.00")
    assert gst["cgst_amount"] == Decimal("6.00")
    assert gst["sgst_amount"] == Decimal("6.00")


def test_prod_settings_requires_secrets(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("LICENSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    with pytest.raises(ImproperlyConfigured):
        import config.settings.prod as prod_mod
        importlib.reload(prod_mod)