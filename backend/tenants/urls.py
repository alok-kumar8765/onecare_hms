from django.urls import path
from .views import reports_hub_view, setup_wizard_view, super_admin_view, tenant_overview_view

urlpatterns = [
    path("overview/", tenant_overview_view, name="tenants-overview"),
    path("platform-admin/", super_admin_view, name="tenants-super-admin"),
    path("setup-wizard/", setup_wizard_view, name="tenants-setup-wizard"),
    path("reports/", reports_hub_view, name="tenants-reports"),
]