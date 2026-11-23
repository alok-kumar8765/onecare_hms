from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from accounts.models import UserRole
from core.audit import record_audit_log
from core.models import AuditLog
from .models import Branch, DeploymentPreset, ModuleCode, ModuleEntitlement, PlatformAnnouncement, Tenant
from .services import PRESET_MODULES, provision_tenant, set_tenant_module_state


@login_required
def tenant_overview_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    tenant = Tenant.objects.filter(id=tenant_id).first() if tenant_id else None
    branches = Branch.objects.filter(tenant_id=tenant_id).order_by("-is_main", "name") if tenant_id else []
    entitlements = ModuleEntitlement.objects.filter(tenant_id=tenant_id).order_by("module_code") if tenant_id else []

    return render(
        request,
        "tenants/overview.html",
        {
            "tenant": tenant,
            "branches": branches,
            "entitlements": entitlements,
        },
    )


@login_required
def super_admin_view(request):
    if getattr(request.user, "role", None) != UserRole.SUPER_ADMIN:
        return redirect("tenants-overview")

    feedback = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "provision_tenant":
            name = (request.POST.get("name") or "").strip()
            preset = request.POST.get("deployment_preset") or DeploymentPreset.STANDALONE_CLINIC
            if name:
                modules = PRESET_MODULES.get(preset, PRESET_MODULES[DeploymentPreset.STANDALONE_CLINIC])
                provision_tenant(name=name, enabled_modules=list(modules), actor=request.user, request=request)
                feedback = f"Provisioned tenant '{name}'."
        elif action == "toggle_module":
            tenant_id = request.POST.get("tenant_id")
            module_code = request.POST.get("module_code")
            is_enabled = request.POST.get("is_enabled") == "true"
            if tenant_id and module_code in ModuleCode.values:
                set_tenant_module_state(
                    tenant_id=tenant_id,
                    module_code=module_code,
                    is_enabled=is_enabled,
                    actor=request.user,
                    request=request,
                )
                feedback = f"Updated {module_code} for tenant."
        elif action == "create_announcement":
            title = (request.POST.get("title") or "").strip()
            message = (request.POST.get("message") or "").strip()
            if title and message:
                ann = PlatformAnnouncement.objects.create(title=title, message=message, created_by=request.user)
                record_audit_log(
                    action="platform.announcement.created",
                    resource_type="PlatformAnnouncement",
                    resource_id=ann.id,
                    actor=request.user,
                    request=request,
                    metadata={"title": title},
                )
                feedback = "Published platform announcement."

    tenants = Tenant.objects.prefetch_related("branches", "entitlements").order_by("-created_at")
    recent_audits = AuditLog.objects.all()[:20]
    announcements = PlatformAnnouncement.objects.all()[:10]

    return render(
        request,
        "tenants/super_admin.html",
        {
            "tenants": tenants,
            "module_codes": ModuleCode.choices,
            "deployment_presets": DeploymentPreset.choices,
            "recent_audits": recent_audits,
            "announcements": announcements,
            "feedback": feedback,
        },
    )