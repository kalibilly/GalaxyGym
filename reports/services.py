from django.db.models import Count, Q, Sum
from django.utils import timezone

from payments.models import Invoice, Payment
from members.models import Member
from notifications.models import Notification
from notifications.services import notify_owners
from .models import DailyFinancialReport


def build_daily_financial_report():
    today = timezone.localdate()
    this_month = today.replace(day=1)

    total_invoices = Invoice.objects.count()
    total_payments = Payment.objects.count()
    total_paid_amount = Payment.objects.filter(payment_date__gte=this_month).aggregate(total=Sum('amount_paid'))['total'] or 0
    pending_balance = Invoice.objects.filter(status__in=[Invoice.STATUS_UNPAID, Invoice.STATUS_PARTIAL]).aggregate(total=Sum('balance_amount'))['total'] or 0
    overdue_invoice_count = Invoice.objects.filter(status=Invoice.STATUS_OVERDUE).count()

    report, _ = DailyFinancialReport.objects.update_or_create(
        report_date=today,
        defaults={
            'total_invoices': total_invoices,
            'total_payments': total_payments,
            'total_paid_amount': total_paid_amount,
            'pending_balance': pending_balance,
            'overdue_invoice_count': overdue_invoice_count,
            'generated_at': timezone.now(),
        },
    )

    if overdue_invoice_count > 0:
        notify_owners(
            title='Overdue invoice review needed',
            message=f'{overdue_invoice_count} invoices are overdue and require attention.',
            level=Notification.LEVEL_WARNING,
            task_name='reports.build_daily_financial_report',
        )

    return report
