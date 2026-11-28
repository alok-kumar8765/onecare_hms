from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import ModuleCode
from tenants.services import is_module_enabled

from .models import (
    AttendanceRecord,
    DutyRoster,
    LeaveRequest,
    PayrollRun,
    ShiftTemplate,
    StaffProfile,
)

from .serializers import (
    AttendanceRecordSerializer,
    DutyRosterSerializer,
    LeaveRequestSerializer,
    PayrollRunSerializer,
    ShiftTemplateSerializer,
    StaffProfileSerializer,
)

from .services import (
    can_manage_hr,
    generate_payroll_run,
    record_attendance,
    review_leave_request,
    submit_leave_request,
)


class HRModuleMixin:

    def get_tenant_id(self):
        tenant_id = (
            getattr(self.request, "active_tenant_id", None)
            or getattr(self.request.user, "tenant_id", None)
        )

        if not tenant_id:
            raise PermissionDenied("Tenant context is required.")

        if not is_module_enabled(tenant_id, ModuleCode.HR):
            raise PermissionDenied("HR module is disabled.")

        return tenant_id


class StaffProfileListAPIView(HRModuleMixin, generics.ListAPIView):
    serializer_class = StaffProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return StaffProfile.objects.filter(
            tenant_id=self.get_tenant_id()
        ).select_related("user")


class ShiftTemplateListAPIView(HRModuleMixin, generics.ListAPIView):
    serializer_class = ShiftTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ShiftTemplate.objects.filter(
            tenant_id=self.get_tenant_id()
        )


class DutyRosterListAPIView(HRModuleMixin, generics.ListAPIView):
    serializer_class = DutyRosterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DutyRoster.objects.filter(
            tenant_id=self.get_tenant_id()
        ).select_related("staff", "shift")


class AttendanceListCreateAPIView(
    HRModuleMixin,
    generics.ListCreateAPIView,
):
    serializer_class = AttendanceRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AttendanceRecord.objects.filter(
            tenant_id=self.get_tenant_id()
        )

    def perform_create(self, serializer):
        if not can_manage_hr(self.request.user):
            raise PermissionDenied("HR permission required.")

        try:
            record = record_attendance(
                tenant_id=self.get_tenant_id(),
                staff=serializer.validated_data["staff"],
                attendance_date=serializer.validated_data["attendance_date"],
                status=serializer.validated_data.get("status", "PRESENT"),
                branch_id=serializer.validated_data.get("branch_id"),
                remarks=serializer.validated_data.get("remarks", ""),
                actor=self.request.user,
                request=self.request,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        serializer.instance = record


class LeaveRequestListCreateAPIView(
    HRModuleMixin,
    generics.ListCreateAPIView,
):
    serializer_class = LeaveRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return LeaveRequest.objects.filter(
            tenant_id=self.get_tenant_id()
        ).select_related("staff")

    def perform_create(self, serializer):
        staff = serializer.validated_data["staff"]

        if staff.user_id != self.request.user.id:
            if not can_manage_hr(self.request.user):
                raise PermissionDenied("You can only request your own leave.")

        try:
            req = submit_leave_request(
                tenant_id=self.get_tenant_id(),
                staff=staff,
                start_date=serializer.validated_data["start_date"],
                end_date=serializer.validated_data["end_date"],
                leave_type=serializer.validated_data.get(
                    "leave_type", "CASUAL"
                ),
                reason=serializer.validated_data.get("reason", ""),
                actor=self.request.user,
                request=self.request,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        serializer.instance = req


class LeaveReviewAPIView(HRModuleMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, leave_request_id):
        if not can_manage_hr(request.user):
            raise PermissionDenied("HR permission required.")

        try:
            req = review_leave_request(
                tenant_id=self.get_tenant_id(),
                leave_request_id=leave_request_id,
                decision=request.data.get("decision", ""),
                reviewer=request.user,
                request=request,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            LeaveRequestSerializer(req).data,
            status=status.HTTP_200_OK,
        )


class PayrollRunListGenerateAPIView(
    HRModuleMixin,
    generics.ListCreateAPIView,
):
    serializer_class = PayrollRunSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PayrollRun.objects.filter(
            tenant_id=self.get_tenant_id()
        )

    def perform_create(self, serializer):
        if not can_manage_hr(self.request.user):
            raise PermissionDenied("HR permission required.")

        try:
            run = generate_payroll_run(
                tenant_id=self.get_tenant_id(),
                period_year=serializer.validated_data["period_year"],
                period_month=serializer.validated_data["period_month"],
                branch_id=serializer.validated_data.get("branch_id"),
                actor=self.request.user,
                request=self.request,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        serializer.instance = run