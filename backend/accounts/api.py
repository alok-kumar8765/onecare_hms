from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import UserDevice
from .serializers import UserDeviceSerializer, UserProfileSerializer
from .services import approve_user_device, evaluate_login_attempt, verify_totp_code


class LoginAPIView(APIView):
    """
    REST authentication endpoint for web/mobile clients with lockout,
    new-device alert detection, and TOTP 2FA verification.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        totp_code = (request.data.get("totp_code") or "").strip()
        ip = request.META.get("REMOTE_ADDR")
        ua = request.META.get("HTTP_USER_AGENT", "")

        result = evaluate_login_attempt(
            username=username,
            password=password,
            user_agent=ua,
            ip_address=ip,
            request=request,
        )
        if not result["ok"]:
            http_status = status.HTTP_423_LOCKED if result["status"] == "locked" else status.HTTP_401_UNAUTHORIZED
            return Response({"detail": result["message"], "status": result["status"]}, status=http_status)

        user = result["user"]
        if result["requires_2fa"]:
            if not totp_code:
                return Response(
                    {
                        "detail": "Two-factor authentication code required.",
                        "status": "2fa_required",
                        "new_device_alert": result["new_device_alert"],
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            if not verify_totp_code(user.totp_secret, totp_code):
                return Response({"detail": "Invalid two-factor code.", "status": "2fa_invalid"}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "status": "authenticated",
                "user": UserProfileSerializer(user, context={"request": request}).data,
                "new_device_alert": result["new_device_alert"],
            },
            status=status.HTTP_200_OK,
        )


class ProfileMeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class DevicesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserDevice.objects.filter(user=request.user, tenant_id=request.user.tenant_id)
        return Response(UserDeviceSerializer(qs, many=True).data, status=status.HTTP_200_OK)


class ApproveDeviceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, device_id):
        device = approve_user_device(user=request.user, device_id=device_id, request=request)
        if not device:
            return Response({"detail": "Device not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserDeviceSerializer(device).data, status=status.HTTP_200_OK)