from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from accounts.permissions import RoleRequiredMixin
from accounts.models import UserAccount
from .services import get_dashboard_metrics


class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'thumbnail': 'Thumbnail.jpeg',
            'images': [
                'image1.jpeg',
                'image2.jpeg',
                'image3.jpeg',
                'image4.jpeg',
                'image5.jpeg',
                'image6.jpeg',
                'image7.jpeg',
                'image8.jpeg',
                'image9.jpeg',
                'image10.jpeg',
            ],
        })
        return context


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard view that routes to role-specific dashboards.
    """
    template_name = 'dashboard/home.html'

    def get(self, request, *args, **kwargs):
        """Route to role-specific dashboard."""
        role = getattr(request.user, 'role', None)
        
        if role == UserAccount.ROLE_OWNER:
            return redirect('dashboard_owner')
        elif role == UserAccount.ROLE_STAFF:
            return redirect('dashboard_staff')
        elif role == UserAccount.ROLE_MEMBER:
            return redirect('dashboard_member')
        
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_dashboard_metrics())
        return context


class MemberDashboardView(RoleRequiredMixin, TemplateView):
    """Dashboard for members."""
    template_name = 'dashboard/member_dashboard.html'
    allowed_roles = [UserAccount.ROLE_MEMBER]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_display'] = self.request.user.get_role_display()
        return context


class StaffDashboardView(RoleRequiredMixin, TemplateView):
    """Dashboard for staff."""
    template_name = 'dashboard/staff_dashboard.html'
    allowed_roles = [UserAccount.ROLE_STAFF, UserAccount.ROLE_OWNER]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_display'] = self.request.user.get_role_display()
        return context


class OwnerDashboardView(RoleRequiredMixin, TemplateView):
    """Dashboard for owners."""
    template_name = 'dashboard/owner_dashboard.html'
    allowed_roles = [UserAccount.ROLE_OWNER]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_display'] = self.request.user.get_role_display()
        return context

