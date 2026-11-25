from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User, UserRole
from billing.models import Invoice, InvoiceLineItem
from clinic.models import OPDEncounter, Prescription, PrescriptionItem
from clinic.services import register_patient
from laboratory.models import LabOrder, LabOrderItem, LabTest
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_named_urls_and_html_print_templates_render():
    tenant = provision_tenant(name="Template Audit Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    doctor = User.objects.create_user(
        username="dr_tpl",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.DOCTOR,
    )
    patient, _ = register_patient(
        tenant_id=tenant.id,
        full_name="Kavita Joshi",
        phone_number="+919855555555",
    )
    patient.allergies = "Penicillin"
    patient.save(update_fields=["allergies_notes"])

    invoice = Invoice.objects.create(
        tenant_id=tenant.id,
        patient=patient,
        customer_name=patient.full_name,
        invoice_number="INV-HTML-001",
        subtotal_amount=Decimal("1000.00"),
        gst_amount=Decimal("180.00"),
        total_amount=Decimal("1180.00"),
    )
    InvoiceLineItem.objects.create(
        invoice=invoice,
        description="CT Scan",
        hsn_sac_code="999312",
        quantity=1,
        unit_price=Decimal("1000.00"),
        gst_rate_percent=Decimal("18.00"),
        line_total=Decimal("1180.00"),
    )

    encounter = OPDEncounter.objects.create(
        tenant_id=tenant.id,
        patient=patient,
        doctor=doctor,
        chief_complaint="Headache",
    )
    rx = Prescription.objects.create(
        tenant_id=tenant.id,
        encounter=encounter,
        patient=patient,
        prescribed_by=doctor,
        advice="Rest and hydration",
    )
    PrescriptionItem.objects.create(
        prescription=rx,
        medicine_name="Paracetamol 500mg",
        dosage="1 tab",
        frequency="SOS",
        duration="3 days",
        
    )

    test = LabTest.objects.create(
        tenant_id=tenant.id,
        code="HB",
        name="Hemoglobin",
        price=Decimal("250.00"),
        unit="g/dL",
        reference_range="12.0 - 15.5",
    )
    verified_order = LabOrder.objects.create(
        tenant_id=tenant.id,
        patient=patient,
        order_number="LAB-VER-001",
        status="VERIFIED",
    )
    LabOrderItem.objects.create(
        order=verified_order,
        test=test,
        price=Decimal("250.00"),
        
    )

    # Verify named backup URLs resolve cleanly
    assert reverse("core-backup-download") == "/core/backup/download/"
    assert reverse("core-backup-drive-upload") == "/core/backup/drive-upload/"
    assert reverse("core-backup-restore") == "/core/backup/restore/"

    client = Client()
    client.force_login(doctor)

    inv_html = client.get(reverse("billing-invoice-print", args=[invoice.id]))
    assert inv_html.status_code == 200
    assert b"INV-HTML-001" in inv_html.content
    assert b"999312" in inv_html.content

    rx_html = client.get(reverse("clinic-prescription-print", args=[rx.id]))
    assert rx_html.status_code == 200
    assert b"Kavita Joshi" in rx_html.content
    assert b"Penicillin" in rx_html.content

    lab_html = client.get(reverse("laboratory-report-print", args=[verified_order.id]))
    assert lab_html.status_code == 200
    assert b"LAB-VER-001" in lab_html.content
    assert b"Hemoglobin" in lab_html.content
    assert b"g/dL" in lab_html.content

    billing_dash = client.get(reverse("billing-dashboard"))
    assert billing_dash.status_code == 200
    assert b"export=gst_return_csv" in billing_dash.content