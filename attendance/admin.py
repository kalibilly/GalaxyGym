from django.contrib import admin

from .models import AttendanceLog, BiometricDevice


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


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'device_name', 'is_active', 'last_seen_at')
    search_fields = ('serial_number', 'device_name')
    readonly_fields = ('last_seen_at',)
