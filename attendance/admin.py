from django.contrib import admin

from .models import AttendanceLog, BiometricDevice, BiometricSyncLog


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
        'device_id',
        'device_user_id',
    )
    list_filter = ('person_type', 'status', 'source', 'verification_mode', 'date')
    search_fields = ('member__full_name', 'member__member_id', 'staff__full_name', 'staff__staff_id', 'device_id', 'device_user_id')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('member', 'staff')


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'serial_number',
        'device_name',
        'device_type',
        'firmware_version',
        'is_active',
        'last_seen_at',
        'last_sync_at',
    )
    list_filter = ('device_type', 'is_active')
    search_fields = ('serial_number', 'device_name')
    readonly_fields = ('last_seen_at', 'last_sync_at')


@admin.register(BiometricSyncLog)
class BiometricSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'action',
        'device',
        'person_type',
        'member',
        'staff',
        'device_user_id',
        'success',
    )
    list_filter = ('action', 'success', 'person_type', 'device')
    search_fields = (
        'device__serial_number',
        'device__device_name',
        'member__member_id',
        'staff__staff_id',
        'device_user_id',
    )
    readonly_fields = ('created_at', 'updated_at')
