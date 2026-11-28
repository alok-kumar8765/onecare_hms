from datetime import date
from decimal import Decimal

import pytest

from accounts.models import User, UserRole

from hr.models import (
    AttendanceRecord,
    AttendanceStatus,
    LeaveRequestStatus,
    LeaveType,
)

from hr.services import (
    assign_duty_roster,
    create_or_update_staff_profile,
    generate_payroll_run,
    record_attendance,
    review_leave_request,
    submit_leave_request,
)

from tenants.models import ModuleCode
from tenants.services import (
    provision_tenant,
    set_tenant_module_state,
)


@pytest.mark.django_db
def test_hr_staff_roster_leave_and_payroll_workflow():

    tenant = provision_tenant(
        name="CarePlus Hospital",
        slug="careplus-hospital",
    )

    set_tenant_module_state(
        tenant_id=tenant.id,
        module_code=ModuleCode.HR,
        is_enabled=True,
    )

    hr_admin = User.objects.create_user(
        username="hr_lead",
        password="StrongPassword123!",
        role=UserRole.HR_MANAGER,
        tenant_id=tenant.id,
    )

    nurse_user = User.objects.create_user(
        username="nurse_anita",
        password="StrongPassword123!",
        role=UserRole.NURSE,
        tenant_id=tenant.id,
    )

    profile = create_or_update_staff_profile(
        tenant_id=tenant.id,
        user=nurse_user,
        employee_code="EMP-001",
        department_name="ICU",
        designation="Senior Nurse",
        base_salary=Decimal("30000.00"),
        hra_amount=Decimal("6000.00"),
        allowance_amount=Decimal("2000.00"),
        deduction_amount=Decimal("3000.00"),
        actor=hr_admin,
    )

    assert profile.employee_code == "EMP-001"

    d1 = date(2026, 12, 1)
    d2 = date(2026, 12, 2)

    roster = assign_duty_roster(
        tenant_id=tenant.id,
        staff=profile,
        roster_date=d1,
        actor=hr_admin,
    )

    assert roster.staff == profile

    record_attendance(
        tenant_id=tenant.id,
        staff=profile,
        attendance_date=d1,
        status=AttendanceStatus.PRESENT,
        actor=hr_admin,
    )

    assert AttendanceRecord.objects.filter(
        tenant_id=tenant.id,
        staff=profile,
        attendance_date=d1,
        status=AttendanceStatus.PRESENT,
    ).exists()

    leave_req = submit_leave_request(
        tenant_id=tenant.id,
        staff=profile,
        start_date=d2,
        end_date=d2,
        leave_type=LeaveType.SICK,
        reason="Fever",
        actor=nurse_user,
    )

    approved = review_leave_request(
        tenant_id=tenant.id,
        leave_request_id=leave_req.id,
        decision=LeaveRequestStatus.APPROVED,
        reviewer=hr_admin,
    )

    assert approved.status == LeaveRequestStatus.APPROVED

    assert AttendanceRecord.objects.filter(
        tenant_id=tenant.id,
        staff=profile,
        attendance_date=d2,
        status=AttendanceStatus.ON_LEAVE,
    ).exists()

    payroll = generate_payroll_run(
        tenant_id=tenant.id,
        period_year=2026,
        period_month=12,
        actor=hr_admin,
    )

    assert payroll.total_gross == Decimal("38000.00")
    assert payroll.total_deductions == Decimal("3000.00")
    assert payroll.total_net == Decimal("35000.00")


@pytest.mark.django_db
def test_hr_cross_tenant_leave_review_rejected():

    tenant_a = provision_tenant(
        name="Alpha Clinic",
        slug="alpha-clinic",
    )

    tenant_b = provision_tenant(
        name="Beta Clinic",
        slug="beta-clinic",
    )

    set_tenant_module_state(
        tenant_id=tenant_a.id,
        module_code=ModuleCode.HR,
        is_enabled=True,
    )

    set_tenant_module_state(
        tenant_id=tenant_b.id,
        module_code=ModuleCode.HR,
        is_enabled=True,
    )

    user_a = User.objects.create_user(
        username="staff_a",
        password="StrongPassword123!",
        tenant_id=tenant_a.id,
    )

    hr_b = User.objects.create_user(
        username="hr_b",
        password="StrongPassword123!",
        role=UserRole.HR_MANAGER,
        tenant_id=tenant_b.id,
    )

    profile_a = create_or_update_staff_profile(
        tenant_id=tenant_a.id,
        user=user_a,
        employee_code="A-101",
    )

    leave_a = submit_leave_request(
        tenant_id=tenant_a.id,
        staff=profile_a,
        start_date=date(2026, 12, 5),
        end_date=date(2026, 12, 5),
    )

    with pytest.raises(
        ValueError,
        match="not found in your organization",
    ):
        review_leave_request(
            tenant_id=tenant_b.id,
            leave_request_id=leave_a.id,
            decision=LeaveRequestStatus.APPROVED,
            reviewer=hr_b,
        )