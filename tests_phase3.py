import pytest
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.test import TestCase, RequestFactory
from django.core.cache import cache

from accounts.models import UserAccount
from accounts.auth_models import AuditLog, Permission
from accounts.auth_services import (
    check_permission, audit_log_action, get_client_ip, get_user_permissions
)
from members.models import Member
from payments.models import Invoice, Payment
from attendance.models import AttendanceLog
from core.task_models import AsyncTask, TaskError
from core.task_services import (
    create_async_task, mark_task_running, mark_task_succeeded, mark_task_failed,
    retry_task, get_task_statistics, get_recent_failures, cleanup_old_tasks,
)
from core.cache_services import (
    cache_dashboard_metrics, invalidate_dashboard_cache,
    paginate_queryset, get_paginated_context,
)
from notifications.models import Notification


@pytest.mark.django_db
class TestAsyncTaskLifecycle(TestCase):
    """Test task status tracking and lifecycle management."""
    
    def setUp(self):
        self.owner = UserAccount.objects.create_user(
            login_id='testowner',
            password='testpass123',
            role='owner',
        )
    
    def test_create_async_task(self):
        task = create_async_task('my_task', input_data={'param': 'value'}, user=self.owner)
        
        assert task.task_type == 'my_task'
        assert task.status == AsyncTask.STATUS_PENDING
        assert task.input_data == {'param': 'value'}
        assert task.user == self.owner
    
    def test_idempotent_task_creation(self):
        key = 'unique_key_123'
        task1 = create_async_task('my_task', idempotency_key=key)
        task2 = create_async_task('my_task', idempotency_key=key)
        
        assert task1.id == task2.id
    
    def test_task_lifecycle_transitions(self):
        task = create_async_task('my_task')
        
        mark_task_running(task.id, 'celery_task_id_123')
        task.refresh_from_db()
        assert task.status == AsyncTask.STATUS_RUNNING
        assert task.started_at is not None
        
        mark_task_succeeded(task.id, result_data={'result': 'success'})
        task.refresh_from_db()
        assert task.status == AsyncTask.STATUS_SUCCEEDED
        assert task.completed_at is not None
        assert task.result_data == {'result': 'success'}
    
    def test_task_failure_and_error_logging(self):
        task = create_async_task('my_task')
        mark_task_running(task.id)
        mark_task_failed(task.id, 'Something went wrong', 'traceback info', severity='error')
        
        task.refresh_from_db()
        assert task.status == AsyncTask.STATUS_FAILED
        assert task.error_message == 'Something went wrong'
        assert task.failed_at is not None
        
        error = TaskError.objects.get(async_task=task)
        assert error.severity == 'error'
        assert not error.is_resolved
    
    def test_retry_logic(self):
        task = create_async_task('my_task', max_retries=3)
        mark_task_running(task.id)
        mark_task_failed(task.id, 'Error 1')
        
        can_retry = retry_task(task.id)
        assert can_retry is True
        task.refresh_from_db()
        assert task.retry_count == 1
        assert task.status == AsyncTask.STATUS_RETRIED
        
        mark_task_failed(task.id, 'Error 2')
        retry_task(task.id)
        retry_task(task.id)
        retry_task(task.id)
        
        can_retry = retry_task(task.id)
        assert can_retry is False
    
    def test_task_statistics_aggregation(self):
        now = timezone.now()
        for i in range(5):
            task = create_async_task(f'task_{i}')
            mark_task_running(task.id)
            if i < 3:
                mark_task_succeeded(task.id)
            else:
                mark_task_failed(task.id, 'Error')
        
        stats = get_task_statistics(time_window_hours=24)
        
        assert stats['total_tasks'] == 5
        assert stats['succeeded_tasks'] == 3
        assert stats['failed_tasks'] == 2
        assert stats['success_rate'] == 60.0


@pytest.mark.django_db
class TestPermissionAndAuthorization(TestCase):
    """Test role-based access control and permission checking."""
    
    def setUp(self):
        self.owner = UserAccount.objects.create_user(
            login_id='owner1',
            password='pass123',
            role='owner',
        )
        self.staff = UserAccount.objects.create_user(
            login_id='staff1',
            password='pass123',
            role='staff',
        )
        self.member = UserAccount.objects.create_user(
            login_id='member1',
            password='pass123',
            role='member',
        )
        Permission.get_default_permissions()
    
    def test_owner_can_create_invoices(self):
        can_create = check_permission(self.owner, 'can_create_invoices')
        assert can_create is True
    
    def test_member_cannot_create_invoices(self):
        can_create = check_permission(self.member, 'can_create_invoices')
        assert can_create is False
    
    def test_staff_can_view_attendance(self):
        can_view = check_permission(self.staff, 'can_view_attendance')
        assert can_view is True
    
    def test_member_cannot_manage_permissions(self):
        can_manage = check_permission(self.member, 'can_manage_permissions')
        assert can_manage is False
    
    def test_get_user_permissions(self):
        perm = get_user_permissions(self.owner)
        assert perm.role == 'owner'
        assert perm.can_access_admin is True


