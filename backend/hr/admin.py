from django.contrib import admin
from .models import (
    ShiftTemplate,
    StaffProfile,
    DutyRoster,
    AttendanceRecord,
    LeaveRequest,
    PayrollRun,
    PayslipEntry,
)


admin.site.register(ShiftTemplate)
admin.site.register(StaffProfile)
admin.site.register(DutyRoster)
admin.site.register(AttendanceRecord)
admin.site.register(LeaveRequest)
admin.site.register(PayrollRun)
admin.site.register(PayslipEntry)