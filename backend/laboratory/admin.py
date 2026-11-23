# backend/laboratory/admin.py
from django.contrib import admin
from .models import LabOrder, LabOrderItem, LabPackage, LabResult, LabSample, LabTest


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department", "price", "gst_rate_percent", "tenant_id")
    search_fields = ("code", "name", "department")
    list_filter = ("department", "is_active")


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "patient", "status", "total_amount", "tenant_id", "created_at")
    list_filter = ("status",)
    search_fields = ("order_number", "patient__full_name")


admin.site.register(LabPackage)
admin.site.register(LabOrderItem)
admin.site.register(LabSample)
admin.site.register(LabResult)