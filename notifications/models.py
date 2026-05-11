from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Notification(TimeStampedModel):
    STATUS_UNREAD = 'unread'
    STATUS_READ = 'read'

    LEVEL_INFO = 'info'
    LEVEL_SUCCESS = 'success'
    LEVEL_WARNING = 'warning'
    LEVEL_DANGER = 'danger'

    STATUS_CHOICES = [
        (STATUS_UNREAD, 'Unread'),
        (STATUS_READ, 'Read'),
    ]

    LEVEL_CHOICES = [
        (LEVEL_INFO, 'Info'),
        (LEVEL_SUCCESS, 'Success'),
        (LEVEL_WARNING, 'Warning'),
        (LEVEL_DANGER, 'Danger'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=140)
    message = models.TextField()
    link = models.CharField(max_length=256, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNREAD)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    task_name = models.CharField(max_length=256, blank=True, default='')
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f'{self.title} for {self.user.login_id}'

    def mark_read(self):
        if self.status != self.STATUS_READ:
            self.status = self.STATUS_READ
            self.read_at = timezone.now()
            self.save(update_fields=['status', 'read_at'])
