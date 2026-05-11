from django.db import models
from django.conf import settings
from django.utils import timezone

from core.models import TimeStampedModel


class AsyncTask(TimeStampedModel):
    """Durable task tracking model for background job orchestration."""
    
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_RETRIED = 'retried'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_RETRIED, 'Retried'),
    ]
    
    task_type = models.CharField(max_length=128, db_index=True)
    celery_task_id = models.CharField(max_length=256, blank=True, unique=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    
    enqueued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    input_data = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)
    
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    
    idempotency_key = models.CharField(max_length=256, blank=True, unique=True, null=True, db_index=True)
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='async_tasks',
    )
    
    class Meta:
        ordering = ['-enqueued_at']
        verbose_name = 'Async Task'
        verbose_name_plural = 'Async Tasks'
        indexes = [
            models.Index(fields=['status', 'enqueued_at']),
            models.Index(fields=['task_type', 'status']),
        ]
    
    def __str__(self):
        return f'{self.task_type} ({self.status}) at {self.enqueued_at}'
    
    def mark_running(self, celery_task_id=None):
        self.status = self.STATUS_RUNNING
        self.started_at = timezone.now()
        if celery_task_id:
            self.celery_task_id = celery_task_id
        self.save(update_fields=['status', 'started_at', 'celery_task_id'])
    
    def mark_succeeded(self, result_data=None):
        self.status = self.STATUS_SUCCEEDED
        self.completed_at = timezone.now()
        if result_data:
            self.result_data = result_data
        self.save(update_fields=['status', 'completed_at', 'result_data'])
    
    def mark_failed(self, error_message, error_traceback=''):
        self.status = self.STATUS_FAILED
        self.failed_at = timezone.now()
        self.error_message = error_message
        self.error_traceback = error_traceback
        self.save(update_fields=['status', 'failed_at', 'error_message', 'error_traceback'])
    
    def should_retry(self):
        return self.status == self.STATUS_FAILED and self.retry_count < self.max_retries
    
    def mark_for_retry(self):
        self.status = self.STATUS_RETRIED
        self.retry_count += 1
        self.save(update_fields=['status', 'retry_count'])


class TaskError(TimeStampedModel):
    """Error registry for task failures and operator visibility."""
    
    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_ERROR = 'error'
    SEVERITY_CRITICAL = 'critical'
    
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, 'Info'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_ERROR, 'Error'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]
    
    async_task = models.ForeignKey(
        AsyncTask,
        on_delete=models.CASCADE,
        related_name='errors',
    )
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_ERROR)
    message = models.TextField()
    exception_type = models.CharField(max_length=128, blank=True)
    
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Task Error'
        verbose_name_plural = 'Task Errors'
    
    def __str__(self):
        return f'{self.async_task.task_type} error: {self.message[:50]}'
    
    def mark_resolved(self):
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.save(update_fields=['is_resolved', 'resolved_at'])
