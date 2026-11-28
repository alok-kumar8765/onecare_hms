from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from core.models import BranchScopedModel, TimeStampedModel


class StaffEmploymentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ON_NOTICE = "ON_NOTICE", "On Notice"
    SUSPENDED = "SUSPENDED", "Suspended"
    EXITED = "EXITED", "Exited"


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    HALF_DAY = "HALF_DAY", "Half Day"
    ON_LEAVE = "ON_LEAVE", "On Leave"
    HOLIDAY = "HOLIDAY", "Holiday"


class LeaveType(models.TextChoices):
    CASUAL = "CASUAL", "Casual Leave"
    SICK = "SICK", "Sick Leave"
    EARNED = "EARNED", "Earned Leave"
    MATERNITY = "MATERNITY", "Maternity Leave"
    UNPAID = "UNPAID", "Unpaid Leave"


class LeaveRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class PayrollRunStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    FINALIZED = "FINALIZED", "Finalized"
    PAID = "PAID", "Paid"


class ShiftTemplate(BranchScopedModel):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_night_shift = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant_id", "code")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class StaffProfile(BranchScopedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hr_profiles",
    )
    employee_code = models.CharField(max_length=40, db_index=True)
    department_name = models.CharField(max_length=120, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    specialization = models.CharField(max_length=160, blank=True)
    qualification = models.CharField(max_length=200, blank=True)
    registration_number = models.CharField(max_length=80, blank=True)

    date_of_joining = models.DateField(default=timezone.localdate)
    date_of_exit = models.DateField(null=True, blank=True)

    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    hra_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    allowance_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deduction_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    employment_status = models.CharField(
        max_length=20,
        choices=StaffEmploymentStatus.choices,
        default=StaffEmploymentStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        ordering = ["employee_code"]
        unique_together = [("tenant_id", "employee_code")]

    def clean(self):
        if self.user_id and self.user.tenant_id != self.tenant_id:
            raise ValidationError(
                "Staff user must belong to the same tenant."
            )

        for field in (
            "base_salary",
            "hra_amount",
            "allowance_amount",
            "deduction_amount",
        ):
            if getattr(self, field) < Decimal("0.00"):
                raise ValidationError(f"{field} cannot be negative.")

    def __str__(self):
        return f"{self.employee_code} ({self.user.username})"


class DutyRoster(BranchScopedModel):
    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="rosters",
    )
    shift = models.ForeignKey(
        ShiftTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rosters",
    )
    roster_date = models.DateField(db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-roster_date"]
        unique_together = [("tenant_id", "staff", "roster_date")]


class AttendanceRecord(BranchScopedModel):
    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    attendance_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
        db_index=True,
    )
    check_in_at = models.DateTimeField(null=True, blank=True)
    check_out_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-attendance_date"]
        unique_together = [("tenant_id", "staff", "attendance_date")]


class LeaveRequest(BranchScopedModel):
    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    leave_type = models.CharField(
        max_length=20,
        choices=LeaveType.choices,
        default=LeaveType.CASUAL,
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=LeaveRequestStatus.choices,
        default=LeaveRequestStatus.PENDING,
        db_index=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_leave_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError(
                "Leave end date cannot be earlier than start date."
            )


class PayrollRun(BranchScopedModel):
    period_year = models.PositiveIntegerField(db_index=True)
    period_month = models.PositiveIntegerField(db_index=True)

    status = models.CharField(
        max_length=20,
        choices=PayrollRunStatus.choices,
        default=PayrollRunStatus.DRAFT,
        db_index=True,
    )

    total_gross = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_deductions = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_net = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_year", "-period_month"]
        unique_together = [
            ("tenant_id", "period_year", "period_month")
        ]


class PayslipEntry(TimeStampedModel):
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="payslips",
    )
    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="payslips",
    )

    gross_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    net_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        unique_together = [("payroll_run", "staff")]