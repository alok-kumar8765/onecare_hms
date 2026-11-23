from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.permissions import IsPlatformSuperAdmin, IsTenantAdminOrOwner, LicenseWriteAndModulePermission
from .models import Branch, DeploymentPreset, ModuleCode, ModuleEntitlement, Tenant
from .serializers import BranchSerializer, ModuleEntitlementSerializer, TenantSummarySerializer
from .services import create_tenant_branch, provision_tenant, set_tenant_module_state


class CurrentTenantAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant associated with user."}, status=status.HTTP_404_NOT_FOUND)
        tenant = Tenant.objects.prefetch_related("branches", "entitlements").filter(id=tenant_id).first()
        if not tenant:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TenantSummarySerializer(tenant).data, status=status.HTTP_200_OK)


class BranchListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response([], status=status.HTTP_200_OK)
        qs = Branch.objects.filter(tenant_id=tenant_id)
        return Response(BranchSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        if not IsTenantAdminOrOwner().has_permission(request, self):
            return Response({"detail": "Admin or Owner role required."}, status=status.HTTP_403_FORBIDDEN)
        tenant_id = getattr(request.user, "tenant_id", None)
        name = (request.data.get("name") or "").strip()
        code = (request.data.get("code") or "").strip()
        if not name or not code:
            return Response({"detail": "Branch name and code are required."}, status=status.HTTP_400_BAD_REQUEST)
        branch = create_tenant_branch(
            tenant_id=tenant_id,
            name=name,
            code=code,
            address=request.data.get("address") or "",
            phone_number=request.data.get("phone_number") or "",
            actor=request.user,
            request=request,
        )
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


class ModuleEntitlementListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response([], status=status.HTTP_200_OK)
        qs = ModuleEntitlement.objects.filter(tenant_id=tenant_id)
        return Response(ModuleEntitlementSerializer(qs, many=True).data, status=status.HTTP_200_OK)


class SuperAdminTenantProvisionAPIView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    def get(self, request):
        tenants = Tenant.objects.prefetch_related("branches", "entitlements").all().order_by("-created_at")
        return Response(TenantSummarySerializer(tenants, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        preset = request.data.get("deployment_preset") or DeploymentPreset.STANDALONE_CLINIC
        if not name:
            return Response({"detail": "Tenant name is required."}, status=status.HTTP_400_BAD_REQUEST)
        from .services import PRESET_MODULES
        modules = PRESET_MODULES.get(preset, PRESET_MODULES[DeploymentPreset.STANDALONE_CLINIC])
        tenant = provision_tenant(
            name=name,
            enabled_modules=list(modules),
            actor=request.user,
            request=request,
        )
        return Response(TenantSummarySerializer(tenant).data, status=status.HTTP_201_CREATED)


class SuperAdminModuleToggleAPIView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    def post(self, request, tenant_id):
        module_code = request.data.get("module_code")
        is_enabled = bool(request.data.get("is_enabled"))
        if module_code not in ModuleCode.values:
            return Response({"detail": "Invalid module_code."}, status=status.HTTP_400_BAD_REQUEST)
        ent = set_tenant_module_state(
            tenant_id=tenant_id,
            module_code=module_code,
            is_enabled=is_enabled,
            actor=request.user,
            request=request,
        )
        return Response(ModuleEntitlementSerializer(ent).data, status=status.HTTP_200_OK)