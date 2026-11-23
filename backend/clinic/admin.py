from django.contrib import admin
from .models import Appointment, OPDEncounter, Patient, Prescription, PrescriptionItem


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("uhid", "full_name", "phone_number", "tenant_id", "branch_id", "created_at")
    search_fields = ("uhid", "full_name", "phone_number", "abha_number")
    list_filter = ("gender", "is_active")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("token_number", "patient", "doctor", "visit_date", "status", "tenant_id")
    list_filter = ("status", "visit_date")
    search_fields = ("patient__full_name", "patient__uhid")


@admin.register(OPDEncounter)
class OPDEncounterAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "encounter_date", "diagnosis", "tenant_id")
    list_filter = ("encounter_date",)
    search_fields = ("patient__full_name", "diagnosis", "chief_complaint")


admin.site.register(Prescription)
admin.site.register(PrescriptionItem)