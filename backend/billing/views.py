# backend/billing/views.py
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from clinic.models import Patient
from tenants.models import ModuleCode
from tenants.services import is_module_enabled
from .models import ExpenseEntry, Invoice, PaymentMethod
from .services import (
    create_invoice_with_items,
    export_invoices_csv,
    record_expense,
    record_invoice_payment,
    summarize_finance,
)


@login_required
def billing_dashboard_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    if tenant_id and not is_module_enabled(tenant_id, ModuleCode.BILLING):
        return render(request, "clinic/module_disabled.html", {"module_name": "Billing & Finance"})

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
            if action == "create_invoice":
                patient = Patient.objects.filter(id=request.POST.get("patient_id"), tenant_id=tenant_id).first()
                inv = create_invoice_with_items(
                    tenant_id=tenant_id,
                    patient=patient,
                    customer_name=request.POST.get("customer_name") or "",
                    discount_amount=Decimal((request.POST.get("discount_amount") or "0.00").strip()),
                    branch_id=getattr(request.user, "primary_branch_id", None),
                    items=[
                        {
                            "description": (request.POST.get("description") or "").strip(),
                            "category": request.POST.get("category") or "OPD",
                            "quantity": int(request.POST.get("quantity") or 1),
                            "unit_price": Decimal((request.POST.get("unit_price") or "0.00").strip()),
                            "gst_rate_percent": Decimal((request.POST.get("gst_rate_percent") or "0.00").strip()),
                        }
                    ],
                    actor=request.user,
                    request=request,
                )
                feedback = f"Created Invoice {inv.invoice_number} (Total ₹{inv.total_amount})."
            elif action == "record_payment":
                txn = record_invoice_payment(
                    tenant_id=tenant_id,
                    invoice_id=request.POST.get("invoice_id"),
                    amount=Decimal((request.POST.get("amount") or "0.00").strip()),
                    method=request.POST.get("method") or PaymentMethod.UPI,
                    reference_no=request.POST.get("reference_no") or "",
                    actor=request.user,
                    request=request,
                )
                feedback = f"Recorded ₹{txn.amount} ({txn.method}) for {txn.invoice.invoice_number}."
            elif action == "record_expense":
                exp = record_expense(
                    tenant_id=tenant_id,
                    title=request.POST.get("title") or "",
                    amount=Decimal((request.POST.get("amount") or "0.00").strip()),
                    category=request.POST.get("category") or "OPERATIONAL",
                    vendor_name=request.POST.get("vendor_name") or "",
                    branch_id=getattr(request.user, "primary_branch_id", None),
                    actor=request.user,
                    request=request,
                )
                feedback = f"Logged expense '{exp.title}' (₹{exp.amount})."
        except (ValueError, InvalidOperation) as exc:
            error = str(exc)

    invoices = Invoice.objects.prefetch_related("payments").filter(tenant_id=tenant_id)[:40] if tenant_id else []
    if request.GET.get("export") == "csv" and tenant_id:
        resp = HttpResponse(export_invoices_csv(invoices), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="billing_invoices.csv"'
        return resp

    expenses = ExpenseEntry.objects.filter(tenant_id=tenant_id)[:30] if tenant_id else []
    patients = Patient.objects.filter(tenant_id=tenant_id)[:50] if tenant_id else []
    summary = (
        summarize_finance(tenant_id=tenant_id)
        if tenant_id
        else {
            "total_invoiced": Decimal("0.00"),
            "total_collected": Decimal("0.00"),
            "pending_receivables": Decimal("0.00"),
            "total_expenses": Decimal("0.00"),
            "net_cashflow": Decimal("0.00"),
        }
    )

    return render(
        request,
        "billing/dashboard.html",
        {
            "invoices": invoices,
            "expenses": expenses,
            "patients": patients,
            "summary": summary,
            "payment_methods": PaymentMethod.choices,
            "feedback": feedback,
            "error": error,
        },
    )