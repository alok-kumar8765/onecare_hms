from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User, UserRole
from billing.models import Invoice, InvoiceLineItem
from billing.services import build_gst_return_summary, create_invoice_with_items
from clinic.models import OPDEncounter, Patient, Prescription
from clinic.services import register_patient
from laboratory.models import LabOrder, LabTest
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_gst_return_summary_and_csv_export():
    tenant = provision_tenant(name="GST Care Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    acct = User.objects.create_user(
        username="gst_acct",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.ACCOUNTANT,
    )
    patient, _ = register_patient(
        tenant_id=tenant.id,
        full_name="Ananya Sharma",
        phone_number="+919811111111",
    )

    inv = create_invoice_with_items(
        tenant_id=tenant.id,
        patient=patient,
        customer_name=patient.full_name,
        items=[
            {
                "description": "Diagnostics Panel",
                "hsn_sac_code": "999312",
                "quantity": 1,
                "unit_price": Decimal("1000.00"),
                "gst_rate_percent": Decimal("18.00"),
            }
        ],
        actor=acct,
    )
    assert inv is not None

    summary = build_gst_return_summary(tenant_id=tenant.id)
    assert len(summary["gstr_3b_by_rate"]) == 1
    assert summary["gstr_3b_by_rate"][0]["cgst"] == Decimal("90.00")
    assert summary["gstr_3b_by_rate"][0]["sgst"] == Decimal("90.00")
    assert summary["gstr_1_hsn_summary"][0]["hsn_sac_code"] == "999312"

    client = Client()
    client.force_login(acct)
    csv_resp = client.get(reverse("billing-dashboard") + "?export=gst_return_csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp["Content-Type"]
    body = csv_resp.content.decode("utf-8")
    assert "999312" in body
    assert "18.00%" in body


@pytest.mark.django_db
def test_print_views_and_lab_verification_gate():
    tenant_a = provision_tenant(name="Print Hospital A", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    tenant_b = provision_tenant(name="Print Hospital B", deployment_preset=DeploymentPreset.FULL_HOSPITAL)

    staff_a = User.objects.create_user(
        username="staff_a",
        password="StrongPassword123!",
        tenant_id=tenant_a.id,
        role=UserRole.DOCTOR,
    )
    staff_b = User.objects.create_user(
        username="staff_b",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.DOCTOR,
    )
    patient_a, _ = register_patient(
        tenant_id=tenant_a.id,
        full_name="Vikram Rao",
        phone_number="+919822222222",
    )

    invoice_a = Invoice.objects.create(
        tenant_id=tenant_a.id,
        patient=patient_a,
        customer_name=patient_a.full_name,
        invoice_number="INV-PRINT-001",
        subtotal_amount=Decimal("500.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
    )
    InvoiceLineItem.objects.create(
        invoice=invoice_a,
        description="Consultation",
        hsn_sac_code="999311",
        quantity=1,
        unit_price=Decimal("500.00"),
        line_total=Decimal("500.00"),
    )

    encounter_a = OPDEncounter.objects.create(
        tenant_id=tenant_a.id,
        patient=patient_a,
        doctor=staff_a,
        chief_complaint="Cough",
    )
    rx_a = Prescription.objects.create(
        tenant_id=tenant_a.id,
        encounter=encounter_a,
        patient=patient_a,
        prescribed_by=staff_a,
        advice="Warm fluids",
    )

    lab_test = LabTest.objects.create(
        tenant_id=tenant_a.id,
        name="CBC",
        price=Decimal("300.00"),
    )
    unverified_order = LabOrder.objects.create(
        tenant_id=tenant_a.id,
        patient=patient_a,
        order_number="LAB-UNVERIFIED-1",
        status="PENDING",
    )
    _ = lab_test

    client_a = Client()
    client_a.force_login(staff_a)

    inv_resp = client_a.get(reverse("billing-invoice-print", args=[invoice_a.id]) + "?format=json")
    assert inv_resp.status_code == 200
    assert inv_resp.json()["invoice_number"] == "INV-PRINT-001"

    rx_resp = client_a.get(reverse("clinic-prescription-print", args=[rx_a.id]) + "?format=json")
    assert rx_resp.status_code == 200
    assert rx_resp.json()["patient_name"] == "Vikram Rao"

    blocked_lab_resp = client_a.get(reverse("laboratory-report-print", args=[unverified_order.id]) + "?format=json")
    assert blocked_lab_resp.status_code == 400

    # Cross-tenant staff_b cannot print tenant_a's invoice
    client_b = Client()
    client_b.force_login(staff_b)
    cross_resp = client_b.get(reverse("billing-invoice-print", args=[invoice_a.id]) + "?format=json")
    assert cross_resp.status_code == 404