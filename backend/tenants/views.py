from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from accounts.models import UserRole
from billing.models import ExpenseEntry, Invoice
from billing.services import summarize_finance
from clinic.models import OPDEncounter, Patient
from core.audit import record_audit_log
from core.import_export import export_rows_to_csv
from core.models import AuditLog
from ipd.models import Bed, IPDAdmission, Ward
from laboratory.models import LabOrder, LabTest
from pharmacy.models import Medicine, MedicineBatch, PharmacySale
from .models import Branch, DeploymentPreset, ModuleCode, ModuleEntitlement, PlatformAnnouncement, Tenant
from .services import (
    PRESET_MODULES,
    create_tenant_branch,
    provision_tenant,
    set_tenant_module_state,
)

User = get_user_model()

ALLOWED_STAFF_ROLES = [
    UserRole.HOSPITAL_ADMIN,
    UserRole.DOCTOR,
    UserRole.RECEPTIONIST,
    UserRole.NURSE,
    UserRole.PHARMACIST,
    UserRole.LAB_TECHNICIAN,
    UserRole.LAB_MANAGER,
    UserRole.ACCOUNTANT,
]


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


@login_required
def setup_wizard_view(request):
    """
    No-shell setup screen so Platform Owner (SUPER_ADMIN) or Hospital Admin
    can create tenants, add branches, toggle modules, and onboard staff users
    from the browser without running manual Django shell commands.
    """
    user_role = getattr(request.user, "role", None)
    is_super = user_role == UserRole.SUPER_ADMIN or request.user.is_superuser
    is_org_admin = user_role in {UserRole.HOSPITAL_OWNER, UserRole.HOSPITAL_ADMIN}
    if not (is_super or is_org_admin):
        return redirect("tenants-overview")

    feedback = None
    error = None

    all_tenants = (
        Tenant.objects.prefetch_related("branches", "entitlements").order_by("-created_at")
        if is_super
        else Tenant.objects.prefetch_related("branches", "entitlements").filter(id=request.user.tenant_id)
    )

    selected_tenant_id = request.POST.get("tenant_id") or request.GET.get("tenant_id") or (
        str(all_tenants.first().id) if all_tenants.exists() else ""
    )
    active_tenant = Tenant.objects.filter(id=selected_tenant_id).first() if selected_tenant_id else None
    if active_tenant and not is_super and str(active_tenant.id) != str(request.user.tenant_id):
        active_tenant = all_tenants.first()

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_tenant" and is_super:
                name = (request.POST.get("name") or "").strip()
                preset = request.POST.get("deployment_preset") or DeploymentPreset.STANDALONE_CLINIC
                if not name:
                    raise ValueError("Organization name is required.")
                new_tenant = provision_tenant(
                    name=name,
                    deployment_preset=preset,
                    actor=request.user,
                    request=request,
                )
                active_tenant = new_tenant
                selected_tenant_id = str(new_tenant.id)
                feedback = f"Created '{new_tenant.name}' (tenant_id: {new_tenant.id}) with main branch."

            elif action == "add_branch" and active_tenant:
                branch_name = (request.POST.get("branch_name") or "").strip()
                branch_code = (request.POST.get("branch_code") or "").strip()
                address = (request.POST.get("address") or "").strip()
                if not branch_name or not branch_code:
                    raise ValueError("Branch name and code are required.")
                branch = create_tenant_branch(
                    tenant_id=active_tenant.id,
                    name=branch_name,
                    code=branch_code,
                    address=address,
                    actor=request.user,
                    request=request,
                )
                feedback = f"Added branch '{branch.name}' ({branch.code}) to {active_tenant.name}."

            elif action == "set_module" and active_tenant and (is_super or is_org_admin):
                mod_code = request.POST.get("module_code")
                enabled = request.POST.get("is_enabled") == "true"
                if mod_code not in ModuleCode.values:
                    raise ValueError("Invalid module code.")
                set_tenant_module_state(
                    tenant_id=active_tenant.id,
                    module_code=mod_code,
                    is_enabled=enabled,
                    actor=request.user,
                    request=request,
                )
                feedback = f"Set {mod_code} to {'ENABLED' if enabled else 'DISABLED'} for {active_tenant.name}."

            elif action == "create_staff" and active_tenant:
                username = (request.POST.get("username") or "").strip()
                password = (request.POST.get("password") or "").strip()
                role = (request.POST.get("role") or "").strip()
                branch_id = request.POST.get("branch_id") or None
                if not username or not password:
                    raise ValueError("Username and password are required for staff creation.")
                if role not in ALLOWED_STAFF_ROLES:
                    raise ValueError("Invalid staff role selected.")
                if User.objects.filter(username=username).exists():
                    raise ValueError(f"Username '{username}' already exists.")
                staff = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=(request.POST.get("first_name") or "").strip(),
                    last_name=(request.POST.get("last_name") or "").strip(),
                    role=role,
                    tenant_id=active_tenant.id,
                    primary_branch_id=branch_id,
                )
                feedback = f"Created user '{staff.username}' with role {role} under {active_tenant.name}."
        except ValueError as exc:
            error = str(exc)

    branches = Branch.objects.filter(tenant_id=active_tenant.id).order_by("-is_main", "name") if active_tenant else []
    entitlements = (
        ModuleEntitlement.objects.filter(tenant_id=active_tenant.id).order_by("module_code")
        if active_tenant
        else []
    )
    staff_users = User.objects.filter(tenant_id=active_tenant.id).order_by("username")[:30] if active_tenant else []

    return render(
        request,
        "tenants/setup_wizard.html",
        {
            "is_super": is_super,
            "all_tenants": all_tenants,
            "active_tenant": active_tenant,
            "selected_tenant_id": str(active_tenant.id) if active_tenant else "",
            "branches": branches,
            "entitlements": entitlements,
            "staff_users": staff_users,
            "deployment_presets": DeploymentPreset.choices,
            "module_codes": ModuleCode.choices,
            "staff_roles": ALLOWED_STAFF_ROLES,
            "feedback": feedback,
            "error": error,
        },
    )


