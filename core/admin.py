from django.contrib import admin

from .models import TaskLock
from .task_models import AsyncTask, TaskError


@admin.register(TaskLock)
class TaskLockAdmin(admin.ModelAdmin):
    list_display = ('name', 'acquired_at', 'expires_at')
    search_fields = ('name',)
    readonly_fields = ('acquired_at',)
    ordering = ('-acquired_at',)


@admin.register(AsyncTask)
class AsyncTaskAdmin(admin.ModelAdmin):
    list_display = ('task_type', 'status', 'enqueued_at', 'started_at', 'completed_at', 'retry_count')
    list_filter = ('status', 'task_type', 'enqueued_at')
    search_fields = ('task_type', 'celery_task_id', 'idempotency_key')
    readonly_fields = ('enqueued_at', 'started_at', 'completed_at', 'failed_at', 'input_data', 'result_data', 'error_traceback')
    fields = (
        'task_type',
        'status',
        'celery_task_id',
        'enqueued_at',
        'started_at',
        'completed_at',
        'failed_at',
        'retry_count',
        'max_retries',
        'idempotency_key',
        'user',
        'input_data',
        'result_data',
        'error_message',
        'error_traceback',
    )
    ordering = ('-enqueued_at',)


@admin.register(TaskError)
class TaskErrorAdmin(admin.ModelAdmin):
    list_display = ('async_task', 'severity', 'is_resolved', 'created_at')
    list_filter = ('severity', 'is_resolved', 'created_at')
    search_fields = ('message', 'exception_type', 'async_task__task_type')
    readonly_fields = ('created_at', 'resolved_at')
    fields = ('async_task', 'severity', 'message', 'exception_type', 'is_resolved', 'resolved_at')
    ordering = ('-created_at',)
    
    def mark_resolved(self, request, queryset):
        for error in queryset:
            error.mark_resolved()
    mark_resolved.short_description = 'Mark selected errors as resolved'
    
    actions = [mark_resolved]
