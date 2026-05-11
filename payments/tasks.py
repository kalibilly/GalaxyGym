from celery import shared_task
from django.utils import timezone

from accounts.models import UserAccount
from notifications.services import notify_owners
from .models import Invoice, Payment


@shared_task(bind=True)
def process_payment_notifications(self, payment_pk, actor_pk=None):
    task_name = 'payments.process_payment_notifications'
    start_message = f'Payment processing started for payment #{payment_pk} at {timezone.localtime()}.'
    notify_owners(title='Payment processing started', message=start_message, task_name=task_name)

    try:
        payment = Payment.objects.select_related('invoice', 'member').get(pk=payment_pk)
        invoice = payment.invoice
        invoice.refresh_balance()
        message = (
            f'Payment of {payment.amount_paid} recorded for invoice {invoice.invoice_no}. '
            f'Invoice status is now {invoice.status}.'
        )
        notify_owners(title='Payment processed', message=message, task_name=task_name, level='success')
        return {'invoice': invoice.invoice_no, 'status': invoice.status}
    except Payment.DoesNotExist as exc:
        notify_owners(title='Payment processing failed', message=str(exc), task_name=task_name, level='danger')
        raise


@shared_task(bind=True)
def send_overdue_invoice_notifications_task(self):
    task_name = 'payments.send_overdue_invoice_notifications'
    start_message = f'Overdue invoice notification task started at {timezone.localtime()}.'
    notify_owners(title='Overdue invoice scan started', message=start_message, task_name=task_name)

    overdue_invoices = Invoice.objects.filter(status=Invoice.STATUS_OVERDUE)
    overdue_count = overdue_invoices.count()
    if overdue_count == 0:
        notify_owners(title='Overdue invoice scan completed', message='No overdue invoices found.', task_name=task_name, level='info')
        return {'overdue_count': 0}

    notify_owners(
        title='Overdue invoices found',
        message=f'{overdue_count} overdue invoices were identified. Please review overdue accounts.',
        task_name=task_name,
        level='warning',
    )
    return {'overdue_count': overdue_count}
