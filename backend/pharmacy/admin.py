# backend/pharmacy/admin.py
from django.contrib import admin
from .models import Medicine, MedicineBatch, PharmacySale, PharmacySaleItem, StockMovement, Supplier


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("brand_name", "salt_composition", "gst_rate_percent", "is_controlled_drug", "tenant_id")
    search_fields = ("brand_name", "generic_name", "salt_composition")
    list_filter = ("is_controlled_drug", "is_active")


@admin.register(MedicineBatch)
class MedicineBatchAdmin(admin.ModelAdmin):
    list_display = ("medicine", "batch_number", "expiry_date", "quantity_on_hand", "mrp", "tenant_id")
    search_fields = ("batch_number", "medicine__brand_name")
    list_filter = ("expiry_date",)


admin.site.register(Supplier)
admin.site.register(PharmacySale)
admin.site.register(PharmacySaleItem)
admin.site.register(StockMovement)