from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    def decorator(view_func):
        @login_required(login_url='login')
        def wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied('You do not have permission to access this page.')
        return wrapped_view
    return decorator


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = []

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.role in self.allowed_roles

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied('You do not have permission to access this page.')