@pytest.mark.django_db
class TestAuditLogging(TestCase):
    """Test audit trail for compliance and security."""
    
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            login_id='testuser',
            password='pass123',
            role='owner',
        )
        self.factory = RequestFactory()
    
    def test_audit_log_creation(self):
        audit_log_action(
            actor=self.user,
            action=AuditLog.ACTION_CREATE,
            object_description='Created invoice INV001',
            content_type='Invoice',
            object_id='1',
            ip_address='127.0.0.1',
            user_agent='TestAgent',
        )
        
        log = AuditLog.objects.get(actor=self.user)
        assert log.action == AuditLog.ACTION_CREATE
        assert log.object_description == 'Created invoice INV001'
        assert log.ip_address == '127.0.0.1'
    
    def test_get_client_ip_from_forwarded(self):
        request = self.factory.get('/')
        request.META['HTTP_X_FORWARDED_FOR'] = '192.168.1.1, 10.0.0.1'
        
        ip = get_client_ip(request)
        assert ip == '192.168.1.1'
    
    def test_audit_log_filtering_by_actor_and_action(self):
        audit_log_action(self.user, AuditLog.ACTION_LOGIN, 'Login')
        audit_log_action(self.user, AuditLog.ACTION_UPDATE, 'Updated invoice')
        
        logins = AuditLog.objects.filter(action=AuditLog.ACTION_LOGIN).count()
        updates = AuditLog.objects.filter(action=AuditLog.ACTION_UPDATE).count()
        
        assert logins == 1
        assert updates == 1


@pytest.mark.django_db
class TestCachingBehavior(TestCase):
    """Test cache hit/miss and invalidation."""
    
    def setUp(self):
        self.member = Member.objects.create(
            full_name='Test Member',
            member_id='MEM001',
            email='member@test.com',
            phone_number='9876543210',
        )
        self.today = timezone.localdate()
    
    def test_dashboard_cache_hit_and_miss(self):
        cache.clear()
        
        metrics1 = cache_dashboard_metrics(ttl=300)
        metrics2 = cache_dashboard_metrics(ttl=300)
        
        assert metrics1 == metrics2
        assert metrics1['page_title'] == 'Dashboard'
    
    def test_cache_invalidation_on_write(self):
        cache.clear()
        
        metrics1 = cache_dashboard_metrics(ttl=300)
        initial_count = metrics1['total_invoices']
        
        Invoice.objects.create(
            invoice_no='INV001',
            member=self.member,
            invoice_date=self.today,
            due_date=self.today,
            total_amount=Decimal('100.00'),
        )
        
        invalidate_dashboard_cache()
        metrics2 = cache_dashboard_metrics(ttl=300)
        
        assert metrics2['total_invoices'] == initial_count + 1


@pytest.mark.django_db
class TestPagination(TestCase):
    """Test pagination for list views."""
    
    def setUp(self):
        for i in range(50):
            Member.objects.create(
                full_name=f'Member {i}',
                member_id=f'MEM{i:03d}',
                email=f'member{i}@test.com',
                phone_number='9876543210',
            )
    
    def test_paginate_first_page(self):
        queryset = Member.objects.all()
        page_obj, paginator, is_paginated = paginate_queryset(queryset, 1, page_size=15)
        
        assert len(page_obj) == 15
        assert page_obj.number == 1
        assert is_paginated is True
        assert paginator.num_pages == 4
    
    def test_paginate_middle_page(self):
        queryset = Member.objects.all()
        page_obj, paginator, is_paginated = paginate_queryset(queryset, 2, page_size=15)
        
        assert len(page_obj) == 15
        assert page_obj.number == 2
    
    def test_paginate_last_page(self):
        queryset = Member.objects.all()
        page_obj, paginator, is_paginated = paginate_queryset(queryset, 4, page_size=15)
        
        assert len(page_obj) == 5
        assert page_obj.number == 4
    
    def test_paginate_invalid_page(self):
        queryset = Member.objects.all()
        page_obj, paginator, is_paginated = paginate_queryset(queryset, 999, page_size=15)
        
        assert page_obj.number == paginator.num_pages
    
    def test_get_paginated_context(self):
        queryset = Member.objects.all()
        page_obj, paginator, is_paginated = paginate_queryset(queryset, 1, page_size=15)
        
        context = get_paginated_context(page_obj, paginator)
        
        assert context['page_number'] == 1
        assert context['total_pages'] == 4
        assert context['total_items'] == 50
        assert context['is_paginated'] is True


@pytest.mark.django_db
class TestQueryOptimization(TestCase):
    """Test that optimized queries avoid N+1 patterns."""
    
    def setUp(self):
        self.member = Member.objects.create(
            full_name='Test Member',
            member_id='MEM001',
            email='member@test.com',
            phone_number='9876543210',
        )
        for i in range(5):
            Invoice.objects.create(
                invoice_no=f'INV{i}',
                member=self.member,
                invoice_date=timezone.localdate(),
                due_date=timezone.localdate(),
                total_amount=Decimal('100.00'),
            )
    
    def test_select_related_optimization(self):
        from django.test.utils import override_settings
        from django.db import connection
        
        with override_settings(DEBUG=True):
            connection.queries_log.clear()
            
            payments = Payment.objects.select_related('member', 'invoice').all()[:5]
            _ = [(p.member.full_name, p.invoice.invoice_no) for p in payments]
            
            query_count = len(connection.queries)
            assert query_count <= 2
    
    def test_annotate_prevents_loop_iteration(self):
        from django.db.models import Count
        
        members_with_counts = (
            Member.objects
            .annotate(invoice_count=Count('invoices'))
            .filter(invoice_count__gt=0)
        )
        
        for member in members_with_counts:
            assert member.invoice_count == 5
