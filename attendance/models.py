from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class AttendanceLog(TimeStampedModel):
    class PersonType(models.TextChoices):
        MEMBER = 'member', 'Member'
        STAFF = 'staff', 'Staff'

    class Source(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        DEVICE = 'device', 'Device'

    class VerificationMode(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        BIOMETRIC = 'biometric', 'Biometric'
        DEVICE = 'device', 'Device'

    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        LATE = 'late', 'Late'

    member = models.ForeignKey(
        'members.Member',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='attendance_logs',
    )
    staff = models.ForeignKey(
        'staffs.Staff',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='attendance_logs',
    )
    person_type = models.CharField(max_length=12, choices=PersonType.choices, blank=True)
    date = models.DateField(default=timezone.localdate)
    check_in_time = models.DateTimeField(default=timezone.now)
    check_out_time = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    verification_mode = models.CharField(
        max_length=16,
        choices=VerificationMode.choices,
        default=VerificationMode.MANUAL,
    )
    device = models.ForeignKey(
        'attendance.BiometricDevice',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='attendance_logs',
    )
    device_id = models.CharField(max_length=64, blank=True)
    device_user_id = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PRESENT)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-check_in_time']
        verbose_name = 'Attendance Log'
        verbose_name_plural = 'Attendance Logs'
        indexes = [
            models.Index(fields=['date', 'person_type']),
            models.Index(fields=['device_user_id', 'date']),
            models.Index(fields=['member', 'date']),
            models.Index(fields=['staff', 'date']),
        ]

    def __str__(self):
        target = self.member.full_name if self.member else self.staff.full_name if self.staff else 'Unknown'
        label = self.get_person_type_display() if self.person_type else 'Unknown'
        return f'{target} — {self.date} ({label})'

    @property
    def status_badge_class(self):
        return {
            self.Status.PRESENT: 'success',
            self.Status.LATE: 'warning',
            self.Status.ABSENT: 'secondary',
        }.get(self.status, 'secondary')

    def clean(self):
        has_member = bool(self.member)
        has_staff = bool(self.staff)

        if has_member == has_staff:
            raise ValidationError('Choose exactly one of member or staff for attendance.')

        if self.check_out_time and self.check_out_time < self.check_in_time:
            raise ValidationError('Check-out time cannot be earlier than check-in time.')

        if self.member:
            self.person_type = self.PersonType.MEMBER
        elif self.staff:
            self.person_type = self.PersonType.STAFF

        if self.device and not self.device_id:
            self.device_id = self.device.serial_number

        if not self.date and self.check_in_time:
            local_dt = timezone.localtime(self.check_in_time) if timezone.is_aware(self.check_in_time) else self.check_in_time
            self.date = local_dt.date()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BiometricDevice(TimeStampedModel):
    class DeviceType(models.TextChoices):
        UNKNOWN = 'unknown', 'Unknown'
        MB20 = 'mb20', 'MB20'
        AIFACE = 'aiface', 'AiFace'

    serial_number = models.CharField(max_length=64, unique=True)
    device_name = models.CharField(max_length=128, blank=True)
    device_type = models.CharField(max_length=32, choices=DeviceType.choices, default=DeviceType.UNKNOWN)
    firmware_version = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_known_ip = models.CharField(max_length=45, blank=True)
    last_payload = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Biometric Device'
        verbose_name_plural = 'Biometric Devices'
        ordering = ['device_name', 'serial_number']

    def __str__(self):
        return self.device_name or self.serial_number

    def identify_device_type(self):
        normalized_name = (self.device_name or self.serial_number or '').lower()
        if normalized_name.startswith('mb') or 'mb20' in normalized_name:
            return self.DeviceType.MB20
        if 'aiface' in normalized_name or normalized_name.startswith('af'):
            return self.DeviceType.AIFACE
        return self.DeviceType.UNKNOWN

    def touch_heartbeat(self, payload, remote_ip=None):
        self.last_seen_at = timezone.now()
        self.last_payload = (payload or '')[:5000]
        if remote_ip:
            self.last_known_ip = remote_ip
        self.device_type = self.identify_device_type()
        if not self.device_name:
            self.device_name = self.serial_number
        self.save(
            update_fields=[
                'last_seen_at',
                'last_payload',
                'last_known_ip',
                'device_type',
                'device_name',
            ]
        )


class BiometricSyncLog(TimeStampedModel):
    class Action(models.TextChoices):
        DEVICE_HEARTBEAT = 'device_heartbeat', 'Device Heartbeat'
        ACCESS_ATTEMPT = 'access_attempt', 'Access Attempt'
        ENROLLMENT = 'enrollment', 'Enrollment'
        DEVICE_SYNC = 'device_sync', 'Device Sync'
        CONFLICT = 'conflict', 'Conflict'
        COMMAND = 'command', 'Command'
        RAW_EVENT = 'raw_event', 'Raw Event'

    device = models.ForeignKey(
        BiometricDevice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sync_logs',
    )
    member = models.ForeignKey(
        'members.Member',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='biometric_sync_logs',
    )
    staff = models.ForeignKey(
        'staffs.Staff',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='biometric_sync_logs',
    )
    person_type = models.CharField(max_length=12, choices=AttendanceLog.PersonType.choices, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices)
    device_user_id = models.CharField(max_length=64, blank=True)
    success = models.BooleanField(default=True)
    payload = models.TextField(blank=True)
    response = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Biometric Sync Log'
        verbose_name_plural = 'Biometric Sync Logs'
        indexes = [
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['device_user_id', '-created_at']),
        ]

    def __str__(self):
        return f'{self.get_action_display()} for {self.device or "Unknown device"} at {self.created_at:%Y-%m-%d %H:%M:%S}'

    def clean(self):
        has_member = bool(self.member)
        has_staff = bool(self.staff)

        if has_member and has_staff:
            raise ValidationError('Sync log cannot reference both member and staff.')

        if self.member:
            self.person_type = AttendanceLog.PersonType.MEMBER
        elif self.staff:
            self.person_type = AttendanceLog.PersonType.STAFF

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DeviceUserLink(TimeStampedModel):
    class PersonType(models.TextChoices):
        MEMBER = 'member', 'Member'
        STAFF = 'staff', 'Staff'

    member = models.ForeignKey(
        'members.Member',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='device_links',
    )
    staff = models.ForeignKey(
        'staffs.Staff',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='device_links',
    )
    person_type = models.CharField(max_length=12, choices=PersonType.choices, blank=True)
    device_user_id = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['device_user_id']
        verbose_name = 'Device User Link'
        verbose_name_plural = 'Device User Links'
        constraints = [
            models.UniqueConstraint(fields=['device_user_id'], name='unique_device_user_link_device_user_id'),
            models.CheckConstraint(
                check=(
                    (models.Q(member__isnull=False) & models.Q(staff__isnull=True))
                    | (models.Q(member__isnull=True) & models.Q(staff__isnull=False))
                ),
                name='device_user_link_exactly_one_person',
            ),
        ]
        indexes = [
            models.Index(fields=['device_user_id', 'is_active']),
            models.Index(fields=['person_type', 'is_active']),
        ]

    def __str__(self):
        person = self.member or self.staff
        return f'{self.device_user_id} → {person}'

    def clean(self):
        has_member = bool(self.member)
        has_staff = bool(self.staff)

        if has_member == has_staff:
            raise ValidationError('Choose exactly one of member or staff for device user link.')

        if self.member:
            self.person_type = self.PersonType.MEMBER
            expected_id = self.member.device_user_id or self.member.member_id
        else:
            self.person_type = self.PersonType.STAFF
            expected_id = self.staff.device_user_id or self.staff.staff_id

        if not self.device_user_id:
            self.device_user_id = expected_id

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BiometricDeviceCommand(TimeStampedModel):
    class CommandType(models.TextChoices):
        SYNC_USER = 'sync_user', 'Sync User'
        DELETE_USER = 'delete_user', 'Delete User'
        ENABLE_USER = 'enable_user', 'Enable User'
        DISABLE_USER = 'disable_user', 'Disable User'
        REFRESH_USER = 'refresh_user', 'Refresh User'
        SYNC_FACE = 'sync_face', 'Sync Face'
        SYNC_FINGERPRINT = 'sync_fingerprint', 'Sync Fingerprint'
        SYNC_PASSWORD = 'sync_password', 'Sync Password'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.CASCADE,
        related_name='commands',
    )
    member = models.ForeignKey(
        'members.Member',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='biometric_commands',
    )
    staff = models.ForeignKey(
        'staffs.Staff',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='biometric_commands',
    )
    person_type = models.CharField(max_length=12, choices=AttendanceLog.PersonType.choices, blank=True)
    command = models.CharField(max_length=32, choices=CommandType.choices)
    device_user_id = models.CharField(max_length=64, blank=True)
    payload = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    queued_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    response_payload = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['status', 'queued_at']
        verbose_name = 'Biometric Device Command'
        verbose_name_plural = 'Biometric Device Commands'
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(member__isnull=False) & models.Q(staff__isnull=True))
                    | (models.Q(member__isnull=True) & models.Q(staff__isnull=False))
                ),
                name='biometric_command_exactly_one_person',
            ),
        ]
        indexes = [
            models.Index(fields=['device', 'status', 'queued_at']),
            models.Index(fields=['device_user_id', 'status']),
            models.Index(fields=['person_type', 'status']),
        ]

    def __str__(self):
        return f'{self.get_command_display()} for {self.device_user_id or self.member or self.staff} on {self.device}'

    def clean(self):
        has_member = bool(self.member)
        has_staff = bool(self.staff)

        if has_member == has_staff:
            raise ValidationError('Choose exactly one of member or staff for device command.')

        if self.member:
            self.person_type = AttendanceLog.PersonType.MEMBER
            expected_id = self.member.device_user_id or self.member.member_id
        else:
            self.person_type = AttendanceLog.PersonType.STAFF
            expected_id = self.staff.device_user_id or self.staff.staff_id

        if not self.device_user_id:
            self.device_user_id = expected_id

    def mark_sent(self, response_payload=''):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        if response_payload:
            self.response_payload = response_payload
        self.save(update_fields=['status', 'sent_at', 'response_payload'])

    def mark_acknowledged(self, response_payload=''):
        self.status = self.Status.ACKNOWLEDGED
        if response_payload:
            self.response_payload = response_payload
        self.save(update_fields=['status', 'response_payload'])

    def mark_success(self, response_payload=''):
        self.status = self.Status.SUCCESS
        self.processed_at = timezone.now()
        self.error_message = ''
        if response_payload:
            self.response_payload = response_payload
        self.save(update_fields=['status', 'processed_at', 'error_message', 'response_payload'])

    def mark_failed(self, error_message, response_payload=''):
        self.status = self.Status.FAILED
        self.processed_at = timezone.now()
        self.error_message = error_message
        if response_payload:
            self.response_payload = response_payload
        self.save(update_fields=['status', 'processed_at', 'error_message', 'response_payload'])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BiometricRawEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        HEARTBEAT = 'heartbeat', 'Heartbeat'
        ATTENDANCE = 'attendance', 'Attendance'
        COMMAND_POLL = 'command_poll', 'Command Poll'
        COMMAND_ACK = 'command_ack', 'Command Ack'
        USER_SNAPSHOT = 'user_snapshot', 'User Snapshot'
        UNKNOWN = 'unknown', 'Unknown'

    device = models.ForeignKey(
        BiometricDevice,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='raw_events',
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices, default=EventType.UNKNOWN)
    remote_ip = models.CharField(max_length=45, blank=True)
    device_user_id = models.CharField(max_length=64, blank=True)
    event_time = models.DateTimeField(default=timezone.now)
    payload = models.TextField(blank=True)
    parsed_ok = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-event_time', '-created_at']
        verbose_name = 'Biometric Raw Event'
        verbose_name_plural = 'Biometric Raw Events'
        indexes = [
            models.Index(fields=['event_type', '-event_time']),
            models.Index(fields=['device_user_id', '-event_time']),
        ]

    def __str__(self):
        return f'{self.get_event_type_display()} from {self.device or "Unknown device"} at {self.event_time:%Y-%m-%d %H:%M:%S}'


