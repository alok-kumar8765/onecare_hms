from rest_framework import serializers
from .models import ExpenseEntry, Invoice, InvoiceLineItem, PaymentTransaction


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLineItem
        fields = ["id", "description", "category", "quantity", "unit_price", "gst_rate_percent", "line_total"]
        read_only_fields = ["id", "line_total"]


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ["id", "invoice", "method", "amount", "reference_no", "created_at"]
        read_only_fields = ["id", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceLineItemSerializer(many=True, read_only=True)
    payments = PaymentTransactionSerializer(many=True, read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "invoice_number",
            "patient",
            "customer_name",
            "status",
            "subtotal_amount",
            "gst_amount",
            "discount_amount",
            "total_amount",
            "paid_amount",
            "balance_due",
            "notes",
            "items",
            "payments",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "invoice_number",
            "subtotal_amount",
            "gst_amount",
            "total_amount",
            "paid_amount",
            "balance_due",
            "created_at",
        ]


class ExpenseEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseEntry
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "title",
            "category",
            "expense_date",
            "amount",
            "gst_amount",
            "vendor_name",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at"]