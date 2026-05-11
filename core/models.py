from django.core.validators import RegexValidator
from django.db import models

phone_regex = RegexValidator(
    regex=r'^\+?\d{7,15}$',
    message='Phone number must be entered in the format: +999999999. Up to 15 digits allowed.',
)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActiveStatusModel(models.Model):
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class TaskLock(models.Model):
    name = models.CharField(max_length=128, unique=True)
    acquired_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = 'Task Lock'
        verbose_name_plural = 'Task Locks'

    def __str__(self):
        return f'Lock {self.name} until {self.expires_at}'
