from django.contrib import admin
from .models import Branch, ModuleEntitlement, PlatformAnnouncement, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "id", "is_active", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tenant_id", "is_main", "is_active")
    search_fields = ("name", "code", "tenant_id")
    list_filter = ("is_main", "is_active")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ModuleEntitlement)
class ModuleEntitlementAdmin(admin.ModelAdmin):
    list_display = ("tenant_id", "module_code", "is_enabled", "updated_at")
    list_filter = ("module_code", "is_enabled")
    search_fields = ("tenant_id",)


@admin.register(PlatformAnnouncement)
class PlatformAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "message")