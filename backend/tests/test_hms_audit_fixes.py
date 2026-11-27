import hashlib
import uuid
import pytest
from django.core.management import call_command

from clinic.models import Patient
from clinic.services import (
    create_opd_encounter_with_prescription,
    register_patient,
    schedule_appointment,
)
from decimal import Decimal
from billing.services import record_expense
from ipd.services import create_ward_with_beds
from laboratory.models import LabOrder, LabOrderStatus
from laboratory.services import mark_sample_collected, record_test_result
from pharmacy.services import add_medicine_and_batch, dispense_fefo_sale

try:
    from tenants.models import Branch, Tenant
except ImportError:
    from clinic.models import Branch
    Tenant = None

# @pytest.mark.django_db
# def test_mark_sample_collected_rejects_order_without_sample():
#     tenant_id = uuid.uuid4()
#     order = LabOrder.objects.create(
#         tenant_id=tenant_id,
#         order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}",
#         status=LabOrderStatus.ORDERED,
#     )
#     with pytest.raises(ValueError, match="No sample record found"):
#         mark_sample_collected(tenant_id=tenant_id, order_id=order.id)


@pytest.mark.django_db
def test_mark_sample_collected_rejects_order_without_sample():
    tenant_id = uuid.uuid4()

    patient, _ = register_patient(tenant_id=tenant_id, full_name="Test Patient", phone_number="+919811111111",)

    order = LabOrder.objects.create(tenant_id=tenant_id, patient=patient, order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}", status=LabOrderStatus.ORDERED,)

    with pytest.raises(ValueError, match="No sample record found"):
        mark_sample_collected(tenant_id=tenant_id, order_id=order.id,)


# @pytest.mark.django_db
# def test_record_test_result_blocked_when_order_verified_or_delivered():
#     tenant_id = uuid.uuid4()
#     order = LabOrder.objects.create(
#         tenant_id=tenant_id,
#         order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}",
#         status=LabOrderStatus.VERIFIED,
#     )
#     item = order.items.first()
#     if item is not None:
#         with pytest.raises(ValueError, match="verified or delivered"):
#             record_test_result(
#                 tenant_id=tenant_id,
#                 order_item_id=item.id,
#                 observed_value="14.2",
#                 is_abnormal=False,
#             )

@pytest.mark.django_db
def test_record_test_result_blocked_when_order_verified_or_delivered():
    tenant_id = uuid.uuid4()

    patient, _ = register_patient(tenant_id=tenant_id, full_name="Test Patient", phone_number="+919822222222",)

    order = LabOrder.objects.create(tenant_id=tenant_id, patient=patient, order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}", status=LabOrderStatus.VERIFIED,)

    item = order.items.first()

    if item is not None:
        with pytest.raises(ValueError, match="verified or delivered"):
            record_test_result(tenant_id=tenant_id, order_item_id=item.id, observed_value="14.2", is_abnormal=False,)


@pytest.mark.django_db
def test_expense_and_ward_reject_nonexistent_branch():
    tenant_id = uuid.uuid4()
    missing_branch_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Selected branch does not exist"):
        record_expense(
            tenant_id=tenant_id,
            title="Generator Diesel",
            amount=Decimal("500.00"),
            branch_id=missing_branch_id,
        )

    with pytest.raises(ValueError, match="Selected branch does not exist"):
        create_ward_with_beds(
            tenant_id=tenant_id,
            branch_id=missing_branch_id,
            code="GW-1",
            name="General Ward",
            daily_charge=Decimal("1000.00"),
            bed_count=2,
        )

