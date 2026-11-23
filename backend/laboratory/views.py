# backend/laboratory/views.py
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from clinic.models import Patient
from tenants.models import ModuleCode
from tenants.services import is_module_enabled
from .models import LabOrder, LabTest
from .services import (
    create_lab_order,
    create_lab_test,
    deliver_lab_report,
    export_lab_orders_csv,
    mark_sample_collected,
    record_test_result,
    verify_lab_order,
)
from django.shortcuts import render, get_object_or_404
from rest_framework.decorators import api_view


@login_required
def laboratory_dashboard_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    if tenant_id and not is_module_enabled(tenant_id, ModuleCode.LABORATORY):
        return render(request, "clinic/module_disabled.html", {"module_name": "Laboratory & Diagnostics"})

    feedback = None
    error = None

    if request.method == "POST" and tenant_id:
        action = request.POST.get("action")
        try:
            if action == "create_test":
                test = create_lab_test(
                    tenant_id=tenant_id,
                    code=request.POST.get("code") or "",
                    name=request.POST.get("name") or "",
                    price=Decimal((request.POST.get("price") or "0").strip()),
                    department=request.POST.get("department") or "Pathology",
                    sample_type=request.POST.get("sample_type") or "Blood",
                    reference_range=request.POST.get("reference_range") or "",
                    unit=request.POST.get("unit") or "",
                    gst_rate_percent=Decimal((request.POST.get("gst_rate_percent") or "0").strip()),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Saved lab test {test.code} ({test.name})."
            elif action == "create_order":
                patient = Patient.objects.filter(id=request.POST.get("patient_id"), tenant_id=tenant_id).first()
                test_ids = request.POST.getlist("test_ids")
                if not patient:
                    error = "Select a valid patient."
                else:
                    order = create_lab_order(
                        tenant_id=tenant_id,
                        patient=patient,
                        test_ids=test_ids,
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        actor=request.user,
                        request=request,
                    )
                    feedback = f"Created Lab Order {order.order_number} (Barcode: {order.sample.barcode})."
            elif action == "collect_sample":
                sample = mark_sample_collected(
                    tenant_id=tenant_id,
                    order_id=request.POST.get("order_id"),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Collected sample {sample.barcode}."
            elif action == "enter_result":
                record_test_result(
                    tenant_id=tenant_id,
                    order_item_id=request.POST.get("order_item_id"),
                    observed_value=request.POST.get("observed_value") or "",
                    is_abnormal=request.POST.get("is_abnormal") == "on",
                    actor=request.user,
                    request=request,
                )
                feedback = "Recorded test result."
            elif action == "verify_order":
                order = verify_lab_order(
                    tenant_id=tenant_id,
                    order_id=request.POST.get("order_id"),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Verified report for {order.order_number}."
            elif action == "deliver_report":
                order = deliver_lab_report(
                    tenant_id=tenant_id,
                    order_id=request.POST.get("order_id"),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Delivered report for {order.order_number}."
        except (ValueError, PermissionError, InvalidOperation) as exc:
            error = str(exc)

    orders = (
        LabOrder.objects.select_related("patient", "sample")
        .prefetch_related("items__test", "items__result")
        .filter(tenant_id=tenant_id)[:40]
        if tenant_id
        else []
    )
    if request.GET.get("export") == "csv" and tenant_id:
        resp = HttpResponse(export_lab_orders_csv(orders), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="laboratory_orders.csv"'
        return resp

    tests = LabTest.objects.filter(tenant_id=tenant_id, is_active=True) if tenant_id else []
    patients = Patient.objects.filter(tenant_id=tenant_id)[:50] if tenant_id else []

    return render(
        request,
        "laboratory/dashboard.html",
        {
            "tests": tests,
            "patients": patients,
            "orders": orders,
            "feedback": feedback,
            "error": error,
        },
    )