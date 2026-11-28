from django.urls import path

from .views import (
    hr_dashboard_view,
    hr_health_view,
)

from .api import (
    StaffProfileListAPIView,
    ShiftTemplateListAPIView,
    DutyRosterListAPIView,
    AttendanceListCreateAPIView,
    LeaveRequestListCreateAPIView,
    LeaveReviewAPIView,
    PayrollRunListGenerateAPIView,
)


urlpatterns = [

    # HR Dashboard
    path(
        "dashboard/",
        hr_dashboard_view,
        name="hr-dashboard",
    ),

    # Health Check
    path(
        "health/",
        hr_health_view,
        name="hr-health",
    ),

    # Staff
    path(
        "api/staff/",
        StaffProfileListAPIView.as_view(),
        name="hr-staff-list",
    ),

    # Shifts
    path(
        "api/shifts/",
        ShiftTemplateListAPIView.as_view(),
        name="hr-shift-list",
    ),

    # Duty Roster
    path(
        "api/rosters/",
        DutyRosterListAPIView.as_view(),
        name="hr-roster-list",
    ),

    # Attendance
    path(
        "api/attendance/",
        AttendanceListCreateAPIView.as_view(),
        name="hr-attendance",
    ),

    # Leave Requests
    path(
        "api/leaves/",
        LeaveRequestListCreateAPIView.as_view(),
        name="hr-leave-list",
    ),

    # Leave Approval
    path(
        "api/leaves/<int:leave_request_id>/review/",
        LeaveReviewAPIView.as_view(),
        name="hr-leave-review",
    ),

    # Payroll
    path(
        "api/payroll/",
        PayrollRunListGenerateAPIView.as_view(),
        name="hr-payroll",
    ),
]