from django.urls import path
from .views import super_admin_view, tenant_overview_view

urlpatterns = [
    path("overview/", tenant_overview_view, name="tenants-overview"),
    path("platform-admin/", super_admin_view, name="tenants-super-admin"),
]