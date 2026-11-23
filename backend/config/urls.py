from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path

from accounts.views import get_default_home_url_name


def home_view(request):
    if request.user.is_authenticated:
        return redirect(get_default_home_url_name(request.user))
    return redirect("accounts-login")


def api_health(request):
    return JsonResponse({
        "status": "ok",
        "service": "OneCare HMS",
        "api_version": "v1",
        "tenant_resolved": bool(getattr(request, "active_tenant_id", None)),
    })


urlpatterns = [
    path("", home_view, name="home"),
    path("admin/", admin.site.urls),
    path("api/v1/health/", api_health, name="api-v1-health"),
    path("api/v1/accounts/", include("accounts.api_urls")),
    path("api/v1/tenants/", include("tenants.api_urls")),
    path("api/v1/licensing/", include("licensing.api_urls")),
    path("api/v1/clinic/", include("clinic.api_urls")),
    path("api/v1/pharmacy/", include("pharmacy.api_urls")),
    path("api/v1/laboratory/", include("laboratory.api_urls")),
    path("api/v1/ipd/", include("ipd.api_urls")),
    path("accounts/", include("accounts.urls")),
    path("tenants/", include("tenants.urls")),
    path("licensing/", include("licensing.urls")),
    path("clinic/", include("clinic.urls")),
    path("pharmacy/", include("pharmacy.urls")),
    path("laboratory/", include("laboratory.urls")),
    path("ipd/", include("ipd.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)