from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from clinic.models import Patient
from core.models import BranchScopedModel, TimeStampedModel


class WardType(models.TextChoices):
    GENERAL = "GENERAL", "General Ward"
    SEMI_PRIVATE = "SEMI_PRIVATE", "Semi-Private Room"
    PRIVATE = "PRIVATE", "Private Deluxe Room"
    ICU = "ICU", "Intensive Care Unit (ICU)"
    NICU = "NICU", "Neonatal ICU (NICU)"


class BedStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    OCCUPIED = "OCCUPIED", "Occupied"
    MAINTENANCE = "MAINTENANCE", "Maintenance / Cleaning"
    RESERVED = "RESERVED", "Reserved"


class AdmissionStatus(models.TextChoices):
    ADMITTED = "ADMITTED", "Admitted"
    DISCHARGED = "DISCHARGED", "Discharged"
    TRANSFERRED = "TRANSFERRED", "Transferred"


class Ward(BranchScopedModel):
    code = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=140)
    ward_type = models.CharField(max_length=24, choices=WardType.choices, default=WardType.GENERAL)
    daily_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1000.00"))
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant_id", "code")]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Bed(BranchScopedModel):
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    bed_number = models.CharField(max_length=32, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=BedStatus.choices,
        default=BedStatus.AVAILABLE,
        db_index=True,
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["ward__name", "bed_number"]
        unique_together = [("tenant_id", "bed_number")]

    def __str__(self) -> str:
        return f"{self.ward.code}/{self.bed_number} ({self.status})"


class IPDAdmission(BranchScopedModel):
    admission_number = models.CharField(max_length=60, unique=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="ipd_admissions")
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="admissions")
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="admissions")
    admitting_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admitted_ipd_patients",
    )
    admitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    discharged_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.ADMITTED,
        db_index=True,
    )
    admission_reason = models.TextField()
    discharge_summary = models.TextField(blank=True)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["-admitted_at"]

    def __str__(self) -> str:
        return f"{self.admission_number} - {self.patient.full_name}"


class IPDRoundNote(BranchScopedModel):
    admission = models.ForeignKey(IPDAdmission, on_delete=models.CASCADE, related_name="round_notes")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ipd_round_notes",
    )
    vitals = models.CharField(max_length=200, blank=True)
    clinical_notes = models.TextField()
    treatment_plan = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class IPDBillingItem(TimeStampedModel):
    admission = models.ForeignKey(IPDAdmission, on_delete=models.CASCADE, related_name="billing_items")
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_rate = models.DecimalField(max_digits=10, decimal_places=2)
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))