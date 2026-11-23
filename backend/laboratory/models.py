from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from clinic.models import Patient
from core.models import BranchScopedModel, TenantScopedModel, TimeStampedModel


class LabOrderStatus(models.TextChoices):
    ORDERED = "ORDERED", "Ordered"
    SAMPLE_COLLECTED = "SAMPLE_COLLECTED", "Sample Collected"
    IN_PROGRESS = "IN_PROGRESS", "Testing In Progress"
    VERIFIED = "VERIFIED", "Verified by Pathologist/Manager"
    DELIVERED = "DELIVERED", "Report Delivered"


class LabTest(TenantScopedModel):
    code = models.CharField(max_length=40, db_index=True)
    name = models.CharField(max_length=180, db_index=True)
    department = models.CharField(max_length=80, default="Pathology")
    sample_type = models.CharField(max_length=80, default="Whole Blood / Serum")
    reference_range = models.CharField(max_length=160, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant_id", "code")]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class LabPackage(TenantScopedModel):
    code = models.CharField(max_length=40, db_index=True)
    name = models.CharField(max_length=180)
    tests = models.ManyToManyField(LabTest, related_name="packages", blank=True)
    package_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant_id", "code")]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class LabOrder(BranchScopedModel):
    order_number = models.CharField(max_length=60, unique=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="lab_orders")
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordered_lab_orders",
    )
    status = models.CharField(
        max_length=24,
        choices=LabOrderStatus.choices,
        default=LabOrderStatus.ORDERED,
        db_index=True,
    )
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order_number} ({self.patient.full_name})"


class LabOrderItem(TimeStampedModel):
    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name="items")
    test = models.ForeignKey(LabTest, on_delete=models.PROTECT, related_name="order_items")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))


class LabSample(BranchScopedModel):
    order = models.OneToOneField(LabOrder, on_delete=models.CASCADE, related_name="sample")
    barcode = models.CharField(max_length=64, unique=True, db_index=True)
    sample_type = models.CharField(max_length=120, default="Blood / Urine")
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collected_lab_samples",
    )

    def __str__(self) -> str:
        return f"Sample {self.barcode} -> {self.order.order_number}"


class LabResult(BranchScopedModel):
    order_item = models.OneToOneField(LabOrderItem, on_delete=models.CASCADE, related_name="result")
    observed_value = models.CharField(max_length=160)
    unit = models.CharField(max_length=40, blank=True)
    reference_range = models.CharField(max_length=160, blank=True)
    is_abnormal = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entered_lab_results",
    )
    entered_at = models.DateTimeField(default=timezone.now)
    is_verified = models.BooleanField(default=False, db_index=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_lab_results",
    )
    verified_at = models.DateTimeField(null=True, blank=True)