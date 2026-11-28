from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import UserRole
from core.audit import record_audit_log
from core.scoping import resolve_scoped_branch_id

from .models import (
    AttendanceRecord,
    AttendanceStatus,
    DutyRoster,
    LeaveRequest,
    LeaveRequestStatus,
    LeaveType,
    PayrollRun,
    PayrollRunStatus,
    PayslipEntry,
    ShiftTemplate,
    StaffEmploymentStatus,
    StaffProfile,
)

User = get_user_model()

HR_MANAGE_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.HOSPITAL_OWNER,
    UserRole.HOSPITAL_ADMIN,
    UserRole.BRANCH_MANAGER,
    UserRole.HR_MANAGER,
}


def _q2(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def can_manage_hr(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return getattr(user, "role", None) in HR_MANAGE_ROLES


@transaction.atomic
def create_or_update_staff_profile(
    *,
    tenant_id,
    user,
    employee_code=None,
    branch_id=None,
    department_name="",
    designation="",
    specialization="",
    qualification="",
    registration_number="",
    date_of_joining=None,
    base_salary=Decimal("0.00"),
    hra_amount=Decimal("0.00"),
    allowance_amount=Decimal("0.00"),
    deduction_amount=Decimal("0.00"),
    actor=None,
    request=None,
):
    if not tenant_id:
        raise ValueError("Tenant context is required.")

    if not user or user.tenant_id != tenant_id:
        raise ValueError("Staff user must belong to the same tenant.")

    scoped_branch = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id or user.primary_branch_id,
    )

    code = (
        employee_code or ""
    ).strip().upper() or f"EMP-{uuid.uuid4().hex[:6].upper()}"

    profile, created = StaffProfile.objects.update_or_create(
        tenant_id=tenant_id,
        employee_code=code,
        defaults={
            "user": user,
            "branch_id": scoped_branch,
            "department_name": department_name.strip(),
            "designation": designation.strip(),
            "specialization": specialization.strip(),
            "qualification": qualification.strip(),
            "registration_number": registration_number.strip(),
            "date_of_joining": date_of_joining or timezone.localdate(),
            "base_salary": _q2(base_salary),
            "hra_amount": _q2(hra_amount),
            "allowance_amount": _q2(allowance_amount),
            "deduction_amount": _q2(deduction_amount),
            "employment_status": StaffEmploymentStatus.ACTIVE,
        },
    )

    profile.full_clean()

    record_audit_log(
        action="hr.staff_profile.created" if created else "hr.staff_profile.updated",
        resource_type="StaffProfile",
        resource_id=profile.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=scoped_branch,
        request=request,
        metadata={"employee_code": profile.employee_code},
    )

    return profile


@transaction.atomic
def create_shift_template(
    *,
    tenant_id,
    name,
    code,
    start_time,
    end_time,
    is_night_shift=False,
    branch_id=None,
    actor=None,
    request=None,
):
    if not tenant_id:
        raise ValueError("Tenant context is required.")

    name = (name or "").strip()
    code = (code or "").strip().upper()

    if not name or not code:
        raise ValueError("Shift name and code are required.")

    scoped_branch = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id,
    )

    shift = ShiftTemplate.objects.create(
        tenant_id=tenant_id,
        branch_id=scoped_branch,
        name=name,
        code=code,
        start_time=start_time,
        end_time=end_time,
        is_night_shift=is_night_shift,
    )

    record_audit_log(
        action="hr.shift.created",
        resource_type="ShiftTemplate",
        resource_id=shift.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=scoped_branch,
        request=request,
        metadata={"code": code},
    )

    return shift


@transaction.atomic
def assign_duty_roster(
    *,
    tenant_id,
    staff,
    roster_date,
    shift=None,
    branch_id=None,
    notes="",
    actor=None,
    request=None,
):
    if not tenant_id or staff.tenant_id != tenant_id:
        raise ValueError("Staff profile must belong to active tenant.")

    if shift and shift.tenant_id != tenant_id:
        raise ValueError("Shift must belong to active tenant.")

    scoped_branch = resolve_scoped_branch_id(
        tenant_id=tenant_id,
        requested_branch_id=branch_id or staff.branch_id or (shift.branch_id if shift else None),
    )

    roster, _ = DutyRoster.objects.update_or_create(
        tenant_id=tenant_id,
        staff=staff,
        roster_date=roster_date,
        defaults={
            "shift": shift,
            "branch_id": scoped_branch,
            "notes": notes.strip(),
        },
    )

    record_audit_log(
        action="hr.roster.assigned",
        resource_type="DutyRoster",
        resource_id=roster.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=scoped_branch,
        request=request,
        metadata={"staff_id": str(staff.id)},
    )

    return roster


