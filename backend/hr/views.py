from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from tenants.models import ModuleCode
from tenants.services import is_module_enabled

from .models import (
    AttendanceRecord,
    AttendanceStatus,
    DutyRoster,
    LeaveRequest,
    LeaveType,
    PayrollRun,
    ShiftTemplate,
    StaffProfile,
)

from .services import can_manage_hr

User = get_user_model()


@login_required
def hr_dashboard_view(request):

    tenant_id = (
        getattr(request, "active_tenant_id", None)
        or getattr(request.user, "tenant_id", None)
    )

    if not tenant_id:
        return render(
            request,
            "hr/dashboard.html",
            {"error": "No tenant context found."},
        )

    if not is_module_enabled(tenant_id, ModuleCode.HR):
        return render(
            request,
            "clinic/module_disabled.html",
            {"module_name": "HR & Staff Management"},
        )

    context = {
        "staff_profiles": StaffProfile.objects.filter(
            tenant_id=tenant_id
        ).select_related("user")[:50],

        "shifts": ShiftTemplate.objects.filter(
            tenant_id=tenant_id
        )[:30],

        "rosters": DutyRoster.objects.filter(
            tenant_id=tenant_id
        ).select_related("staff", "shift")[:40],

        "attendance_records": AttendanceRecord.objects.filter(
            tenant_id=tenant_id
        ).select_related("staff")[:40],

        "leave_requests": LeaveRequest.objects.filter(
            tenant_id=tenant_id
        ).select_related("staff")[:40],

        "payroll_runs": PayrollRun.objects.filter(
            tenant_id=tenant_id
        )[:24],

        "tenant_users": User.objects.filter(
            tenant_id=tenant_id
        ).order_by("username")[:50],

        "leave_types": LeaveType.choices,
        "attendance_statuses": AttendanceStatus.choices,

        "can_manage_hr": can_manage_hr(request.user),
    }

    return render(
        request,
        "hr/dashboard.html",
        context,
    )


@login_required
def hr_health_view(request):

    tenant_id = (
        getattr(request, "active_tenant_id", None)
        or getattr(request.user, "tenant_id", None)
    )

    if not tenant_id:
        return JsonResponse(
            {"detail": "No tenant context found."},
            status=403,
        )

    return JsonResponse({
        "status": "ok",
        "module": "hr",
        "tenant_id": str(tenant_id),
    })