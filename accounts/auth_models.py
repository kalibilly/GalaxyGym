from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    """Durable audit trail for compliance and security review."""
    
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_PERMISSION_CHANGE = 'permission_change'
    ACTION_OVERRIDE = 'admin_override'
    ACTION_EXPORT = 'export'
    
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
        (ACTION_LOGIN, 'Login'),
        (ACTION_LOGOUT, 'Logout'),
        (ACTION_PERMISSION_CHANGE, 'Permission Change'),
        (ACTION_OVERRIDE, 'Admin Override'),
        (ACTION_EXPORT, 'Export'),
    ]
    
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='audit_logs_created',
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES, db_index=True)
    
    content_type = models.CharField(max_length=128, blank=True)
    object_id = models.CharField(max_length=256, blank=True)
    object_description = models.CharField(max_length=256, blank=True)
    
    changes = models.JSONField(default=dict, blank=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
    
    def __str__(self):
        return f'{self.actor.login_id} {self.action} {self.object_description} at {self.created_at}'


class Permission(models.Model):
    """Role-based permission registry."""
    
    ROLE_OWNER = 'owner'
    ROLE_STAFF = 'staff'
    ROLE_MEMBER = 'member'
    
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_STAFF, 'Staff'),
        (ROLE_MEMBER, 'Member'),
    ]
    
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, unique=True)
    
    # Billing permissions
    can_view_invoices = models.BooleanField(default=False)
    can_create_invoices = models.BooleanField(default=False)
    can_edit_invoices = models.BooleanField(default=False)
    can_delete_invoices = models.BooleanField(default=False)
    can_view_payments = models.BooleanField(default=False)
    can_create_payments = models.BooleanField(default=False)
    can_edit_payments = models.BooleanField(default=False)
    
    # Attendance permissions
    can_view_attendance = models.BooleanField(default=False)
    can_create_attendance = models.BooleanField(default=False)
    can_edit_attendance = models.BooleanField(default=False)
    
    # Member/Staff permissions
    can_view_members = models.BooleanField(default=False)
    can_create_members = models.BooleanField(default=False)
    can_edit_members = models.BooleanField(default=False)
    can_delete_members = models.BooleanField(default=False)
    
    can_view_staff = models.BooleanField(default=False)
    can_create_staff = models.BooleanField(default=False)
    can_edit_staff = models.BooleanField(default=False)
    can_delete_staff = models.BooleanField(default=False)
    
    # Reporting permissions
    can_view_reports = models.BooleanField(default=False)
    can_export_reports = models.BooleanField(default=False)
    
    # Admin permissions
    can_access_admin = models.BooleanField(default=False)
    can_view_audit_logs = models.BooleanField(default=False)
    can_manage_permissions = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
    
    def __str__(self):
        return f'Permissions for {self.role}'
    
    @classmethod
    def get_default_permissions(cls):
        """Initialize default permission sets for standard roles."""
        owner_perms, _ = cls.objects.get_or_create(
            role=cls.ROLE_OWNER,
            defaults={
                'can_view_invoices': True,
                'can_create_invoices': True,
                'can_edit_invoices': True,
                'can_delete_invoices': True,
                'can_view_payments': True,
                'can_create_payments': True,
                'can_edit_payments': True,
                'can_view_attendance': True,
                'can_create_attendance': True,
                'can_edit_attendance': True,
                'can_view_members': True,
                'can_create_members': True,
                'can_edit_members': True,
                'can_delete_members': True,
                'can_view_staff': True,
                'can_create_staff': True,
                'can_edit_staff': True,
                'can_delete_staff': True,
                'can_view_reports': True,
                'can_export_reports': True,
                'can_access_admin': True,
                'can_view_audit_logs': True,
                'can_manage_permissions': True,
                'can_manage_users': True,
            },
        )
        
        staff_perms, _ = cls.objects.get_or_create(
            role=cls.ROLE_STAFF,
            defaults={
                'can_view_invoices': True,
                'can_create_payments': True,
                'can_view_payments': True,
                'can_view_attendance': True,
                'can_create_attendance': True,
                'can_edit_attendance': True,
                'can_view_members': True,
                'can_view_staff': True,
                'can_view_reports': False,
            },
        )
        
        member_perms, _ = cls.objects.get_or_create(
            role=cls.ROLE_MEMBER,
            defaults={
                'can_view_invoices': True,
                'can_view_payments': True,
                'can_view_attendance': True,
            },
        )
        
        return owner_perms, staff_perms, member_perms
