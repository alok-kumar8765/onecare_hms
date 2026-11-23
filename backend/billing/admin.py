# backend/billing/admin.py
from django.contrib import admin
from .models import ExpenseEntry, Invoice, InvoiceLineItem, PaymentTransaction


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer_name", "status", "total_amount", "paid_amount", "tenant_id")
    list_filter = ("status",)
    search_fields = ("invoice_number", "customer_name")


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("invoice", "method", "amount", "reference_no", "tenant_id", "created_at")
    list_filter = ("method",)


@admin.register(ExpenseEntry)
class ExpenseEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "amount", "expense_date", "tenant_id")
    list_filter = ("category", "expense_date")
    search_fields = ("title", "vendor_name")


admin.site.register(InvoiceLineItem)