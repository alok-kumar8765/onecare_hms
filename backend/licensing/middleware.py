from __future__ import annotations
from typing import Optional
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from accounts.models import UserRole
from licensing.models import LicenseStatus
from licensing.services import get_or_start_installation_license


class LicenseEnforcementMiddleware:
    """
    Server-side license enforcement middleware.
    When a tenant's 7-day trial or 1-year license has expired (status is RESTRICTED or REVOKED):
    - Operational state-mutating API calls (POST, PUT, PATCH, DELETE) are blocked with HTTP 403.
    - Protected web routes are locked and redirected to the License Activation screen (/licensing/status/)
      except for license status/activation itself, login/logout, static, media, and platform super admin routes.
    """
    EXEMPT_URL_PREFIXES = (
        "/static/",
        "/media/",
        "/admin/",
        "/accounts/login/",
        "/accounts/logout/",
        "/licensing/",
        "/api/v1/licensing/",
        "/api/v1/health/",
        "/api/v1/accounts/login/",
        "/api/v1/accounts/logout/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        # Super Admin is exempt so they can manage the platform and activate licenses
        if getattr(user, "role", None) == UserRole.SUPER_ADMIN:
            return self.get_response(request)

        tenant_id = getattr(request, "active_tenant_id", None) or getattr(user, "tenant_id", None)
        if not tenant_id:
            return self.get_response(request)

        path = request.path_info or request.path

        # If path is explicitly exempt, allow through
        for prefix in self.EXEMPT_URL_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        lic = get_or_start_installation_license(tenant_id=tenant_id, request=request)
        if not lic.is_write_allowed:
            # License is expired or restricted
            if path.startswith("/api/"):
                # For APIs, block state-mutating requests (POST, PUT, PATCH, DELETE) with 403
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    return JsonResponse(
                        {
                            "detail": (
                                "Subscription expired: account is in Patient-Data-Safe Restricted Mode. "
                                "Operational writes are locked. Please activate a valid 1-year license key."
                            ),
                            "code": "LICENSE_RESTRICTED",
                            "installation_id": str(lic.installation_id),
                        },
                        status=403,
                    )
            else:
                # For Web routes, redirect to the license activation screen
                try:
                    status_url = reverse("licensing-status")
                except Exception:
                    status_url = "/licensing/status/"

                if path != status_url:
                    return redirect(f"{status_url}?expired=1")

        return self.get_response(request)
