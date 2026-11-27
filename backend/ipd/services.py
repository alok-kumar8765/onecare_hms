from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any, Dict, List, Optional
import uuid
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from clinic.models import Patient
from core.audit import record_audit_log
from core.import_export import export_rows_to_csv
from .models import (
    AdmissionStatus,
    Bed,
    BedStatus,
    IPDBillingItem,
    IPDAdmission,
    IPDRoundNote,
    Ward,
    WardType,
)
from core.scoping import resolve_scoped_branch_id, validate_patient_branch_alignment
from math import ceil
from django.db.models import Sum

def _q(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



def _quantize_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# @transaction.atomic
# def create_ward_with_beds(
#     *,
#     tenant_id,
#     code: str,
#     name: str,
#     ward_type: str = WardType.GENERAL,
#     daily_charge: Decimal = Decimal("1000.00"),
#     gst_rate_percent: Decimal = Decimal("0.00"),
#     bed_count: int = 1,
#     branch_id=None,
#     actor=None,
#     request=None,
# ) -> tuple[Ward, List[Bed]]:
#     clean_code = code.strip().upper()
#     if not clean_code or not name.strip():
#         raise ValueError("Ward code and name are required.")
#     if bed_count < 0:
#         raise ValueError("Bed count cannot be negative.")

#     ward, _ = Ward.objects.update_or_create(
#         tenant_id=tenant_id,
#         code=clean_code,
#         defaults={
#             "branch_id": branch_id,
#             "name": name.strip(),
#             "ward_type": ward_type or WardType.GENERAL,
#             "daily_charge": _quantize_money(daily_charge),
#             "gst_rate_percent": gst_rate_percent,
#             "is_active": True,
#         },
#     )

#     created_beds: List[Bed] = []
#     for idx in range(1, bed_count + 1):
#         bed_no = f"{clean_code}-B{idx:02d}"
#         bed, _ = Bed.objects.get_or_create(
#             tenant_id=tenant_id,
#             bed_number=bed_no,
#             defaults={
#                 "branch_id": branch_id,
#                 "ward": ward,
#                 "status": BedStatus.AVAILABLE,
#             },
#         )
#         created_beds.append(bed)

#     record_audit_log(
#         action="ipd.ward.saved",
#         resource_type="Ward",
#         resource_id=ward.id,
#         actor=actor,
#         tenant_id=tenant_id,
#         branch_id=branch_id,
#         request=request,
#         metadata={"code": ward.code, "beds_ensured": len(created_beds)},
#     )
#     return ward, created_beds


@transaction.atomic
def create_ward_with_beds(
    *,
    tenant_id,
    code: str,
    name: str,
    ward_type: str = WardType.GENERAL,
    daily_charge: Decimal = Decimal("1000.00"),
    gst_rate_percent: Decimal = Decimal("0.00"),
    bed_count: int = 1,
    branch_id=None,
    actor=None,
    request=None,
) -> tuple[Ward, List[Bed]]:
    clean_code = code.strip().upper()

    if not clean_code or not name.strip():
        raise ValueError("Ward code and name are required.")

    if bed_count < 0:
        raise ValueError("Bed count cannot be negative.")

    # Validate branch belongs to the requested tenant.
    scoped_branch_id = resolve_scoped_branch_id(
        tenant_id=tenant_id,
        requested_branch_id=branch_id,
    )

    ward, _ = Ward.objects.update_or_create(
        tenant_id=tenant_id,
        code=clean_code,
        defaults={
            "branch_id": scoped_branch_id,
            "name": name.strip(),
            "ward_type": ward_type or WardType.GENERAL,
            "daily_charge": _quantize_money(daily_charge),
            "gst_rate_percent": gst_rate_percent,
            "is_active": True,
        },
    )

    created_beds: List[Bed] = []

    for idx in range(1, bed_count + 1):
        bed_no = f"{clean_code}-B{idx:02d}"

        bed, _ = Bed.objects.get_or_create(
            tenant_id=tenant_id,
            bed_number=bed_no,
            defaults={
                "branch_id": scoped_branch_id,
                "ward": ward,
                "status": BedStatus.AVAILABLE,
            },
        )

        created_beds.append(bed)

    record_audit_log(
        action="ipd.ward.saved",
        resource_type="Ward",
        resource_id=ward.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=scoped_branch_id,
        request=request,
        metadata={
            "code": ward.code,
            "beds_ensured": len(created_beds),
        },
    )

    return ward, created_beds


@transaction.atomic
def admit_patient_to_bed(
    *,
    tenant_id,
    patient: Patient,
    bed_id,
    admission_reason: str,
    admitting_doctor=None,
    branch_id=None,
    actor=None,
    request=None,
) -> IPDAdmission:
    if not admission_reason or not admission_reason.strip():
        raise ValueError("Admission reason is required.")

    scoped_branch_id = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id,
    fallback_branch_id=getattr(patient, "branch_id", None) if patient else None,
    )
    validate_patient_branch_alignment(
        tenant_id=tenant_id,
        patient=patient,
        branch_id=scoped_branch_id,
    )
    bed = (
        Bed.objects.select_for_update()
        .select_related("ward")
        .filter(id=bed_id, tenant_id=tenant_id)
        .first()
    )
    if not bed:
        raise ValueError("Bed not found in your organization.")
    if bed.status != BedStatus.AVAILABLE:
        raise ValueError(f"Bed {bed.bed_number} is currently {bed.status} and cannot be assigned.")

    admission_no = f"IPD-{timezone.localdate().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    admission = IPDAdmission.objects.create(
        tenant_id=tenant_id,
        branch_id=scoped_branch_id or bed.branch_id or patient.branch_id,
        admission_number=admission_no,
        patient=patient,
        ward=bed.ward,
        bed=bed,
        admitting_doctor=admitting_doctor or actor,
        admitted_at=timezone.now(),
        status=AdmissionStatus.ADMITTED,
        admission_reason=admission_reason.strip(),
    )

    bed.status = BedStatus.OCCUPIED
    bed.save(update_fields=["status", "updated_at"])

    record_audit_log(
        action="ipd.patient.admitted",
        resource_type="IPDAdmission",
        resource_id=admission.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=admission.branch_id,
        request=request,
        metadata={"admission_number": admission.admission_number, "bed_number": bed.bed_number},
    )
    return admission


