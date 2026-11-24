import os
from typing import Optional
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from core.models import BranchScopedModel, TimeStampedModel


def validate_patient_photo(file_obj):
    max_bytes = 2 * 1024 * 1024  # 2 MB
    if file_obj.size > max_bytes:
        raise ValidationError("Patient photo must be 2 MB or smaller.")
    ext = os.path.splitext(file_obj.name or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValidationError("Patient photo must be a JPG, PNG, or WebP image.")


#def patient_photo_upload_path(instance, filename):
#    ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
#    return f"tenants/{instance.tenant_id}/patients/{instance.id}/photo_{uuid.uuid4().hex[:8]}{ext}"

def patient_photo_upload_path(instance, filename):
    ext = os.path.splitext(filename or "")[1].lower() or ".jpg"

    return (
        f"tenants/{instance.tenant_id}/"
        f"patients/{instance.id}/"
        f"photo_{uuid.uuid4().hex[:8]}{ext}"
    )

class Gender(models.TextChoices):
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"
    OTHER = "OTHER", "Other"


class AppointmentStatus(models.TextChoices):
    WAITING = "WAITING", "Waiting in Queue"
    IN_CONSULTATION = "IN_CONSULTATION", "In Consultation"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class Patient(BranchScopedModel):
    uhid = models.CharField(max_length=40, db_index=True)
    full_name = models.CharField(max_length=180, db_index=True)
    gender = models.CharField(max_length=16, choices=Gender.choices, default=Gender.OTHER)
    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    abha_number = models.CharField(max_length=32, blank=True, db_index=True)
    blood_group = models.CharField(max_length=8, blank=True)
    address = models.TextField(blank=True)
    allergies_notes = models.TextField(blank=True)
    photo = models.ImageField(
        upload_to=patient_photo_upload_path,
        validators=[validate_patient_photo],
        null=True,
        blank=True,
        max_length=255,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("tenant_id", "uhid")]

    def __str__(self) -> str:
        return f"{self.uhid} - {self.full_name}"

    @property
    def allergies(self):
        return self.allergies_notes

    @allergies.setter
    def allergies(self, value):
        self.allergies_notes = value or ""


class Appointment(BranchScopedModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clinic_appointments",
    )
    visit_date = models.DateField(default=timezone.localdate, db_index=True)
    token_number = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=24,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.WAITING,
        db_index=True,
    )

    class Meta:
        ordering = ["visit_date", "token_number"]

    def __str__(self) -> str:
        return f"Token #{self.token_number} - {self.patient.full_name}"


class OPDEncounter(BranchScopedModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="encounters")
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encounter",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opd_encounters",
    )
    encounter_date = models.DateField(default=timezone.localdate, db_index=True)
    chief_complaint = models.TextField()
    vitals_summary = models.CharField(max_length=255, blank=True)
    clinical_notes = models.TextField(blank=True)
    diagnosis = models.CharField(max_length=255, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-encounter_date", "-created_at"]


class Prescription(BranchScopedModel):
    encounter = models.ForeignKey(OPDEncounter, on_delete=models.CASCADE, related_name="prescriptions")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="prescriptions")
    prescribed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_prescriptions",
    )
    advice = models.TextField(blank=True)


class PrescriptionItem(TimeStampedModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    medicine_name = models.CharField(max_length=160)
    dosage = models.CharField(max_length=80)
    frequency = models.CharField(max_length=80)
    duration = models.CharField(max_length=80)
    instructions = models.CharField(max_length=200, blank=True)