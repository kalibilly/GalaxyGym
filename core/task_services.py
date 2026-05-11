import json
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .task_models import AsyncTask, TaskError


logger = logging.getLogger(__name__)


def create_async_task(task_type, input_data=None, idempotency_key=None, user=None, max_retries=3):
    """Create a durable task record before background execution."""
    if idempotency_key:
        existing = AsyncTask.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            logger.info(f'Task {task_type} already exists for key {idempotency_key}, returning existing')
            return existing
    
    task = AsyncTask.objects.create(
        task_type=task_type,
        input_data=input_data or {},
        idempotency_key=idempotency_key,
        user=user,
        max_retries=max_retries,
    )
    logger.info(f'Created async task {task.id}: {task_type}')
    return task


def mark_task_running(task_id, celery_task_id=None):
    """Mark task as running after Celery accepts it."""
    task = AsyncTask.objects.get(id=task_id)
    task.mark_running(celery_task_id)
    logger.info(f'Task {task.id} marked running (celery_id={celery_task_id})')


def mark_task_succeeded(task_id, result_data=None):
    """Mark task succeeded and log completion."""
    task = AsyncTask.objects.get(id=task_id)
    task.mark_succeeded(result_data)
    logger.info(f'Task {task.id} marked succeeded')


def mark_task_failed(task_id, error_message, error_traceback='', severity='error'):
    """Mark task failed, log error, and create error record."""
    with transaction.atomic():
        task = AsyncTask.objects.select_for_update().get(id=task_id)
        task.mark_failed(error_message, error_traceback)
        
        TaskError.objects.create(
            async_task=task,
            severity=severity,
            message=error_message,
            exception_type=error_message.split(':')[0] if ':' in error_message else 'Unknown',
        )
        logger.error(f'Task {task.id} marked failed: {error_message}')


def retry_task(task_id, celery_task_id=None):
    """Prepare task for retry if not exceeded max."""
    with transaction.atomic():
        task = AsyncTask.objects.select_for_update().get(id=task_id)
        if not task.should_retry():
            logger.warning(f'Task {task.id} cannot retry: retries exhausted')
            return False
        
        task.mark_for_retry()
        if celery_task_id:
            task.celery_task_id = celery_task_id
            task.save(update_fields=['celery_task_id'])
        logger.info(f'Task {task.id} marked for retry (attempt {task.retry_count})')
        return True


def get_task_statistics(time_window_hours=24):
    """Aggregate statistics for dashboard insight."""
    cutoff_time = timezone.now() - timedelta(hours=time_window_hours)
    
    total_tasks = AsyncTask.objects.filter(enqueued_at__gte=cutoff_time).count()
    succeeded_tasks = AsyncTask.objects.filter(status=AsyncTask.STATUS_SUCCEEDED, enqueued_at__gte=cutoff_time).count()
    failed_tasks = AsyncTask.objects.filter(status=AsyncTask.STATUS_FAILED, enqueued_at__gte=cutoff_time).count()
    running_tasks = AsyncTask.objects.filter(status=AsyncTask.STATUS_RUNNING, enqueued_at__gte=cutoff_time).count()
    pending_tasks = AsyncTask.objects.filter(status=AsyncTask.STATUS_PENDING, enqueued_at__gte=cutoff_time).count()
    
    success_rate = (succeeded_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    return {
        'total_tasks': total_tasks,
        'succeeded_tasks': succeeded_tasks,
        'failed_tasks': failed_tasks,
        'running_tasks': running_tasks,
        'pending_tasks': pending_tasks,
        'success_rate': round(success_rate, 2),
    }


def get_recent_failures(limit=10):
    """Get recent failed tasks for dashboard/admin visibility."""
    return TaskError.objects.filter(is_resolved=False).order_by('-created_at')[:limit]


def cleanup_old_tasks(days=30):
    """Delete successful tasks older than retention window."""
    cutoff_time = timezone.now() - timedelta(days=days)
    deleted_count, _ = AsyncTask.objects.filter(
        status=AsyncTask.STATUS_SUCCEEDED,
        completed_at__lt=cutoff_time,
    ).delete()
    logger.info(f'Cleaned up {deleted_count} old successful tasks')
    return deleted_count