@transaction.atomic
def add_ipd_round_note(
    *,
    tenant_id,
    admission_id,
    clinical_notes: str,
    vitals: str = "",
    treatment_plan: str = "",
    actor=None,
    request=None,
) -> IPDRoundNote:
    admission = IPDAdmission.objects.filter(id=admission_id, tenant_id=tenant_id).first()
    if not admission:
        raise ValueError("IPD admission not found in your organization.")
    if not clinical_notes or not clinical_notes.strip():
        raise ValueError("Clinical round notes are required.")

    note = IPDRoundNote.objects.create(
        tenant_id=tenant_id,
        branch_id=admission.branch_id,
        admission=admission,
        recorded_by=actor,
        vitals=vitals.strip(),
        clinical_notes=clinical_notes.strip(),
        treatment_plan=treatment_plan.strip(),
    )
    record_audit_log(
        action="ipd.round_note.added",
        resource_type="IPDRoundNote",
        resource_id=note.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=admission.branch_id,
        request=request,
        metadata={"admission_number": admission.admission_number},
    )
    return note


@transaction.atomic
def add_ipd_billing_item(
    *,
    tenant_id,
    admission_id,
    description: str,
    quantity: int,
    unit_rate: Decimal,
    gst_rate_percent: Decimal = Decimal("0.00"),
) -> IPDBillingItem:
    admission = IPDAdmission.objects.filter(id=admission_id, tenant_id=tenant_id).first()
    if not admission:
        raise ValueError("IPD admission not found in your organization.")
    if not description or not description.strip():
        raise ValueError("Billing item description is required.")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    base = _quantize_money(_quantize_money(unit_rate) * Decimal(quantity))
    gst = _quantize_money((base * gst_rate_percent) / Decimal("100"))
    line_total = _quantize_money(base + gst)

    return IPDBillingItem.objects.create(
        admission=admission,
        description=description.strip(),
        quantity=quantity,
        unit_rate=_quantize_money(unit_rate),
        gst_rate_percent=gst_rate_percent,
        line_total=line_total,
    )


