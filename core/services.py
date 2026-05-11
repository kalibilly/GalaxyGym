from collections import OrderedDict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from attendance.models import AttendanceLog
from members.models import Member
from payments.models import Invoice, Payment

from .task_services import get_task_statistics, get_recent_failures


def acquire_task_lock(name, lease_seconds=1800):
    from .models import TaskLock

    class TaskLockContext:
        def __enter__(self):
            now = timezone.now()
            expires_at = now + timedelta(seconds=lease_seconds)
            with transaction.atomic():
                lock, created = TaskLock.objects.select_for_update().get_or_create(
                    name=name,
                    defaults={'expires_at': expires_at},
                )
                if not created and lock.expires_at > now:
                    raise RuntimeError(f'Task lock "{name}" is already held until {lock.expires_at}.')
                lock.expires_at = expires_at
                lock.save(update_fields=['expires_at'])
            return lock

        def __exit__(self, exc_type, exc, tb):
            with transaction.atomic():
                TaskLock.objects.filter(name=name).delete()

    return TaskLockContext()


def get_dashboard_metrics():
    today = timezone.localdate()
    this_month = today.replace(day=1)
    unpaid_invoices = Invoice.objects.filter(status__in=[Invoice.STATUS_UNPAID, Invoice.STATUS_PARTIAL])
    total_invoices = Invoice.objects.count()
    overdue_invoices = Invoice.objects.filter(status=Invoice.STATUS_OVERDUE).count()
    collected_this_month = Payment.objects.filter(payment_date__gte=this_month).aggregate(total=Sum('amount_paid'))['total'] or 0
    attendance_today = AttendanceLog.objects.filter(date=today).count()
    attendance_month = AttendanceLog.objects.filter(date__gte=this_month).count()

    top_members = (
        Member.objects.annotate(
            open_invoice_count=Count('invoices', filter=Q(invoices__status__in=[Invoice.STATUS_UNPAID, Invoice.STATUS_PARTIAL])),
            overdue_invoice_count=Count('invoices', filter=Q(invoices__status=Invoice.STATUS_OVERDUE)),
        )
        .filter(open_invoice_count__gt=0)
        .order_by('-open_invoice_count', '-overdue_invoice_count')[:5]
    )

    recent_attendance = (
        AttendanceLog.objects.select_related('member', 'staff')
        .order_by('-check_in_time')[:5]
    )
    
    task_stats = get_task_statistics(time_window_hours=24)
    recent_failures = list(get_recent_failures(limit=5))

    return OrderedDict([
        ('page_title', 'Dashboard'),
        ('today', today),
        ('unpaid_invoices_count', unpaid_invoices.count()),
        ('pending_balance', unpaid_invoices.aggregate(total=Sum('balance_amount'))['total'] or 0),
        ('collected_this_month', collected_this_month),
        ('attendance_today', attendance_today),
        ('attendance_month', attendance_month),
        ('total_invoices', total_invoices),
        ('overdue_invoices', overdue_invoices),
        ('top_members', top_members),
        ('recent_attendance', recent_attendance),
        ('task_stats', task_stats),
        ('recent_failures', recent_failures),
    ])
