from rest_framework import serializers

from .models import (
    AttendanceRecord,
    DutyRoster,
    LeaveRequest,
    PayrollRun,
    ShiftTemplate,
    StaffProfile,
)


class ShiftTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftTemplate
        fields = "__all__"
        read_only_fields = ["id", "tenant_id"]


class StaffProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    class Meta:
        model = StaffProfile
        fields = "__all__"
        read_only_fields = ["id", "tenant_id"]


class DutyRosterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DutyRoster
        fields = "__all__"
        read_only_fields = ["id", "tenant_id"]


class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = "__all__"
        read_only_fields = ["id", "tenant_id"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = "__all__"
        read_only_fields = [
            "id",
            "tenant_id",
            "status",
            "reviewed_by",
            "reviewed_at",
        ]


class PayrollRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = "__all__"
        read_only_fields = [
            "id",
            "tenant_id",
            "status",
            "total_gross",
            "total_deductions",
            "total_net",
            "finalized_at",
        ]