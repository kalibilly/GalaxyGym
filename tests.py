import pytest
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.test import TestCase

from accounts.models import UserAccount
from members.models import Member
from payments.models import Invoice, Payment
from attendance.models import AttendanceLog
from notifications.models import Notification
from reports.models import DailyFinancialReport
from core.services import get_dashboard_metrics


@pytest.mark.django_db
class TestDashboardMetrics(TestCase):
    fixtures = []

    def setUp(self):
        self.user = UserAccount.objects.create_user(
            login_id='testowner',
            password='testpass123',
            role='owner',
            is_staff=True,
        )
        self.member = Member.objects.create(
            full_name='Test Member',
            member_id='MEM001',
            email='member@test.com',
            phone_number='9876543210',
        )

    def test_dashboard_metrics_aggregate_queries(self):
        today = timezone.localdate()
        this_month = today.replace(day=1)

        Invoice.objects.create(
            invoice_no='INV001',
            member=self.member,
            invoice_date=today,
            due_date=today + timedelta(days=30),
            total_amount=Decimal('1000.00'),
            status=Invoice.STATUS_UNPAID,
        )
        Invoice.objects.create(
            invoice_no='INV002',
            member=self.member,
            invoice_date=today,
            due_date=today - timedelta(days=1),
            total_amount=Decimal('500.00'),
            status=Invoice.STATUS_OVERDUE,
        )

        Payment.objects.create(
            invoice_id=1,
            member=self.member,
            payment_date=today,
            amount_paid=Decimal('250.00'),
            payment_mode='cash',
        )

        metrics = get_dashboard_metrics()

        assert metrics['unpaid_invoices_count'] == 1
        assert metrics['pending_balance'] == Decimal('1250.00')
        assert metrics['collected_this_month'] == Decimal('250.00')
        assert metrics['overdue_invoices'] == 1

    def test_dashboard_metrics_annotate_top_members(self):
        today = timezone.localdate()

        for i in range(3):
            member = Member.objects.create(
                full_name=f'Member {i}',
                member_id=f'MEM{i:03d}',
                email=f'member{i}@test.com',
                phone_number='9876543210',
            )
            for j in range(i + 1):
                Invoice.objects.create(
                    invoice_no=f'INV{i}{j}',
                    member=member,
                    invoice_date=today,
                    due_date=today + timedelta(days=30),
                    total_amount=Decimal('1000.00'),
                    status=Invoice.STATUS_UNPAID,
                )

        metrics = get_dashboard_metrics()
        top_members = list(metrics['top_members'])

        assert len(top_members) == 3
        assert top_members[0].open_invoice_count == 3
        assert top_members[1].open_invoice_count == 2

    def test_attendance_today_and_month(self):
        today = timezone.localdate()
        this_month = today.replace(day=1)

        AttendanceLog.objects.create(
            date=today,
            check_in_time=timezone.now().replace(hour=9, minute=0),
            check_out_time=timezone.now().replace(hour=17, minute=0),
            person_type='member',
            member=self.member,
            source='check_in',
            status='present',
        )

        AttendanceLog.objects.create(
            date=today - timedelta(days=1),
            check_in_time=(timezone.now() - timedelta(days=1)).replace(hour=9, minute=0),
            check_out_time=(timezone.now() - timedelta(days=1)).replace(hour=17, minute=0),
            person_type='member',
            member=self.member,
            source='check_in',
            status='present',
        )

        metrics = get_dashboard_metrics()

        assert metrics['attendance_today'] == 1
        assert metrics['attendance_month'] == 2

    def test_recent_attendance_queryset(self):
        today = timezone.localdate()
        for i in range(7):
            AttendanceLog.objects.create(
                date=today - timedelta(days=i),
                check_in_time=(timezone.now() - timedelta(days=i)).replace(hour=9, minute=0),
                person_type='member',
                member=self.member,
                source='check_in',
                status='present',
            )

        metrics = get_dashboard_metrics()
        recent = list(metrics['recent_attendance'])

        assert len(recent) == 5
        assert recent[0].date == today


