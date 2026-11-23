from rest_framework.permissions import BasePermission, SAFE_METHODS
from accounts.models import UserRole
from licensing.services import get_or_start_installation_license
from tenants.services import is_module_enabled


class IsPlatformSuperAdmin(BasePermission):
    """
    Restricts platform-wide administration strictly to authenticated SUPER_ADMIN users.
    """
    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "role", None) == UserRole.SUPER_ADMIN)


class IsTenantAdminOrOwner(BasePermission):
    """
    Allows Hospital Owner, Hospital Admin, or Platform Super Admin.
    """
    ALLOWED_ROLES = {UserRole.SUPER_ADMIN, UserRole.HOSPITAL_OWNER, UserRole.HOSPITAL_ADMIN}

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "role", None) in self.ALLOWED_ROLES)


class LicenseWriteAndModulePermission(BasePermission):
    """
    Enforces two core business rules:
    1. Module entitlement: if `required_module` is set on the view, the tenant must have it enabled.
    2. Patient-Data-Safe Restricted Mode: if the tenant's trial/license is expired/restricted,
       SAFE_METHODS (GET/HEAD/OPTIONS) and authorized exports remain allowed, while state-mutating
       operational writes are blocked until renewal.
    """
    message = "Operation blocked by module entitlement or expired license restricted mode."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "role", None) == UserRole.SUPER_ADMIN:
            return True

        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            return False

        required_module = getattr(view, "required_module", None)
        if required_module and not is_module_enabled(tenant_id, required_module):
            self.message = f"Module '{required_module}' is not enabled for your subscription."
            return False

        if request.method not in SAFE_METHODS and not getattr(view, "allow_in_restricted_mode", False):
            lic = get_or_start_installation_license(tenant_id=tenant_id, request=request)
            if not lic.is_write_allowed:
                self.message = (
                    "Subscription expired: account is in Patient-Data-Safe Restricted Mode. "
                    "Existing records and exports remain accessible; renew license to resume writes."
                )
                return False

        return True