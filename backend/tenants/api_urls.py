from django.urls import path
from .api import (
    BranchListCreateAPIView,
    CurrentTenantAPIView,
    ModuleEntitlementListAPIView,
    SuperAdminModuleToggleAPIView,
    SuperAdminTenantProvisionAPIView,
)

urlpatterns = [
    path("current/", CurrentTenantAPIView.as_view(), name="api-tenants-current"),
    path("branches/", BranchListCreateAPIView.as_view(), name="api-tenants-branches"),
    path("modules/", ModuleEntitlementListAPIView.as_view(), name="api-tenants-modules"),
    path("platform/tenants/", SuperAdminTenantProvisionAPIView.as_view(), name="api-platform-tenants"),
    path("platform/tenants/<uuid:tenant_id>/modules/", SuperAdminModuleToggleAPIView.as_view(), name="api-platform-tenant-modules"),
]