from typing import List, Optional
from django.db import transaction
from django.utils.text import slugify
from core.audit import record_audit_log
from .models import Branch, DeploymentPreset, ModuleCode, ModuleEntitlement, SubscriptionPlan, Tenant


PRESET_MODULES = {
    DeploymentPreset.FULL_HOSPITAL: [
        ModuleCode.HOSPITAL_IPD,
        ModuleCode.CLINIC_OPD,
        ModuleCode.LABORATORY,
        ModuleCode.PHARMACY,
        ModuleCode.BILLING,
        ModuleCode.HR,
        ModuleCode.ANALYTICS,
        ModuleCode.IPD,
    ],
    DeploymentPreset.STANDALONE_CLINIC: [
        ModuleCode.CLINIC_OPD,
        ModuleCode.BILLING,
        ModuleCode.ANALYTICS,
    ],
    DeploymentPreset.CLINIC_LAB: [
        ModuleCode.CLINIC_OPD,
        ModuleCode.LABORATORY,
        ModuleCode.BILLING,
        ModuleCode.ANALYTICS,
    ],
    DeploymentPreset.CLINIC_PHARMACY: [
        ModuleCode.CLINIC_OPD,
        ModuleCode.PHARMACY,
        ModuleCode.BILLING,
        ModuleCode.ANALYTICS,
    ],
    DeploymentPreset.STANDALONE_PHARMACY: [
        ModuleCode.PHARMACY,
        ModuleCode.BILLING,
        ModuleCode.ANALYTICS,
    ],
    DeploymentPreset.STANDALONE_LAB: [
        ModuleCode.LABORATORY,
        ModuleCode.BILLING,
        ModuleCode.ANALYTICS,
    ],
}


@transaction.atomic
def provision_tenant(
    *,
    name: str,
    slug: Optional[str] = None,
    plan: Optional[SubscriptionPlan] = None,
    deployment_preset: Optional[str] = None,
    enabled_modules: Optional[List[str]] = None,
    main_branch_name: str = "Main Branch",
    main_branch_code: str = "MAIN",
    actor=None,
    request=None,
) -> Tenant:
    resolved_slug = slug or slugify(name)
    modules_to_enable = enabled_modules
    if modules_to_enable is None:
        if deployment_preset and deployment_preset in PRESET_MODULES:
            modules_to_enable = list(PRESET_MODULES[deployment_preset])
        elif plan and plan.default_modules:
            modules_to_enable = list(plan.default_modules)
        elif plan and plan.deployment_preset in PRESET_MODULES:
            modules_to_enable = list(PRESET_MODULES[plan.deployment_preset])
        else:
            modules_to_enable = list(PRESET_MODULES[DeploymentPreset.STANDALONE_CLINIC])

    tenant = Tenant.objects.create(
        name=name,
        slug=resolved_slug,
        plan=plan,
        is_active=True,
    )
    Branch.objects.create(
        tenant=tenant,
        name=main_branch_name,
        code=main_branch_code,
        is_main=True,
        is_active=True,
    )
    for code in ModuleCode.values:
        ModuleEntitlement.objects.create(
            tenant=tenant,
            module_code=code,
            is_enabled=(code in modules_to_enable),
        )

    record_audit_log(
        action="tenant.provisioned",
        resource_type="Tenant",
        resource_id=tenant.id,
        actor=actor,
        tenant_id=tenant.id,
        request=request,
        metadata={"slug": tenant.slug, "enabled_modules": modules_to_enable},
    )
    return tenant


def get_enabled_modules(tenant_id) -> List[str]:
    if not tenant_id:
        return []
    return list(
        ModuleEntitlement.objects.filter(tenant_id=tenant_id, is_enabled=True)
        .values_list("module_code", flat=True)
    )


def is_module_enabled(tenant_id, module_code: str) -> bool:
    if not tenant_id:
        return False
    return ModuleEntitlement.objects.filter(
        tenant_id=tenant_id,
        module_code=module_code,
        is_enabled=True,
    ).exists()

def set_tenant_module_state(*, tenant_id, module_code: str, is_enabled: bool, actor=None, request=None) -> ModuleEntitlement:
    entitlement, _ = ModuleEntitlement.objects.update_or_create(
        tenant_id=tenant_id,
        module_code=module_code,
        defaults={"is_enabled": is_enabled},
    )
    record_audit_log(
        action="tenant.module.updated",
        resource_type="ModuleEntitlement",
        resource_id=entitlement.id,
        actor=actor,
        tenant_id=tenant_id,
        request=request,
        metadata={"module_code": module_code, "is_enabled": is_enabled},
    )
    return entitlement


def create_tenant_branch(*, tenant_id, name: str, code: str, address: str = "", phone_number: str = "", actor=None, request=None) -> Branch:
    branch = Branch.objects.create(
        tenant_id=tenant_id,
        name=name.strip(),
        code=code.strip().upper(),
        address=address.strip(),
        phone_number=phone_number.strip(),
        is_main=False,
        is_active=True,
    )
    record_audit_log(
        action="tenant.branch.created",
        resource_type="Branch",
        resource_id=branch.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=branch.id,
        request=request,
        metadata={"code": branch.code, "name": branch.name},
    )
    return branch