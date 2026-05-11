from django.db import models
from django.utils import timezone

from core.models import ActiveStatusModel, TimeStampedModel, phone_regex


class Member(TimeStampedModel, ActiveStatusModel):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_BLACKLISTED = 'blacklisted'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_BLACKLISTED, 'Blacklisted'),
    ]

    GENDER_MALE = 'male'
    GENDER_FEMALE = 'female'
    GENDER_OTHER = 'other'

    GENDER_CHOICES = [
        (GENDER_MALE, 'Male'),
        (GENDER_FEMALE, 'Female'),
        (GENDER_OTHER, 'Other'),
    ]

    user = models.OneToOneField(
        'accounts.UserAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='member_profile',
    )
    member_id = models.CharField(max_length=24, unique=True)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, validators=[phone_regex])
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    photo = models.ImageField(upload_to='member_photos/', null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[phone_regex],
    )
    assigned_staff = models.ForeignKey(
        'staffs.Staff',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_members',
    )
    address = models.TextField(blank=True)
    date_of_joining = models.DateField(default=timezone.now)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['member_id']
        verbose_name = 'Member'
        verbose_name_plural = 'Members'

    def __str__(self):
        return f'{self.member_id} - {self.full_name}'

    @property
    def active_membership(self):
        return self.memberships.filter(status='active').order_by('-end_date').first()
