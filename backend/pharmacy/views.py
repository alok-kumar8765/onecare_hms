# backend/pharmacy/views.py
from datetime import date
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from tenants.models import ModuleCode
from tenants.services import is_module_enabled
from .models import MedicineBatch, PharmacySale
from .services import (
    add_medicine_and_batch,
    dispense_fefo_sale,
    export_pharmacy_sales_csv,
    search_medicines,
)


# @login_required
# def pharmacy_dashboard_view(request):
#     tenant_id = getattr(request.user, "tenant_id", None)
#     if tenant_id and not is_module_enabled(tenant_id, ModuleCode.PHARMACY):
#         return render(request, "clinic/module_disabled.html", {"module_name": "Pharmacy & Inventory"})

#     feedback = None
#     error = None

#     if request.method == "POST" and tenant_id:
#         action = request.POST.get("action")
#         try:
#             if action == "add_batch":
#                 exp = date.fromisoformat((request.POST.get("expiry_date") or "").strip())
#                 qty = int(request.POST.get("quantity") or 0)
#                 mrp = Decimal((request.POST.get("mrp") or "0").strip())
#                 gst = Decimal((request.POST.get("gst_rate_percent") or "12.00").strip())
#                 med, batch = add_medicine_and_batch(
#                     tenant_id=tenant_id,
#                     branch_id=getattr(request.user, "primary_branch_id", None),
#                     brand_name=(request.POST.get("brand_name") or "").strip(),
#                     generic_name=(request.POST.get("generic_name") or "").strip(),
#                     salt_composition=(request.POST.get("salt_composition") or "").strip(),
#                     batch_number=(request.POST.get("batch_number") or "").strip(),
#                     expiry_date=exp,
#                     quantity=qty,
#                     unit_price=mrp,
#                     gst_rate_percent=gst,
#                     is_controlled_drug=request.POST.get("is_controlled_drug") == "on",
#                     actor=request.user,
#                     request=request,
#                 )
#                 feedback = f"Added batch {batch.batch_number} ({qty} units) for {med.brand_name}."
#             elif action == "dispense_sale":
#                 med_id = (request.POST.get("medicine_id") or "").strip()
#                 qty = int(request.POST.get("quantity") or 0)
#                 sale = dispense_fefo_sale(
#                     tenant_id=tenant_id,
#                     branch_id=getattr(request.user, "primary_branch_id", None),
#                     items_requested=[{"medicine_id": med_id, "quantity": qty}],
#                     customer_name=(request.POST.get("customer_name") or "").strip(),
#                     actor=request.user,
#                     request=request,
#                 )
#                 feedback = f"Dispensed invoice {sale.invoice_number} (Total ₹{sale.total_amount})."
#         except (ValueError, InvalidOperation) as exc:
#             error = str(exc)

#     query = (request.GET.get("q") or "").strip()
#     medicines = search_medicines(tenant_id=tenant_id, query=query) if tenant_id else []
#     batches = MedicineBatch.objects.select_related("medicine").filter(tenant_id=tenant_id).order_by("expiry_date")[:50] if tenant_id else []
#     sales = PharmacySale.objects.filter(tenant_id=tenant_id)[:30] if tenant_id else []

#     if request.GET.get("export") == "csv" and tenant_id:
#         resp = HttpResponse(export_pharmacy_sales_csv(sales), content_type="text/csv")
#         resp["Content-Disposition"] = 'attachment; filename="pharmacy_sales.csv"'
#         return resp

#     return render(
#         request,
#         "pharmacy/dashboard.html",
#         {
#             "medicines": medicines,
#             "batches": batches,
#             "sales": sales,
#             "query": query,
#             "feedback": feedback,
#             "error": error,
#         },
#     )


@login_required
def pharmacy_dashboard_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)

    if tenant_id and not is_module_enabled(tenant_id, ModuleCode.PHARMACY):
        return render(
            request,
            "clinic/module_disabled.html",
            {"module_name": "Pharmacy & Inventory"}
        )

    feedback = None
    error = None

    if request.method == "POST":
        if not tenant_id:
            error = "No clinic or hospital organization (tenant) is linked to your account. Sign in with a tenant staff account or use a tenant-scoped account first."
        else:
            action = request.POST.get("action")

            try:
                if action == "add_batch":
                    exp = date.fromisoformat(
                        (request.POST.get("expiry_date") or "").strip()
                    )
                    qty = int(request.POST.get("quantity") or 0)
                    mrp = Decimal((request.POST.get("mrp") or "0").strip())
                    gst = Decimal(
                        (request.POST.get("gst_rate_percent") or "12.00").strip()
                    )

                    med, batch = add_medicine_and_batch(
                        tenant_id=tenant_id,
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        brand_name=(request.POST.get("brand_name") or "").strip(),
                        generic_name=(request.POST.get("generic_name") or "").strip(),
                        salt_composition=(request.POST.get("salt_composition") or "").strip(),
                        batch_number=(request.POST.get("batch_number") or "").strip(),
                        expiry_date=exp,
                        quantity=qty,
                        unit_price=mrp,
                        gst_rate_percent=gst,
                        is_controlled_drug=request.POST.get("is_controlled_drug") == "on",
                        actor=request.user,
                        request=request,
                    )

                    feedback = (
                        f"Added batch {batch.batch_number} "
                        f"({qty} units) for {med.brand_name}."
                    )

                elif action == "dispense_sale":
                    med_id = (request.POST.get("medicine_id") or "").strip()
                    qty = int(request.POST.get("quantity") or 0)

                    sale = dispense_fefo_sale(
                        tenant_id=tenant_id,
                        branch_id=getattr(request.user, "primary_branch_id", None),
                        items_requested=[
                            {"medicine_id": med_id, "quantity": qty}
                        ],
                        customer_name=(request.POST.get("customer_name") or "").strip(),
                        actor=request.user,
                        request=request,
                    )

                    feedback = (
                        f"Dispensed invoice {sale.invoice_number} "
                        f"(Total ₹{sale.total_amount})."
                    )

            except (ValueError, InvalidOperation) as exc:
                error = str(exc)

    query = (request.GET.get("q") or "").strip()

    medicines = (
        search_medicines(tenant_id=tenant_id, query=query)
        if tenant_id else []
    )

    batches = (
        MedicineBatch.objects.select_related("medicine")
        .filter(tenant_id=tenant_id)
        .order_by("expiry_date")[:50]
        if tenant_id else []
    )

    sales = (
        PharmacySale.objects.filter(tenant_id=tenant_id)[:30]
        if tenant_id else []
    )

    if request.GET.get("export") == "csv" and tenant_id:
        resp = HttpResponse(
            export_pharmacy_sales_csv(sales),
            content_type="text/csv"
        )
        resp["Content-Disposition"] = 'attachment; filename="pharmacy_sales.csv"'
        return resp

    return render(
        request,
        "pharmacy/dashboard.html",
        {
            "medicines": medicines,
            "batches": batches,
            "sales": sales,
            "query": query,
            "feedback": feedback,
            "error": error,
        },
    )