class MemberBiometricDeviceStatus(TimeStampedModel):
    class SyncStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent to Device'
        SUCCESS = 'success', 'Synced Successfully'
        FAILED = 'failed', 'Failed'

    member = models.ForeignKey(
        'members.Member',
        on_delete=models.CASCADE,
        related_name='device_statuses',
    )
    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.CASCADE,
        related_name='member_statuses',
    )
    device_user_id = models.CharField(
        max_length=64,
        blank=True,
        help_text='Device user ID (PIN/UID) for this member, copied from Member.device_user_id.',
    )
    is_enabled_on_device = models.BooleanField(
        default=False,
        help_text='Whether this member is currently enabled or active on this device.',
    )
    sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
        help_text='Overall biometric sync status for this member on this device.',
    )
    face_added = models.BooleanField(default=False)
    fingerprint_added = models.BooleanField(default=False)
    password_added = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_status_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['device', 'member']
        verbose_name = 'Member Biometric Device Status'
        verbose_name_plural = 'Member Biometric Device Statuses'
        constraints = [
            models.UniqueConstraint(fields=['member', 'device'], name='unique_member_biometric_device_status')
        ]
        indexes = [
            models.Index(fields=['device', 'sync_status']),
            models.Index(fields=['member', 'sync_status']),
        ]

    def __str__(self):
        device_name = self.device.device_name or self.device.serial_number
        return f'{self.member.full_name} — {device_name} ({self.get_sync_status_display()})'

    def clean(self):
        expected_id = self.member.device_user_id or self.member.member_id
        if not self.device_user_id:
            self.device_user_id = expected_id

    def mark_sync_sent(self):
        self.sync_status = self.SyncStatus.SENT
        self.last_error = ''
        self.save(update_fields=['sync_status', 'last_error'])

    def mark_sync_success(self):
        self.sync_status = self.SyncStatus.SUCCESS
        self.is_enabled_on_device = True
        self.last_synced_at = timezone.now()
        self.last_error = ''
        self.save(update_fields=['sync_status', 'is_enabled_on_device', 'last_synced_at', 'last_error'])

    def mark_sync_failed(self, error_message: str):
        self.sync_status = self.SyncStatus.FAILED
        self.is_enabled_on_device = False
        self.last_error = error_message
        self.save(update_fields=['sync_status', 'is_enabled_on_device', 'last_error'])

    def set_face_added(self, added: bool):
        self.face_added = added
        self.save(update_fields=['face_added'])

    def set_fingerprint_added(self, added: bool):
        self.fingerprint_added = added
        self.save(update_fields=['fingerprint_added'])

    def set_password_added(self, added: bool):
        self.password_added = added
        self.save(update_fields=['password_added'])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StaffBiometricDeviceStatus(TimeStampedModel):
    class SyncStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent to Device'
        SUCCESS = 'success', 'Synced Successfully'
        FAILED = 'failed', 'Failed'

    staff = models.ForeignKey(
        'staffs.Staff',
        on_delete=models.CASCADE,
        related_name='device_statuses',
    )
    device = models.ForeignKey(
        BiometricDevice,
        on_delete=models.CASCADE,
        related_name='staff_statuses',
    )
    device_user_id = models.CharField(
        max_length=64,
        blank=True,
        help_text='Device user ID (PIN/UID) for this staff member, copied from Staff.device_user_id.',
    )
    is_enabled_on_device = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    face_added = models.BooleanField(default=False)
    fingerprint_added = models.BooleanField(default=False)
    password_added = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_status_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['device', 'staff']
        verbose_name = 'Staff Biometric Device Status'
        verbose_name_plural = 'Staff Biometric Device Statuses'
        constraints = [
            models.UniqueConstraint(fields=['staff', 'device'], name='unique_staff_biometric_device_status')
        ]
        indexes = [
            models.Index(fields=['device', 'sync_status']),
            models.Index(fields=['staff', 'sync_status']),
        ]

    def __str__(self):
        device_name = self.device.device_name or self.device.serial_number
        return f'{self.staff.full_name} — {device_name} ({self.get_sync_status_display()})'

    def clean(self):
        expected_id = self.staff.device_user_id or self.staff.staff_id
        if not self.device_user_id:
            self.device_user_id = expected_id

    def mark_sync_sent(self):
        self.sync_status = self.SyncStatus.SENT
        self.last_error = ''
        self.save(update_fields=['sync_status', 'last_error'])

    def mark_sync_success(self):
        self.sync_status = self.SyncStatus.SUCCESS
        self.is_enabled_on_device = True
        self.last_synced_at = timezone.now()
        self.last_error = ''
        self.save(update_fields=['sync_status', 'is_enabled_on_device', 'last_synced_at', 'last_error'])

    def mark_sync_failed(self, error_message: str):
        self.sync_status = self.SyncStatus.FAILED
        self.is_enabled_on_device = False
        self.last_error = error_message
        self.save(update_fields=['sync_status', 'is_enabled_on_device', 'last_error'])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
