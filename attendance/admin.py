from django.contrib import admin

from .models import (
    AttendanceLog,
    BiometricDevice,
    BiometricSyncLog,
    MemberBiometricDeviceStatus,
)


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'person_type',
        'member',
        'staff',
        'date',
        'check_in_time',
        'check_out_time',
        'source',
        'verification_mode',
        'device_id',
        'device_user_id',
        'status',
    )
    list_filter = (
        'person_type',
        'source',
        'verification_mode',
        'status',
        'date',
    )
    search_fields = (
        'member__full_name',
        'member__member_id',
        'member__device_user_id',
        'staff__full_name',
        'device_id',
        'device_user_id',
        'remarks',
    )
    autocomplete_fields = ('member', 'staff')
    date_hierarchy = 'date'


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'device_name',
        'serial_number',
        'device_type',
        'firmware_version',
        'is_active',
        'last_seen_at',
        'last_sync_at',
        'last_known_ip',
    )
    list_filter = (
        'device_type',
        'is_active',
    )
    search_fields = (
        'device_name',
        'serial_number',
        'firmware_version',
        'last_known_ip',
        'notes',
    )


@admin.register(BiometricSyncLog)
class BiometricSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'created_at',
        'action',
        'device',
        'member',
        'staff',
        'person_type',
        'device_user_id',
        'success',
    )
    list_filter = (
        'action',
        'success',
        'person_type',
        'created_at',
    )
    search_fields = (
        'device__device_name',
        'device__serial_number',
        'member__full_name',
        'member__member_id',
        'staff__full_name',
        'device_user_id',
        'payload',
        'response',
        'notes',
    )
    autocomplete_fields = ('device', 'member', 'staff')
    date_hierarchy = 'created_at'


@admin.register(MemberBiometricDeviceStatus)
class MemberBiometricDeviceStatusAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'member',
        'device',
        'device_user_id',
        'sync_status',
        'is_enabled_on_device',
        'face_added',
        'fingerprint_added',
        'password_added',
        'last_synced_at',
        'last_status_checked_at',
        'created_at',
        'updated_at',
    )
    list_filter = (
        'sync_status',
        'is_enabled_on_device',
        'face_added',
        'fingerprint_added',
        'password_added',
        'device',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'member__full_name',
        'member__member_id',
        'member__device_user_id',
        'device__device_name',
        'device__serial_number',
        'device_user_id',
        'last_error',
        'notes',
    )
    autocomplete_fields = ('member', 'device')
    readonly_fields = (
        'created_at',
        'updated_at',
        'last_synced_at',
        'last_status_checked_at',
    )