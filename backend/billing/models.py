from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from clinic.models import Patient
from core.models import BranchScopedModel, TimeStampedModel


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ISSUED = "ISSUED", "Issued"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
    PAID = "PAID", "Paid"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    UPI = "UPI", "UPI"
    CARD = "CARD", "Card"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer / NEFT / RTGS"
    INSURANCE = "INSURANCE", "Health Insurance / TPA"


class Invoice(BranchScopedModel):
    invoice_number = models.CharField(max_length=60, unique=True, db_index=True)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    customer_name = models.CharField(max_length=180, blank=True)
    status = models.CharField(
        max_length=24,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.ISSUED,
        db_index=True,
    )
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def balance_due(self) -> Decimal:
        due = self.total_amount - self.paid_amount
        return due if due > Decimal("0.00") else Decimal("0.00")

    def __str__(self) -> str:
        return f"{self.invoice_number} (₹{self.total_amount})"


class InvoiceLineItem(TimeStampedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=220)
    category = models.CharField(max_length=60, default="GENERAL")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    hsn_sac_code = models.CharField(max_length=16, blank=True, default="")

class PaymentTransaction(BranchScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=24, choices=PaymentMethod.choices, default=PaymentMethod.UPI)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference_no = models.CharField(max_length=120, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )

    class Meta:
        ordering = ["-created_at"]


class ExpenseEntry(BranchScopedModel):
    title = models.CharField(max_length=180, db_index=True)
    category = models.CharField(max_length=80, default="OPERATIONAL")
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vendor_name = models.CharField(max_length=160, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_expenses",
    )

    class Meta:
        ordering = ["-expense_date", "-created_at"]