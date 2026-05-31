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
    serial_number = models.CharField(max_length=64, unique=True)
    device_name = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_payload = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Biometric Device'
        verbose_name_plural = 'Biometric Devices'

    def __str__(self):
        return self.device_name or self.serial_number