@transaction.atomic
def record_attendance(
    *,
    tenant_id,
    staff,
    attendance_date,
    status=AttendanceStatus.PRESENT,
    branch_id=None,
    remarks="",
    actor=None,
    request=None,
):
    if not tenant_id or staff.tenant_id != tenant_id:
        raise ValueError("Staff profile must belong to active tenant.")

    if status not in AttendanceStatus.values:
        raise ValueError("Invalid attendance status.")

    scoped_branch = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id or staff.branch_id,
    )

    record, _ = AttendanceRecord.objects.update_or_create(
        tenant_id=tenant_id,
        staff=staff,
        attendance_date=attendance_date,
        defaults={
            "branch_id": scoped_branch,
            "status": status,
            "check_in_at": (
                timezone.now()
                if status in (
                    AttendanceStatus.PRESENT,
                    AttendanceStatus.HALF_DAY,
                )
                else None
            ),
            "remarks": remarks.strip(),
        },
    )

    record_audit_log(
        action="hr.attendance.recorded",
        resource_type="AttendanceRecord",
        resource_id=record.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=scoped_branch,
        request=request,
        metadata={"status": status},
    )

    return record


@transaction.atomic
def submit_leave_request(
    *,
    tenant_id,
    staff,
    start_date,
    end_date,
    leave_type=LeaveType.CASUAL,
    reason="",
    actor=None,
    request=None,
):
    if not tenant_id or staff.tenant_id != tenant_id:
        raise ValueError("Staff profile must belong to active tenant.")

    if end_date < start_date:
        raise ValueError("Invalid leave date range.")

    if leave_type not in LeaveType.values:
        raise ValueError("Invalid leave type.")

    req = LeaveRequest.objects.create(
        tenant_id=tenant_id,
        branch_id=staff.branch_id,
        staff=staff,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip(),
        status=LeaveRequestStatus.PENDING,
    )

    record_audit_log(
        action="hr.leave.requested",
        resource_type="LeaveRequest",
        resource_id=req.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=req.branch_id,
        request=request,
        metadata={"staff_id": str(staff.id)},
    )

    return req


@transaction.atomic
def review_leave_request(
    *,
    tenant_id,
    leave_request_id,
    decision,
    reviewer,
    request=None,
):
    req = LeaveRequest.objects.select_for_update().filter(
        id=leave_request_id,
        tenant_id=tenant_id,
    ).first()

    if not req:
        raise ValueError("Leave request not found in your organization.")

    if req.status != LeaveRequestStatus.PENDING:
        raise ValueError("Only pending requests can be reviewed.")

    decision = (decision or "").strip().upper()

    if decision not in (
        LeaveRequestStatus.APPROVED,
        LeaveRequestStatus.REJECTED,
    ):
        raise ValueError("Invalid leave decision.")

    req.status = decision
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()

    req.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    if decision == LeaveRequestStatus.APPROVED:
        current = req.start_date

        while current <= req.end_date:
            AttendanceRecord.objects.update_or_create(
                tenant_id=tenant_id,
                staff=req.staff,
                attendance_date=current,
                defaults={
                    "branch_id": req.branch_id,
                    "status": AttendanceStatus.ON_LEAVE,
                    "remarks": f"Approved {req.leave_type} leave",
                },
            )
            current += timedelta(days=1)

    record_audit_log(
        action="hr.leave.reviewed",
        resource_type="LeaveRequest",
        resource_id=req.id,
        actor=reviewer,
        tenant_id=tenant_id,
        branch_id=req.branch_id,
        request=request,
        metadata={"decision": decision},
    )

    return req


@transaction.atomic
def generate_payroll_run(
    *,
    tenant_id,
    period_year,
    period_month,
    branch_id=None,
    actor=None,
    request=None,
):
    if not tenant_id:
        raise ValueError("Tenant context is required.")

    if period_month < 1 or period_month > 12:
        raise ValueError("Invalid payroll month.")

    scoped_branch = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id,
    )

    run, _ = PayrollRun.objects.get_or_create(
        tenant_id=tenant_id,
        period_year=period_year,
        period_month=period_month,
        defaults={
            "branch_id": scoped_branch,
            "status": PayrollRunStatus.DRAFT,
        },
    )

    if run.status != PayrollRunStatus.DRAFT:
        raise ValueError("Cannot regenerate finalized payroll.")

    run.payslips.all().delete()

    staff_qs = StaffProfile.objects.filter(
        tenant_id=tenant_id,
        employment_status=StaffEmploymentStatus.ACTIVE,
    )

    if scoped_branch:
        staff_qs = staff_qs.filter(branch_id=scoped_branch)

    gross_sum = Decimal("0.00")
    deduction_sum = Decimal("0.00")
    net_sum = Decimal("0.00")

    for profile in staff_qs:
        gross = _q2(
            profile.base_salary
            + profile.hra_amount
            + profile.allowance_amount
        )

        deductions = _q2(profile.deduction_amount)
        net = _q2(max(Decimal("0.00"), gross - deductions))

        PayslipEntry.objects.create(
            payroll_run=run,
            staff=profile,
            gross_pay=gross,
            deductions=deductions,
            net_pay=net,
        )

        gross_sum += gross
        deduction_sum += deductions
        net_sum += net

    run.total_gross = _q2(gross_sum)
    run.total_deductions = _q2(deduction_sum)
    run.total_net = _q2(net_sum)

    run.save(
        update_fields=[
            "total_gross",
            "total_deductions",
            "total_net",
            "updated_at",
        ]
    )

    record_audit_log(
        action="hr.payroll.generated",
        resource_type="PayrollRun",
        resource_id=run.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=scoped_branch,
        request=request,
        metadata={
            "year": period_year,
            "month": period_month,
            "total_net": str(run.total_net),
        },
    )

    return run