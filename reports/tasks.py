from celery import shared_task
from django.utils import timezone

from core.services import acquire_task_lock
from notifications.services import notify_owners, task_started, task_completed, task_failed
from .services import build_daily_financial_report


@shared_task(bind=True)
def build_daily_financial_report_task(self):
    task_name = 'reports.build_daily_financial_report'
    start_message = f'Report generation started at {timezone.localtime()}. The daily financial report is being built.'
    notify_owners(title='Daily report started', message=start_message, task_name=task_name)

    try:
        with acquire_task_lock(task_name, lease_seconds=3600):
            report = build_daily_financial_report()
        notify_owners(
            title='Daily report completed',
            message=f'Report for {report.report_date} has been generated.',
            task_name=task_name,
            level='success',
        )
        return {'report_date': str(report.report_date)}
    except Exception as exc:
        notify_owners(
            title='Daily report failed',
            message=str(exc),
            task_name=task_name,
            level='danger',
        )
        raise
