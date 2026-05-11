import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.utils.decorators import method_decorator

from accounts.auth_models import AuditLog, Permission


logger = logging.getLogger(__name__)


def get_user_permissions(user):
    """Get permission object for user role."""
    perm, _ = Permission.objects.get_or_create(role=user.role)
    return perm


def check_permission(user, permission_attr):
    """Check if user has a specific permission."""
    if not user or not user.is_authenticated:
        return False
    perm = get_user_permissions(user)
    return getattr(perm, permission_attr, False)


def require_permission(permission_attr):
    """Decorator for view functions requiring a permission."""
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not check_permission(request.user, permission_attr):
                audit_log_action(
                    actor=request.user,
                    action=AuditLog.ACTION_OVERRIDE,
                    object_description=f'Attempted unauthorized access: {view_func.__name__}',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
                return HttpResponseForbidden('You do not have permission to access this resource.')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class PermissionRequiredMixin:
    """Mixin for class-based views requiring a permission."""
    permission_required = None
    
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.permission_required:
            return super().dispatch(request, *args, **kwargs)
        
        if not check_permission(request.user, self.permission_required):
            audit_log_action(
                actor=request.user,
                action=AuditLog.ACTION_OVERRIDE,
                object_description=f'Attempted unauthorized access: {self.__class__.__name__}',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            return HttpResponseForbidden('You do not have permission to access this resource.')
        
        return super().dispatch(request, *args, **kwargs)


def audit_log_action(actor, action, object_description='', content_type='', object_id='', changes=None, ip_address='', user_agent=''):
    """Create an audit log entry."""
    if changes is None:
        changes = {}
    
    AuditLog.objects.create(
        actor=actor,
        action=action,
        object_description=object_description,
        content_type=content_type,
        object_id=object_id,
        changes=changes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    logger.info(f'Audit: {actor.login_id} {action} {object_description}')


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR', '')


def audit_login(user, request):
    """Log user login."""
    audit_log_action(
        actor=user,
        action=AuditLog.ACTION_LOGIN,
        object_description=f'User logged in',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


def audit_logout(user, request):
    """Log user logout."""
    audit_log_action(
        actor=user,
        action=AuditLog.ACTION_LOGOUT,
        object_description=f'User logged out',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


def audit_create(user, model_name, object_id, object_description, ip_address='', user_agent=''):
    """Log object creation."""
    audit_log_action(
        actor=user,
        action=AuditLog.ACTION_CREATE,
        content_type=model_name,
        object_id=str(object_id),
        object_description=object_description,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def audit_update(user, model_name, object_id, object_description, changes=None, ip_address='', user_agent=''):
    """Log object update."""
    audit_log_action(
        actor=user,
        action=AuditLog.ACTION_UPDATE,
        content_type=model_name,
        object_id=str(object_id),
        object_description=object_description,
        changes=changes or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def audit_delete(user, model_name, object_id, object_description, ip_address='', user_agent=''):
    """Log object deletion."""
    audit_log_action(
        actor=user,
        action=AuditLog.ACTION_DELETE,
        content_type=model_name,
        object_id=str(object_id),
        object_description=object_description,
        ip_address=ip_address,
        user_agent=user_agent,
    )