@login_required
def reports_hub_view(request):
    tenant_id = getattr(request.user, "tenant_id", None)
    if not tenant_id and getattr(request.user, "role", None) == UserRole.SUPER_ADMIN:
        first_tenant = Tenant.objects.order_by("-created_at").first()
        tenant_id = first_tenant.id if first_tenant else None

    if request.GET.get("export") == "summary_csv" and tenant_id:
        fin = summarize_finance(tenant_id=tenant_id)
        rows = [
            {"metric": "Patients Registered", "value": str(Patient.objects.filter(tenant_id=tenant_id).count())},
            {"metric": "OPD Encounters", "value": str(OPDEncounter.objects.filter(tenant_id=tenant_id).count())},
            {"metric": "Pharmacy Sales Invoices", "value": str(PharmacySale.objects.filter(tenant_id=tenant_id).count())},
            {"metric": "Lab Orders", "value": str(LabOrder.objects.filter(tenant_id=tenant_id).count())},
            {"metric": "IPD Admissions", "value": str(IPDAdmission.objects.filter(tenant_id=tenant_id).count())},
            {"metric": "Total Invoiced (INR)", "value": str(fin["total_invoiced"])},
            {"metric": "Total Collected (INR)", "value": str(fin["total_collected"])},
            {"metric": "Pending Receivables (INR)", "value": str(fin["pending_receivables"])},
            {"metric": "Total Expenses (INR)", "value": str(fin["total_expenses"])},
            {"metric": "Net Cashflow (INR)", "value": str(fin["net_cashflow"])},
        ]
        csv_data = export_rows_to_csv(["metric", "value"], rows)
        resp = HttpResponse(csv_data, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="onecare_consolidated_report.csv"'
        return resp

    stats = {
        "patients": Patient.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "encounters": OPDEncounter.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "medicines": Medicine.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "batches": MedicineBatch.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "sales": PharmacySale.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "lab_tests": LabTest.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "lab_orders": LabOrder.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "wards": Ward.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "beds": Bed.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "admissions": IPDAdmission.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "invoices": Invoice.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
        "expenses": ExpenseEntry.objects.filter(tenant_id=tenant_id).count() if tenant_id else 0,
    }
    finance = (
        summarize_finance(tenant_id=tenant_id)
        if tenant_id
        else {
            "total_invoiced": Decimal("0.00"),
            "total_collected": Decimal("0.00"),
            "pending_receivables": Decimal("0.00"),
            "total_expenses": Decimal("0.00"),
            "net_cashflow": Decimal("0.00"),
        }
    )

    return render(
        request,
        "tenants/reports_hub.html",
        {
            "stats": stats,
            "finance": finance,
            "tenant_id": str(tenant_id) if tenant_id else "",
        },
    )