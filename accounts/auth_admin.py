from django.contrib import admin

from .auth_models import AuditLog, Permission


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('actor', 'action', 'object_description', 'created_at')
    list_filter = ('action', 'created_at', 'actor')
    search_fields = ('actor__login_id', 'object_description', 'content_type')
    readonly_fields = ('created_at', 'actor', 'action', 'ip_address', 'user_agent', 'changes')
    fields = ('actor', 'action', 'object_description', 'content_type', 'object_id', 'changes', 'ip_address', 'user_agent', 'created_at')
    ordering = ('-created_at',)
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('role',)
    fields = (
        'role',
        ('can_view_invoices', 'can_create_invoices', 'can_edit_invoices', 'can_delete_invoices'),
        ('can_view_payments', 'can_create_payments', 'can_edit_payments'),
        ('can_view_attendance', 'can_create_attendance', 'can_edit_attendance'),
        ('can_view_members', 'can_create_members', 'can_edit_members', 'can_delete_members'),
        ('can_view_staff', 'can_create_staff', 'can_edit_staff', 'can_delete_staff'),
        ('can_view_reports', 'can_export_reports'),
        ('can_access_admin', 'can_view_audit_logs', 'can_manage_permissions', 'can_manage_users'),
    )
