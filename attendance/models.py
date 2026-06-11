from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


from core.models import TimeStampedModel



class AttendanceLog(TimeStampedModel):
    PERSON_MEMBER = 'member'
    PERSON_STAFF = 'staff'


    PERSON_TYPE_CHOICES = [
        (PERSON_MEMBER, 'Member'),
        (PERSON_STAFF, 'Staff'),
    ]


    SOURCE_MANUAL = 'manual'
    SOURCE_DEVICE = 'device'


    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual'),
        (SOURCE_DEVICE, 'Device'),
    ]


    VERIFICATION_MANUAL = 'manual'
    VERIFICATION_BIOMETRIC = 'biometric'
    VERIFICATION_DEVICE = 'device'


    VERIFICATION_CHOICES = [
        (VERIFICATION_MANUAL, 'Manual'),
        (VERIFICATION_BIOMETRIC, 'Biometric'),
        (VERIFICATION_DEVICE, 'Device'),
    ]


    STATUS_PRESENT = 'present'
    STATUS_ABSENT = 'absent'
    STATUS_LATE = 'late'


    STATUS_CHOICES = [
        (STATUS_PRESENT, 'Present'),
        (STATUS_ABSENT, 'Absent'),
        (STATUS_LATE, 'Late'),
    ]


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
    person_type = models.CharField(max_length=12, choices=PERSON_TYPE_CHOICES, blank=True)
    date = models.DateField(default=timezone.localdate)
    check_in_time = models.DateTimeField(default=timezone.now)
    check_out_time = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    verification_mode = models.CharField(max_length=16, choices=VERIFICATION_CHOICES, default=VERIFICATION_MANUAL)
    device_id = models.CharField(max_length=64, blank=True)
    # device_user_id stores the PIN/UID reported by the biometric device
    # persisted here to aid debugging and mapping back to devices/users
    device_user_id = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    remarks = models.TextField(blank=True)


    class Meta:
        ordering = ['-date', '-check_in_time']
        verbose_name = 'Attendance Log'
        verbose_name_plural = 'Attendance Logs'


    def __str__(self):
        target = self.member.full_name if self.member else self.staff.full_name if self.staff else 'Unknown'
        return f'{target} — {self.date} ({self.get_person_type_display()})'


    @property
    def status_badge_class(self):
        return {
            self.STATUS_PRESENT: 'success',
            self.STATUS_LATE: 'warning',
            self.STATUS_ABSENT: 'secondary',
        }.get(self.status, 'secondary')


    def clean(self):
        has_member = bool(self.member)
        has_staff = bool(self.staff)
        if has_member == has_staff:
            raise ValidationError('Choose exactly one of member or staff for attendance.')
        if self.check_out_time and self.check_out_time < self.check_in_time:
            raise ValidationError('Check-out time cannot be earlier than check-in time.')
        if self.member:
            self.person_type = self.PERSON_MEMBER
        elif self.staff:
            self.person_type = self.PERSON_STAFF


    def save(self, *args, **kwargs):
        self.clean()
        if not self.date and self.check_in_time:
            self.date = self.check_in_time.date()
        super().save(*args, **kwargs)



class BiometricDevice(TimeStampedModel):
    TYPE_UNKNOWN = 'unknown'
    TYPE_MB20 = 'mb20'
    TYPE_AIFACE = 'aiface'


    DEVICE_TYPE_CHOICES = [
        (TYPE_UNKNOWN, 'Unknown'),
        (TYPE_MB20, 'MB20'),
        (TYPE_AIFACE, 'AiFace'),
    ]


    serial_number = models.CharField(max_length=64, unique=True)
    device_name = models.CharField(max_length=128, blank=True)
    device_type = models.CharField(max_length=32, choices=DEVICE_TYPE_CHOICES, default=TYPE_UNKNOWN)
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


    def __str__(self):
        return self.device_name or self.serial_number


    def identify_device_type(self):
        normalized_name = (self.device_name or self.serial_number or '').lower()
        if normalized_name.startswith('mb') or 'mb20' in normalized_name:
            return self.TYPE_MB20
        if 'aiface' in normalized_name or normalized_name.startswith('af'):
            return self.TYPE_AIFACE
        return self.TYPE_UNKNOWN


    def touch_heartbeat(self, payload, remote_ip=None):
        self.last_seen_at = timezone.localtime()
        self.last_payload = payload[:5000]
        if remote_ip:
            self.last_known_ip = remote_ip
        self.device_type = self.identify_device_type()
        if not self.device_name:
            self.device_name = self.serial_number
        self.save(update_fields=['last_seen_at', 'last_payload', 'last_known_ip', 'device_type', 'device_name'])



