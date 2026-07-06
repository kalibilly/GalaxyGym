from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.urls import reverse_lazy
from accounts.permissions import RoleRequiredMixin
from accounts.models import UserAccount
from members.models import Member
from memberships.models import MembershipPlan  # Imported to fetch gym membership plans
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

        # Fetch active membership plans to utilize the empty left column
        context['membership_plans'] = MembershipPlan.objects.filter(is_active=True).order_by('price')

        if self.request.user.is_authenticated:
            member_profile = getattr(self.request.user, 'member_profile', None)
            staff_profile = getattr(self.request.user, 'staff_profile', None)
            context['member_profile'] = member_profile
            context['staff_profile'] = staff_profile
            context['user_role'] = getattr(self.request.user, 'role', None)
            context['gym_id'] = member_profile.member_id if member_profile else None
            context['membership_summary'] = member_profile.get_membership_summary() if member_profile else None
            context['pending_amount'] = member_profile.pending_amount if member_profile else 0
            context['wallet_balance'] = member_profile.wallet_balance if member_profile else 0
            context['membership_expiry_alert'] = member_profile.has_expiring_membership() if member_profile else False
            context['pending_payment_alert'] = member_profile.needs_pending_payment_warning() if member_profile else False
            context['downgrade_warning'] = member_profile.should_warn_downgrade() if member_profile else False
            context['downgrade_plan'] = member_profile.suggested_downgrade_plan() if member_profile else None

        context['membership_records'] = []
        context['member_vehicle_records'] = []
        if self.request.user.is_authenticated:
            members = Member.objects.select_related('assigned_staff').prefetch_related('memberships__plan').order_by('member_id')[:8]
            context['membership_records'] = [
                {
                    'member': member,
                    'history': member.memberships.select_related('plan').order_by('-start_date'),
                }
                for member in members
            ]
            context['member_vehicle_records'] = [
                {
                    'member': member,
                    'vehicle_number': member.vehicle_number_permanent or member.vehicle_number_temporary or '—',
                    'vehicle_type': 'Permanent' if member.vehicle_number_permanent else 'Temporary' if member.vehicle_number_temporary else 'None',
                }
                for member in members
                if member.vehicle_number_permanent or member.vehicle_number_temporary
            ]

        return context


class EventListView(LoginRequiredMixin, TemplateView):
    template_name = 'events/list.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Events'
        context['events'] = []
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
            raise PermissionDenied('Member access is disabled. Contact gym staff for support.')
        
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
