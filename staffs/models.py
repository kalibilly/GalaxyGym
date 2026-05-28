from django.db import models
from django.utils import timezone

from core.models import ActiveStatusModel, TimeStampedModel, phone_regex


class Staff(TimeStampedModel, ActiveStatusModel):
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
        related_name='staff_profile',
    )
    staff_id = models.CharField(max_length=24, unique=True)
    device_user_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, validators=[phone_regex])
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    photo = models.ImageField(upload_to='staff_photos/', null=True, blank=True)
    department = models.ForeignKey(
        'departments.Department',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='staff_members',
    )
    designation = models.CharField(max_length=120, blank=True)
    date_of_joining = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['staff_id']
        verbose_name = 'Staff'
        verbose_name_plural = 'Staff'

    def __str__(self):
        return f'{self.staff_id} - {self.full_name}'
