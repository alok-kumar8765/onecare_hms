# backend/clinic/views.py
from core.linked_workflows import dispense_prescription_to_pharmacy_sale
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models.functions import TruncMonth
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, render
from accounts.models import UserRole
from tenants.models import ModuleCode
from core.print_summaries import build_prescription_print_payload
from tenants.services import is_module_enabled
from .models import Appointment, Patient
from django.http import JsonResponse
from .services import (
    create_opd_encounter_with_prescription,
    export_encounters_csv,
    filter_encounters_queryset,
    register_patient,
    schedule_appointment,
)

User = get_user_model()


def _parse_date_safe(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        return None


@login_required
def clinic_dashboard_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    if tenant_id and not is_module_enabled(tenant_id, ModuleCode.CLINIC_OPD):
        return render(
            request,
            "clinic/module_disabled.html",
            {"module_name": "Clinic, OPD & EMR"},
        )

    feedback = None
    error = None
    last_saved_patient = None

    if request.method == "POST" and not tenant_id:
        error = (
            "No clinic or hospital organization (tenant) is linked to your account. "
            "Sign in with a tenant staff account or use a tenant-scoped account first."
        )
        
    if request.method == "POST" and tenant_id:
        action = request.POST.get("action")
        try:
            if action == "register_patient":
                full_name = (request.POST.get("full_name") or "").strip()
                if not full_name:
                    error = "Patient full name is required."
                else:
                    patient, dups = register_patient(
                        tenant_id=tenant_id,
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        full_name=full_name,
                        gender=request.POST.get("gender") or "OTHER",
                        date_of_birth=_parse_date_safe(request.POST.get("date_of_birth")),
                        phone_number=request.POST.get("phone_number") or "",
                        abha_number=request.POST.get("abha_number") or "",
                        photo=request.FILES.get("photo"),
                        allow_duplicate=request.POST.get("allow_duplicate") == "on",
                        actor=request.user,
                        request=request,
                    )
                    #feedback = f"Registered patient {patient.uhid} ({patient.full_name}). Potential matches: {len(dups)}."
                    last_saved_patient = patient

                    feedback = (
                        f"Saved in DB — UHID: {patient.uhid} | "
                        f"Name: {patient.full_name} "
                        f"(Duplicates matched: {len(dups)})."
                    )
            elif action == "book_appointment":
                patient = Patient.objects.filter(id=request.POST.get("patient_id"), tenant_id=tenant_id).first()
                doctor = User.objects.filter(id=request.POST.get("doctor_id"), tenant_id=tenant_id).first()
                if not patient:
                    error = "Select a valid patient."
                else:
                    appt = schedule_appointment(
                        tenant_id=tenant_id,
                        patient=patient,
                        doctor=doctor,
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        visit_date=_parse_date_safe(request.POST.get("visit_date")),
                        reason=request.POST.get("reason") or "",
                        actor=request.user,
                        request=request,
                    )
                    feedback = f"Scheduled token #{appt.token_number} for {patient.full_name}."
            elif action == "record_encounter":
                patient = Patient.objects.filter(id=request.POST.get("patient_id"), tenant_id=tenant_id).first()
                complaint = (request.POST.get("chief_complaint") or "").strip()
                if not patient or not complaint:
                    error = "Patient and chief complaint are required."
                else:
                    med_name = (request.POST.get("medicine_name") or "").strip()
                    items = []
                    if med_name:
                        items.append({
                            "medicine_name": med_name,
                            "dosage": request.POST.get("dosage") or "1 tab",
                            "frequency": request.POST.get("frequency") or "Twice daily",
                            "duration": request.POST.get("duration") or "5 days",
                        })
                    create_opd_encounter_with_prescription(
                        tenant_id=tenant_id,
                        patient=patient,
                        doctor=request.user if request.user.role == UserRole.DOCTOR else None,
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        chief_complaint=complaint,
                        vitals_summary=request.POST.get("vitals_summary") or "",
                        diagnosis=request.POST.get("diagnosis") or "",
                        follow_up_date=_parse_date_safe(request.POST.get("follow_up_date")),
                        items=items,
                        actor=request.user,
                        request=request,
                    )
                    feedback = f"Saved consultation & prescription for {patient.full_name}."
            elif action == "dispense_prescription":
                sale = dispense_prescription_to_pharmacy_sale(
                    tenant_id=tenant_id,
                    prescription_id=request.POST.get("prescription_id"),
                    branch_id=getattr(request.user, "primary_branch_id", None),
                    actor=request.user,
                    request=request,
                )
                feedback = (
                    f"Dispensed prescription into Pharmacy Sale "
                    f"{sale.invoice_number} (Total ₹{sale.total_amount})."
                )
        except ValueError as exc:
            error = str(exc)

    period = request.GET.get("period") or "all"
    doctor_id = request.GET.get("doctor_id") or ""
    start_date = _parse_date_safe(request.GET.get("start_date"))
    end_date = _parse_date_safe(request.GET.get("end_date"))

    encounters_qs = (
    filter_encounters_queryset(
        tenant_id=tenant_id,
        period=period,
        doctor_id=doctor_id or None,
        start_date=start_date,
        end_date=end_date,
    ).select_related(
        "patient",
        "doctor",
        "prescription",
    )
    if tenant_id
    else []
    )

    if request.GET.get("export") == "csv" and tenant_id:
        csv_content = export_encounters_csv(encounters_qs)
        resp = HttpResponse(csv_content, content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="clinic_records_{period}.csv"'
        return resp

    monthly_qs = (
        filter_encounters_queryset(tenant_id=tenant_id, doctor_id=doctor_id or None)
        .annotate(month_bucket=TruncMonth("encounter_date"))
        .values("month_bucket")
        .annotate(total=Count("id"))
        .order_by("month_bucket")
    ) if tenant_id else []

    chart_labels = [row["month_bucket"].strftime("%b %Y") for row in monthly_qs if row["month_bucket"]]
    chart_values = [row["total"] for row in monthly_qs if row["month_bucket"]]

    patients = (
    Patient.objects
    .filter(tenant_id=tenant_id)
    .order_by("-created_at")[:50]
    if tenant_id else []
)
    appointments = Appointment.objects.select_related("patient", "doctor").filter(tenant_id=tenant_id)[:30] if tenant_id else []
    doctors = User.objects.filter(tenant_id=tenant_id, role=UserRole.DOCTOR) if tenant_id else []

    return render(
        request,
        "clinic/dashboard.html",
        {
            "patients": patients,
            "last_saved_patient": last_saved_patient,
            "appointments": appointments,
            "encounters": encounters_qs[:50],
            "doctors": doctors,
            "period": period,
            "selected_doctor_id": doctor_id,
            "start_date": request.GET.get("start_date") or "",
            "end_date": request.GET.get("end_date") or "",
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "feedback": feedback,
            "error": error,
            "user": request.user,
            "request": request,
        },
    )

@login_required
def prescription_print_view(request, prescription_id):
    tenant_id = getattr(request.user, "tenant_id", None)
    if not tenant_id:
        return JsonResponse({"detail": "No tenant context found."}, status=403)
    try:
        payload = build_prescription_print_payload(tenant_id=tenant_id, prescription_id=prescription_id)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=404)

    if request.GET.get("format") == "json":
        #   return JsonResponse(payload, default=str)
        return JsonResponse(payload, json_dumps_params={"default": str})
    return render(request, "clinic/prescription_print.html", {"doc": payload})