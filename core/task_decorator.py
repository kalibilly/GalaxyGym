from functools import wraps
import traceback

from django.utils import timezone

from core.task_services import (
    create_async_task,
    mark_task_running,
    mark_task_succeeded,
    mark_task_failed,
    retry_task,
)


def tracked_task(task_type, max_retries=3, idempotency_key_fn=None):
    """
    Decorator for Celery tasks that automatically tracks task lifecycle.
    
    Usage:
        @tracked_task('my_task', max_retries=3, idempotency_key_fn=lambda args: f"key_{args[0]}")
        @shared_task(bind=True)
        def my_background_job(self, arg1, arg2):
            return {'result': 'success'}
    """
    def decorator(celery_task):
        @wraps(celery_task)
        def wrapper(self, async_task_id, *args, **kwargs):
            from core.task_models import AsyncTask
            
            try:
                task_record = AsyncTask.objects.get(id=async_task_id)
                mark_task_running(async_task_id, self.request.id)
                
                result = celery_task(self, *args, **kwargs)
                
                mark_task_succeeded(async_task_id, result_data=result)
                return result
            except Exception as exc:
                error_msg = str(exc)
                error_tb = traceback.format_exc()
                mark_task_failed(async_task_id, error_msg, error_tb, severity='error')
                
                if retry_task(async_task_id, self.request.id):
                    raise self.retry(countdown=60, max_retries=max_retries)
                raise
        
        return wrapper
    return decorator


def enqueue_tracked_task(celery_task_func, task_type, input_data=None, idempotency_key=None, user=None, max_retries=3):
    """
    Create an AsyncTask record and enqueue it to Celery.
    
    Returns the AsyncTask instance.
    """
    task_record = create_async_task(
        task_type=task_type,
        input_data=input_data,
        idempotency_key=idempotency_key,
        user=user,
        max_retries=max_retries,
    )
    
    celery_task_func.delay(task_record.id)
    
    return task_record