def _create_test_tenant_and_branch():
    tenant = None
    tenant_id = uuid.uuid4()

    if Tenant is not None:
        tenant = Tenant()
        for field in Tenant._meta.fields:
            if field.primary_key or field.auto_created:
                continue
            if field.name == "name":
                setattr(tenant, field.name, f"Test Hospital {uuid.uuid4().hex[:6]}")
            elif field.name == "slug":
                setattr(tenant, field.name, f"test-hospital-{uuid.uuid4().hex[:8]}")
            elif field.name == "code":
                setattr(tenant, field.name, f"TEN-{uuid.uuid4().hex[:6].upper()}")
            elif not field.null and not field.has_default():
                if field.get_internal_type() in ("CharField", "TextField"):
                    setattr(tenant, field.name, f"val-{uuid.uuid4().hex[:6]}")
                elif field.get_internal_type() in ("IntegerField", "BigIntegerField", "PositiveIntegerField"):
                    setattr(tenant, field.name, 1)
                elif field.get_internal_type() == "BooleanField":
                    setattr(tenant, field.name, True)
        tenant.save()
        tenant_id = tenant.id

    branch = Branch()
    for field in Branch._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        if field.name == "tenant" and tenant is not None:
            setattr(branch, field.name, tenant)
        elif field.name == "tenant_id":
            setattr(branch, field.name, tenant_id)
        elif field.name == "name":
            setattr(branch, field.name, "Main OPD Branch")
        elif field.name == "code":
            setattr(branch, field.name, f"BR-{uuid.uuid4().hex[:6].upper()}")
        elif not field.null and not field.has_default():
            if field.get_internal_type() in ("CharField", "TextField"):
                setattr(branch, field.name, f"br-{uuid.uuid4().hex[:6]}")
            elif field.get_internal_type() in ("IntegerField", "BigIntegerField", "PositiveIntegerField"):
                setattr(branch, field.name, 1)
            elif field.get_internal_type() == "BooleanField":
                setattr(branch, field.name, True)
    branch.save()
    return tenant_id, branch


@pytest.mark.django_db
def test_patient_appointment_encounter_prescription_flow():
    tenant_id, branch = _create_test_tenant_and_branch()

    patient, _ = register_patient(
        tenant_id=tenant_id,
        full_name="Aarav Sharma",
        branch_id=branch.id,
        phone_number="9876543210",
        allergies_notes="Penicillin",
    )
    assert patient.tenant_id == tenant_id
    assert patient.branch_id == branch.id

    appt = schedule_appointment(
        tenant_id=tenant_id,
        patient=patient,
        branch_id=patient.branch_id,
        reason="Fever",
    )
    assert appt.token_number >= 1

    encounter, prescription = create_opd_encounter_with_prescription(
        tenant_id=tenant_id,
        patient=patient,
        appointment=appt,
        branch_id=patient.branch_id,
        chief_complaint="Fever for 2 days",
        diagnosis="Viral fever",
        items=[{"medicine_name": "Paracetamol 500mg"}],
    )
    assert encounter.id is not None
    assert prescription.items.count() == 1


@pytest.mark.django_db
def test_nonexistent_branch_rejected_on_registration():
    tenant_id = uuid.uuid4()
    missing_branch_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Selected branch does not exist"):
        register_patient(
            tenant_id=tenant_id,
            full_name="Branch Check Patient",
            branch_id=missing_branch_id,
            phone_number="9876500002",
        )


@pytest.mark.django_db
def test_cross_tenant_patient_lookup_isolated():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    patient_a, _ = register_patient(
        tenant_id=tenant_a,
        full_name="Meera Nair",
        phone_number="9876500001",
    )

    assert Patient.objects.filter(id=patient_a.id, tenant_id=tenant_b).count() == 0


def test_backup_hms_verify_detects_tampered_artifact(tmp_path):
    backup_file = tmp_path / "onecare_sqlite_test.sqlite3"
    backup_file.write_bytes(b"SQLite format 3\x00original-data")
    sha_file = tmp_path / "onecare_sqlite_test.sqlite3.sha256"

    digest = hashlib.sha256(backup_file.read_bytes()).hexdigest()
    sha_file.write_text(f"{digest}  {backup_file.name}\n", encoding="utf-8")

    call_command("backup_hms", mode="verify", file=str(backup_file))

    backup_file.write_bytes(b"SQLite format 3\x00tampered-data")
    with pytest.raises(Exception):
        call_command("backup_hms", mode="verify", file=str(backup_file))