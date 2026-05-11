from django.db import models

from core.models import ActiveStatusModel, TimeStampedModel, phone_regex


class Department(TimeStampedModel, ActiveStatusModel):
    name = models.CharField(max_length=120, unique=True)
    speciality = models.CharField(max_length=150, blank=True)
    head_name = models.CharField(max_length=150, blank=True)
    head_phone_number = models.CharField(
        max_length=20,
        blank=True,
        validators=[phone_regex],
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'

    def __str__(self):
        return self.name

    @property
    def number_of_staff(self):
        return self.staff_members.filter(is_active=True).count()
