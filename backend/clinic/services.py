from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from core.audit import record_audit_log
from core.import_export import export_rows_to_csv
from .models import Appointment, AppointmentStatus, OPDEncounter, Patient, Prescription, PrescriptionItem


def find_duplicate_patients(
    *,
    tenant_id,
    full_name: str = "",
    phone_number: str = "",
    abha_number: str = "",
    date_of_birth: Optional[date] = None,
) -> QuerySet:
    qs = Patient.objects.filter(tenant_id=tenant_id)
    cond = Q()
    has_criterion = False

    if phone_number and phone_number.strip():
        cond |= Q(phone_number=phone_number.strip())
        has_criterion = True

    if abha_number and abha_number.strip():
        cond |= Q(abha_number=abha_number.strip())
        has_criterion = True

    if full_name and full_name.strip() and date_of_birth:
        cond |= Q(full_name__iexact=full_name.strip(), date_of_birth=date_of_birth)
        has_criterion = True

    if not has_criterion:
        return qs.none()
    return qs.filter(cond).order_by("-created_at")


@transaction.atomic
def register_patient(
    *,
    tenant_id,
    full_name: str,
    branch_id=None,
    gender: str = "OTHER",
    date_of_birth: Optional[date] = None,
    phone_number: str = "",
    email: str = "",
    abha_number: str = "",
    blood_group: str = "",
    address: str = "",
    allergies_notes: str = "",
    photo=None,
    allow_duplicate: bool = False,
    actor=None,
    request=None,
) -> Tuple[Patient, List[Patient]]:
    duplicates = list(
        find_duplicate_patients(
            tenant_id=tenant_id,
            full_name=full_name,
            phone_number=phone_number,
            abha_number=abha_number,
            date_of_birth=date_of_birth,
        )
    )
    if duplicates and not allow_duplicate:
        raise ValueError("Potential duplicate patient record found; confirm duplicate override if intended.")

    uhid = f"OC-{timezone.localdate().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    patient = Patient.objects.create(
        tenant_id=tenant_id,
        branch_id=branch_id,
        uhid=uhid,
        full_name=full_name.strip(),
        gender=gender,
        date_of_birth=date_of_birth,
        phone_number=phone_number.strip(),
        email=email.strip(),
        abha_number=abha_number.strip(),
        blood_group=blood_group.strip(),
        address=address.strip(),
        allergies_notes=allergies_notes.strip(),
        photo=photo,
    )
    record_audit_log(
        action="clinic.patient.registered",
        resource_type="Patient",
        resource_id=patient.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=branch_id,
        request=request,
        metadata={"uhid": patient.uhid, "duplicates_found": len(duplicates)},
    )
    return patient, duplicates


@transaction.atomic
def schedule_appointment(
    *,
    tenant_id,
    patient: Patient,
    doctor=None,
    branch_id=None,
    visit_date: Optional[date] = None,
    reason: str = "",
    actor=None,
    request=None,
) -> Appointment:
    target_date = visit_date or timezone.localdate()
    existing_max = (
        Appointment.objects.filter(tenant_id=tenant_id, visit_date=target_date)
        .order_by("-token_number")
        .values_list("token_number", flat=True)
        .first()
    )
    next_token = (existing_max or 0) + 1

    appt = Appointment.objects.create(
        tenant_id=tenant_id,
        branch_id=branch_id or patient.branch_id,
        patient=patient,
        doctor=doctor,
        visit_date=target_date,
        token_number=next_token,
        reason=reason.strip(),
        status=AppointmentStatus.WAITING,
    )
    record_audit_log(
        action="clinic.appointment.scheduled",
        resource_type="Appointment",
        resource_id=appt.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=appt.branch_id,
        request=request,
        metadata={"token_number": appt.token_number, "visit_date": str(target_date)},
    )
    return appt


