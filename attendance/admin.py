from django.contrib import admin

from .models import AttendanceLog


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'person_type',
        'member',
        'staff',
        'check_in_time',
        'check_out_time',
        'source',
        'verification_mode',
        'status',
    )
    list_filter = ('person_type', 'status', 'source', 'verification_mode', 'date')
    search_fields = ('member__full_name', 'member__member_id', 'staff__full_name', 'staff__staff_id', 'device_id')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('member', 'staff')