@pytest.mark.django_db
class TestNotificationSystem(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            login_id='testowner',
            password='testpass123',
            role='owner',
            is_active=True,
        )

    def test_notification_creation(self):
        notification = Notification.objects.create(
            user=self.user,
            title='Test Notification',
            message='This is a test.',
            level=Notification.LEVEL_INFO,
            status=Notification.STATUS_UNREAD,
        )

        assert notification.status == Notification.STATUS_UNREAD
        assert notification.read_at is None

    def test_notification_mark_read(self):
        notification = Notification.objects.create(
            user=self.user,
            title='Test Notification',
            message='This is a test.',
            level=Notification.LEVEL_INFO,
            status=Notification.STATUS_UNREAD,
        )

        notification.mark_read()

        assert notification.status == Notification.STATUS_READ
        assert notification.read_at is not None

    def test_notification_queryset_filtering(self):
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                title=f'Notification {i}',
                message=f'Message {i}',
                level=Notification.LEVEL_INFO,
                status=Notification.STATUS_UNREAD if i < 2 else Notification.STATUS_READ,
            )

        unread = Notification.objects.filter(user=self.user, status=Notification.STATUS_UNREAD).count()

        assert unread == 2


@pytest.mark.django_db
class TestPaymentProcessing(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            login_id='testowner',
            password='testpass123',
            role='owner',
        )
        self.member = Member.objects.create(
            full_name='Test Member',
            member_id='MEM001',
            email='member@test.com',
            phone_number='9876543210',
        )

    def test_invoice_refresh_balance_after_payment(self):
        today = timezone.localdate()
        invoice = Invoice.objects.create(
            invoice_no='INV001',
            member=self.member,
            invoice_date=today,
            due_date=today + timedelta(days=30),
            total_amount=Decimal('1000.00'),
            status=Invoice.STATUS_UNPAID,
        )

        payment = Payment.objects.create(
            invoice=invoice,
            member=self.member,
            payment_date=today,
            amount_paid=Decimal('600.00'),
            payment_mode='cash',
        )

        invoice.refresh_from_db()

        assert invoice.paid_amount == Decimal('600.00')
        assert invoice.balance_amount == Decimal('400.00')
        assert invoice.status == Invoice.STATUS_PARTIAL

    def test_invoice_become_paid_on_full_payment(self):
        today = timezone.localdate()
        invoice = Invoice.objects.create(
            invoice_no='INV001',
            member=self.member,
            invoice_date=today,
            due_date=today + timedelta(days=30),
            total_amount=Decimal('1000.00'),
            status=Invoice.STATUS_UNPAID,
        )

        Payment.objects.create(
            invoice=invoice,
            member=self.member,
            payment_date=today,
            amount_paid=Decimal('1000.00'),
            payment_mode='cash',
        )

        invoice.refresh_from_db()

        assert invoice.balance_amount == Decimal('0.00')
        assert invoice.status == Invoice.STATUS_PAID


@pytest.mark.django_db
class TestDailyFinancialReport(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            login_id='testowner',
            password='testpass123',
            role='owner',
        )
        self.member = Member.objects.create(
            full_name='Test Member',
            member_id='MEM001',
            email='member@test.com',
            phone_number='9876543210',
        )

    def test_daily_report_generation(self):
        today = timezone.localdate()
        this_month = today.replace(day=1)

        for i in range(3):
            Invoice.objects.create(
                invoice_no=f'INV{i}',
                member=self.member,
                invoice_date=today,
                due_date=today + timedelta(days=30),
                total_amount=Decimal('1000.00'),
                status=Invoice.STATUS_UNPAID,
            )

        Payment.objects.create(
            invoice_id=1,
            member=self.member,
            payment_date=today,
            amount_paid=Decimal('500.00'),
            payment_mode='cash',
        )

        report = DailyFinancialReport.objects.create(
            report_date=today,
            total_invoices=3,
            total_payments=1,
            total_paid_amount=Decimal('500.00'),
            pending_balance=Decimal('2500.00'),
            overdue_invoice_count=0,
        )

        assert report.report_date == today
        assert report.total_invoices == 3
        assert report.total_paid_amount == Decimal('500.00')