@transaction.atomic
def create_opd_encounter_with_prescription(
    *,
    tenant_id,
    patient: Patient,
    doctor=None,
    appointment: Optional[Appointment] = None,
    branch_id=None,
    chief_complaint: str,
    vitals_summary: str = "",
    clinical_notes: str = "",
    diagnosis: str = "",
    follow_up_date: Optional[date] = None,
    advice: str = "",
    items: Optional[List[Dict[str, Any]]] = None,
    actor=None,
    request=None,
) -> Tuple[OPDEncounter, Prescription]:
    encounter = OPDEncounter.objects.create(
        tenant_id=tenant_id,
        branch_id=branch_id or patient.branch_id,
        patient=patient,
        appointment=appointment,
        doctor=doctor or actor,
        encounter_date=timezone.localdate(),
        chief_complaint=chief_complaint.strip(),
        vitals_summary=vitals_summary.strip(),
        clinical_notes=clinical_notes.strip(),
        diagnosis=diagnosis.strip(),
        follow_up_date=follow_up_date,
    )
    prescription = Prescription.objects.create(
        tenant_id=tenant_id,
        branch_id=encounter.branch_id,
        encounter=encounter,
        patient=patient,
        prescribed_by=doctor or actor,
        advice=advice.strip(),
    )
    for item in items or []:
        if item.get("medicine_name"):
            PrescriptionItem.objects.create(
                prescription=prescription,
                medicine_name=item["medicine_name"].strip(),
                dosage=(item.get("dosage") or "1 tab").strip(),
                frequency=(item.get("frequency") or "Once daily").strip(),
                duration=(item.get("duration") or "5 days").strip(),
                instructions=(item.get("instructions") or "").strip(),
            )

    if appointment:
        appointment.status = AppointmentStatus.COMPLETED
        appointment.save(update_fields=["status", "updated_at"])

    record_audit_log(
        action="clinic.encounter.created",
        resource_type="OPDEncounter",
        resource_id=encounter.id,
        actor=actor or doctor,
        tenant_id=tenant_id,
        branch_id=encounter.branch_id,
        request=request,
        metadata={"patient_id": str(patient.id), "diagnosis": encounter.diagnosis},
    )
    return encounter, prescription


def filter_encounters_queryset(
    *,
    tenant_id,
    period: str = "all",
    doctor_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> QuerySet:
    qs = OPDEncounter.objects.select_related("patient", "doctor").filter(tenant_id=tenant_id)
    today = timezone.localdate()

    if period == "this_month":
        first_of_month = today.replace(day=1)
        qs = qs.filter(encounter_date__gte=first_of_month, encounter_date__lte=today)
    elif period == "this_year":
        first_of_year = today.replace(month=1, day=1)
        qs = qs.filter(encounter_date__gte=first_of_year, encounter_date__lte=today)
    elif period == "previous_year":
        prev_year = today.year - 1
        qs = qs.filter(encounter_date__year=prev_year)

    if start_date:
        qs = qs.filter(encounter_date__gte=start_date)
    if end_date:
        qs = qs.filter(encounter_date__lte=end_date)
    if doctor_id:
        qs = qs.filter(doctor_id=doctor_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    return qs


def export_encounters_csv(qs: QuerySet) -> str:
    headers = [
        "encounter_id",
        "encounter_date",
        "uhid",
        "patient_name",
        "patient_phone",
        "doctor_name",
        "diagnosis",
        "chief_complaint",
        "follow_up_date",
    ]
    rows: List[Dict[str, Any]] = []
    for enc in qs:
        doc_name = ""
        if enc.doctor:
            doc_name = enc.doctor.get_full_name() or enc.doctor.username
        rows.append({
            "encounter_id": str(enc.id),
            "encounter_date": enc.encounter_date.isoformat(),
            "uhid": enc.patient.uhid,
            "patient_name": enc.patient.full_name,
            "patient_phone": enc.patient.phone_number,
            "doctor_name": doc_name,
            "diagnosis": enc.diagnosis,
            "chief_complaint": enc.chief_complaint,
            "follow_up_date": enc.follow_up_date.isoformat() if enc.follow_up_date else "",
        })
    return export_rows_to_csv(headers, rows)