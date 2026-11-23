from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.permissions import IsTenantAdminOrOwner
from .serializers import InstallationLicenseSerializer
from .services import activate_signed_license, get_or_start_installation_license


class LicenseStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]
    allow_in_restricted_mode = True

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant associated with user."}, status=status.HTTP_404_NOT_FOUND)
        lic = get_or_start_installation_license(tenant_id=tenant_id, request=request)
        return Response(InstallationLicenseSerializer(lic).data, status=status.HTTP_200_OK)


class LicenseActivateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsTenantAdminOrOwner]
    allow_in_restricted_mode = True

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        token = (request.data.get("signed_token") or "").strip()
        if not tenant_id:
            return Response({"detail": "No tenant associated with user."}, status=status.HTTP_404_NOT_FOUND)
        ok, message, lic = activate_signed_license(
            tenant_id=tenant_id,
            signed_token=token,
            actor=request.user,
            request=request,
        )
        if not ok:
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": message, "license": InstallationLicenseSerializer(lic).data}, status=status.HTTP_200_OK)