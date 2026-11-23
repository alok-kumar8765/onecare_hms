# backend/ipd/views.py
from core.linked_workflows import create_invoice_from_ipd_admission
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from clinic.models import Patient
from tenants.models import ModuleCode
from tenants.services import is_module_enabled
from .models import Bed, BedStatus, IPDAdmission, Ward, WardType
from .services import (
    add_ipd_billing_item,
    add_ipd_round_note,
    admit_patient_to_bed,
    create_ward_with_beds,
    discharge_ipd_patient,
    export_ipd_admissions_csv,
    transfer_ipd_bed,
)

@login_required
def ipd_dashboard_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    if tenant_id and not is_module_enabled(tenant_id, ModuleCode.IPD):
        return render(request, "clinic/module_disabled.html", {"module_name": "Hospital & IPD Management"})

    feedback = None
    error = None

    if request.method == "POST" and not tenant_id:
        error = (
            "No clinic or hospital organization (tenant) is linked to your account. "
            "Sign in with a tenant staff account or use a tenant-scoped account first."
        )
        
    if request.method == "POST" and tenant_id:
        action = request.POST.get("action")
        try:
            if action == "create_ward":
                ward, beds = create_ward_with_beds(
                    tenant_id=tenant_id,
                    branch_id=getattr(request.user, "primary_branch_id", None),
                    code=request.POST.get("code") or "",
                    name=request.POST.get("name") or "",
                    ward_type=request.POST.get("ward_type") or WardType.GENERAL,
                    daily_charge=Decimal((request.POST.get("daily_charge") or "1000.00").strip()),
                    bed_count=int(request.POST.get("bed_count") or 0),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Saved ward {ward.code} with {len(beds)} bed(s)."
            elif action == "admit_patient":
                patient = Patient.objects.filter(id=request.POST.get("patient_id"), tenant_id=tenant_id).first()
                if not patient:
                    error = "Select a valid patient."
                else:
                    adm = admit_patient_to_bed(
                        tenant_id=tenant_id,
                        patient=patient,
                        bed_id=request.POST.get("bed_id"),
                        admission_reason=request.POST.get("admission_reason") or "",
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        actor=request.user,
                        request=request,
                    )
                    feedback = f"Admitted {patient.full_name} ({adm.admission_number}) on bed {adm.bed.bed_number}."
            elif action == "add_round":
                add_ipd_round_note(
                    tenant_id=tenant_id,
                    admission_id=request.POST.get("admission_id"),
                    vitals=request.POST.get("vitals") or "",
                    clinical_notes=request.POST.get("clinical_notes") or "",
                    treatment_plan=request.POST.get("treatment_plan") or "",
                    actor=request.user,
                    request=request,
                )
                feedback = "Recorded daily IPD round note."
            elif action == "add_charge":
                add_ipd_billing_item(
                    tenant_id=tenant_id,
                    admission_id=request.POST.get("admission_id"),
                    description=request.POST.get("description") or "",
                    quantity=int(request.POST.get("quantity") or 1),
                    unit_rate=Decimal((request.POST.get("unit_rate") or "0.00").strip()),
                )
                feedback = "Added IPD billing charge."
            elif action == "discharge":
                adm = discharge_ipd_patient(
                    tenant_id=tenant_id,
                    admission_id=request.POST.get("admission_id"),
                    discharge_summary=request.POST.get("discharge_summary") or "",
                    actor=request.user,
                    request=request,
                )
                feedback = f"Discharged {adm.admission_number} — Final Bill: ₹{adm.total_amount}."
            elif action == "transfer_bed":
                updated_adm = transfer_ipd_bed(
                    tenant_id=tenant_id,
                    admission_id=request.POST.get("admission_id"),
                    target_bed_id=request.POST.get("target_bed_id"),
                    transfer_reason=request.POST.get("transfer_reason") or "",
                    actor=request.user,
                    request=request,
                )
                feedback = f"Transferred {updated_adm.admission_number} to {updated_adm.ward.name}/{updated_adm.bed.bed_number}."
            elif action == "convert_to_invoice":
                inv = create_invoice_from_ipd_admission(
                    tenant_id=tenant_id,
                    admission_id=request.POST.get("admission_id"),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Generated Billing Invoice {inv.invoice_number} (Total ₹{inv.total_amount})."
        except (ValueError, InvalidOperation) as exc:
            error = str(exc)

    admissions = (
        IPDAdmission.objects.select_related("patient", "ward", "bed")
        .prefetch_related("round_notes", "billing_items")
        .filter(tenant_id=tenant_id)[:40]
        if tenant_id
        else []
    )
    if request.GET.get("export") == "csv" and tenant_id:
        resp = HttpResponse(export_ipd_admissions_csv(admissions), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="ipd_admissions.csv"'
        return resp

    wards = Ward.objects.filter(tenant_id=tenant_id, is_active=True) if tenant_id else []
    available_beds = Bed.objects.select_related("ward").filter(tenant_id=tenant_id, status=BedStatus.AVAILABLE) if tenant_id else []
    patients = Patient.objects.filter(tenant_id=tenant_id)[:50] if tenant_id else []

    return render(
        request,
        "ipd/dashboard.html",
        {
            "wards": wards,
            "available_beds": available_beds,
            "admissions": admissions,
            "patients": patients,
            "ward_types": WardType.choices,
            "feedback": feedback,
            "error": error,
        },
    )