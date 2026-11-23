# backend/ipd/admin.py
from django.contrib import admin
from .models import Bed, IPDBillingItem, IPDAdmission, IPDRoundNote, Ward


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "ward_type", "daily_charge", "tenant_id", "is_active")
    list_filter = ("ward_type", "is_active")
    search_fields = ("code", "name")


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ("bed_number", "ward", "status", "tenant_id")
    list_filter = ("status",)
    search_fields = ("bed_number", "ward__name")


@admin.register(IPDAdmission)
class IPDAdmissionAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "patient", "ward", "bed", "status", "total_amount", "tenant_id")
    list_filter = ("status",)
    search_fields = ("admission_number", "patient__full_name")


admin.site.register(IPDRoundNote)
admin.site.register(IPDBillingItem)