@transaction.atomic
def discharge_ipd_patient(
    *,
    tenant_id,
    admission_id,
    discharge_summary: str = "",
    discharged_at: Optional[datetime] = None,
    actor=None,
    request=None,
) -> IPDAdmission:
    admission = (
        IPDAdmission.objects.select_related("ward", "bed")
        .prefetch_related("billing_items")
        .filter(id=admission_id, tenant_id=tenant_id)
        .first()
    )
    if not admission:
        raise ValueError("IPD admission not found in your organization.")
    if admission.status == AdmissionStatus.DISCHARGED:
        raise ValueError("Patient is already discharged.")

    end_ts = discharged_at or timezone.now()
    elapsed_seconds = max(0.0, (end_ts - admission.admitted_at).total_seconds())
    stay_days = max(1, math.ceil(elapsed_seconds / 86400.0))

    bed_base = _quantize_money(admission.ward.daily_charge * Decimal(stay_days))
    bed_gst = _quantize_money((bed_base * admission.ward.gst_rate_percent) / Decimal("100"))

    items_subtotal = Decimal("0.00")
    items_gst = Decimal("0.00")
    for item in admission.billing_items.all():
        item_base = _quantize_money(item.unit_rate * Decimal(item.quantity))
        item_gst = _quantize_money((item_base * item.gst_rate_percent) / Decimal("100"))
        items_subtotal += item_base
        items_gst += item_gst

    subtotal = _quantize_money(bed_base + items_subtotal)
    total_gst = _quantize_money(bed_gst + items_gst)
    total = _quantize_money(subtotal + total_gst)

    admission.status = AdmissionStatus.DISCHARGED
    admission.discharged_at = end_ts
    if discharge_summary and discharge_summary.strip():
        admission.discharge_summary = discharge_summary.strip()
    admission.subtotal_amount = subtotal
    admission.gst_amount = total_gst
    admission.total_amount = total
    admission.save(
        update_fields=[
            "status",
            "discharged_at",
            "discharge_summary",
            "subtotal_amount",
            "gst_amount",
            "total_amount",
            "updated_at",
        ]
    )

    bed = Bed.objects.select_for_update().filter(id=admission.bed_id).first()
    if bed:
        bed.status = BedStatus.AVAILABLE
        bed.save(update_fields=["status", "updated_at"])

    record_audit_log(
        action="ipd.patient.discharged",
        resource_type="IPDAdmission",
        resource_id=admission.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=admission.branch_id,
        request=request,
        metadata={
            "admission_number": admission.admission_number,
            "stay_days": stay_days,
            "total_amount": str(admission.total_amount),
        },
    )
    return admission


def export_ipd_admissions_csv(admissions_qs: QuerySet) -> str:
    headers = [
        "admission_number",
        "patient_uhid",
        "patient_name",
        "ward_name",
        "bed_number",
        "status",
        "subtotal_amount",
        "gst_amount",
        "total_amount",
        "admitted_at",
        "discharged_at",
    ]
    rows: List[Dict[str, Any]] = []
    for adm in admissions_qs:
        rows.append({
            "admission_number": adm.admission_number,
            "patient_uhid": adm.patient.uhid,
            "patient_name": adm.patient.full_name,
            "ward_name": adm.ward.name,
            "bed_number": adm.bed.bed_number,
            "status": adm.status,
            "subtotal_amount": str(adm.subtotal_amount),
            "gst_amount": str(adm.gst_amount),
            "total_amount": str(adm.total_amount),
            "admitted_at": adm.admitted_at.isoformat() if adm.admitted_at else "",
            "discharged_at": adm.discharged_at.isoformat() if adm.discharged_at else "",
        })
    return export_rows_to_csv(headers, rows)