class BiometricSyncLog(TimeStampedModel):
    ACTION_DEVICE_HEARTBEAT = 'device_heartbeat'
    ACTION_ACCESS_ATTEMPT = 'access_attempt'
    ACTION_ENROLLMENT = 'enrollment'
    ACTION_DEVICE_SYNC = 'device_sync'
    ACTION_CONFLICT = 'conflict'


    ACTION_CHOICES = [
        (ACTION_DEVICE_HEARTBEAT, 'Device Heartbeat'),
        (ACTION_ACCESS_ATTEMPT, 'Access Attempt'),
        (ACTION_ENROLLMENT, 'Enrollment'),
        (ACTION_DEVICE_SYNC, 'Device Sync'),
        (ACTION_CONFLICT, 'Conflict'),
    ]


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
    person_type = models.CharField(max_length=12, choices=AttendanceLog.PERSON_TYPE_CHOICES, blank=True)
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    device_user_id = models.CharField(max_length=64, blank=True)
    success = models.BooleanField(default=True)
    payload = models.TextField(blank=True)
    response = models.TextField(blank=True)
    notes = models.TextField(blank=True)


    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Biometric Sync Log'
        verbose_name_plural = 'Biometric Sync Logs'


    def __str__(self):
        return f'{self.get_action_display()} for {self.device or "Unknown device"} at {self.created_at:%Y-%m-%d %H:%M:%S}'



class MemberBiometricDeviceStatus(TimeStampedModel):
    """
    Per-member-per-device biometric enrollment status.
    One row per (member, device) pair, so a member can have separate
    status for front gate and back gate devices.
    """

    SYNC_PENDING = 'pending'
    SYNC_SENT = 'sent'
    SYNC_SUCCESS = 'success'
    SYNC_FAILED = 'failed'


    SYNC_STATUS_CHOICES = [
        (SYNC_PENDING, 'Pending'),
        (SYNC_SENT, 'Sent to Device'),
        (SYNC_SUCCESS, 'Synced Successfully'),
        (SYNC_FAILED, 'Failed'),
    ]


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
    # Shared device_user_id for this member (from Member.device_user_id)
    device_user_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Device user ID (PIN/UID) for this member, copied from Member.device_user_id.",
    )
    is_enabled_on_device = models.BooleanField(
        default=False,
        help_text="Whether this member is currently enabled/active on this device.",
    )
    # Overall sync status
    sync_status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_PENDING,
        help_text="Overall biometric sync status for this member on this device.",
    )
    # Per-feature status
    face_added = models.BooleanField(
        default=False,
        help_text="Whether face data has been added to this device for this member.",
    )
    fingerprint_added = models.BooleanField(
        default=False,
        help_text="Whether fingerprint data has been added to this device for this member.",
    )
    password_added = models.BooleanField(
        default=False,
        help_text="Whether password has been added to this device for this member.",
    )
    # Timestamps
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this member was successfully synced to this device.",
    )
    last_status_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time we checked the device for this member's status.",
    )
    # Error handling
    last_error = models.TextField(
        blank=True,
        help_text="Last error message encountered when syncing or checking status.",
    )
    # Notes / debug info
    notes = models.TextField(
        blank=True,
        help_text="Optional notes or debug information about this sync.",
    )

    class Meta:
        ordering = ['device', 'member']
        unique_together = ('member', 'device')
        verbose_name = 'Member Biometric Device Status'
        verbose_name_plural = 'Member Biometric Device Statuses'


    def __str__(self):
        device_name = self.device.device_name or self.device.serial_number
        return f"{self.member.full_name} — {device_name} ({self.get_sync_status_display()})"


    def mark_sync_sent(self):
        """Mark that sync request has been sent to device."""
        self.sync_status = self.SYNC_SENT
        self.save(update_fields=['sync_status'])


    def mark_sync_success(self):
        """Mark that sync was successful on device."""
        self.sync_status = self.SYNC_SUCCESS
        self.is_enabled_on_device = True
        self.last_synced_at = timezone.now()
        self.last_error = ''
        self.save(update_fields=['sync_status', 'is_enabled_on_device', 'last_synced_at', 'last_error'])


    def mark_sync_failed(self, error_message: str):
        """Mark that sync failed on device."""
        self.sync_status = self.SYNC_FAILED
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