@transaction.atomic
def transfer_ipd_bed(
    *,
    tenant_id,
    admission_id,
    target_bed_id,
    transfer_reason: str = "",
    actor=None,
    request=None,
) -> IPDAdmission:
    """
    Atomically transfers an admitted IPD patient from their current bed to an
    AVAILABLE target bed within the same tenant (and branch if branch-scoped).
    """
    admission = (
        IPDAdmission.objects.select_for_update()
        .select_related("ward", "bed", "patient")
        .filter(id=admission_id, tenant_id=tenant_id)
        .first()
    )
    if not admission:
        raise ValueError("IPD admission not found in your organization.")
    if admission.status != AdmissionStatus.ADMITTED:
        raise ValueError("Only currently admitted patients can be transferred to another bed.")

    target_bed = (
        Bed.objects.select_for_update()
        .select_related("ward")
        .filter(id=target_bed_id, tenant_id=tenant_id)
        .first()
    )
    if not target_bed:
        raise ValueError("Target bed not found in your organization.")
    if str(target_bed.id) == str(admission.bed_id):
        raise ValueError("Patient is already assigned to this bed.")
    if target_bed.status != BedStatus.AVAILABLE:
        raise ValueError("Target bed is not available for transfer.")
    if (
        admission.branch_id
        and getattr(target_bed, "branch_id", None)
        and str(admission.branch_id) != str(target_bed.branch_id)
    ):
        raise ValueError("Target bed belongs to a different branch than the admission.")

    old_bed = admission.bed
    old_label = f"{admission.ward.name}/{old_bed.bed_number}"
    new_label = f"{target_bed.ward.name}/{target_bed.bed_number}"

    old_bed.status = BedStatus.AVAILABLE
    old_bed.save(update_fields=["status", "updated_at"])

    target_bed.status = BedStatus.OCCUPIED
    target_bed.save(update_fields=["status", "updated_at"])

    admission.ward = target_bed.ward
    admission.bed = target_bed
    admission.save(update_fields=["ward", "bed", "updated_at"])

    note_body = f"Bed Transfer: {old_label} -> {new_label}."
    if transfer_reason.strip():
        note_body = f"{note_body} Reason: {transfer_reason.strip()}"

    IPDRoundNote.objects.create(
    tenant_id=tenant_id,
    branch_id=admission.branch_id,
    admission=admission,
    recorded_by=actor,
    clinical_notes=note_body,
    treatment_plan="Bed transfer completed.",
    )

    record_audit_log(
        action="ipd.bed_transferred",
        resource_type="IPDAdmission",
        resource_id=admission.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=admission.branch_id,
        request=request,
        metadata={
            "admission_number": admission.admission_number,
            "from_bed": old_label,
            "to_bed": new_label,
        },
    )
    return admission


def compute_ipd_running_ledger(*, tenant_id, admission_id, as_of=None) -> dict:
    """
    Computes live accrued IPD room/bed charges plus itemized IPDBillingItem charges
    for an active or discharged admission without mutating admission state.
    """
    admission = (
        IPDAdmission.objects.select_related("ward", "bed")
        .filter(id=admission_id, tenant_id=tenant_id)
        .first()
    )
    if not admission:
        raise ValueError("IPD admission not found in your organization.")

    end_time = admission.discharged_at or as_of or timezone.now()
    elapsed_seconds = max((end_time - admission.admitted_at).total_seconds(), 0)
    billable_days = max(1, ceil(elapsed_seconds / 86400))
    bed_charges = _quantize_money(Decimal(billable_days) * admission.ward.daily_charge)

    items_subtotal = (
        IPDBillingItem.objects.filter(admission=admission).aggregate(s=Sum("line_total"))["s"]
        or Decimal("0.00")
    )
    items_subtotal = _quantize_money(items_subtotal)
    running_total = _quantize_money(bed_charges + items_subtotal)

    return {
        "admission_number": admission.admission_number,
        "status": admission.status,
        "billable_days": billable_days,
        "daily_charge": _quantize_money(admission.ward.daily_charge),
        "accrued_bed_charges": bed_charges,
        "itemized_charges": items_subtotal,
        "running_total": running_total,
    }