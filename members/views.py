from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.models import UserAccount
from accounts.permissions import RoleRequiredMixin
from attendance.models import AttendanceLog
from staffs.models import Staff
from .forms import (
    MemberForm,
    MemberDeleteRequestForm,
    MemberDeleteRequestReviewForm,
)
from .models import Member, MemberDeleteRequest


class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    context_object_name = 'member_list'
    template_name = 'members/member_list.html'
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset().select_related('assigned_staff').order_by('member_id')
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        staff_id = self.request.GET.get('staff')

        if query:
            queryset = queryset.filter(
                Q(member_id__icontains=query)
                | Q(full_name__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(email__icontains=query)
                | Q(emergency_contact_name__icontains=query)
            )
        if status:
            queryset = queryset.filter(status=status)
        if staff_id:
            queryset = queryset.filter(assigned_staff_id=staff_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        context['staff_id'] = self.request.GET.get('staff', '')
        context['staff_members'] = Staff.objects.order_by('full_name')
        return context


class MemberCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Member profile created successfully.'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.updated_by = self.request.user
        self.object.save()
        return super().form_valid(form)


class MemberUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Member profile updated successfully.'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.updated_by = self.request.user
        self.object.save()
        return super().form_valid(form)


class MemberDeleteRequestCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    allowed_roles = [UserAccount.ROLE_STAFF, UserAccount.ROLE_OWNER]
    model = MemberDeleteRequest
    form_class = MemberDeleteRequestForm
    template_name = 'members/member_delete_request_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Delete request submitted successfully. Owner will review it.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = get_object_or_404(Member, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        form.instance.member = get_object_or_404(Member, pk=self.kwargs['pk'])
        form.instance.requested_by = self.request.user
        return super().form_valid(form)


class MemberDeleteRequestListView(RoleRequiredMixin, TemplateView):
    allowed_roles = [UserAccount.ROLE_OWNER, UserAccount.ROLE_STAFF]
    template_name = 'members/member_delete_request_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requests = MemberDeleteRequest.objects.select_related('member', 'requested_by', 'reviewed_by').order_by('-requested_at')
        if self.request.user.role == UserAccount.ROLE_STAFF:
            requests = requests.filter(requested_by=self.request.user)
        context['delete_requests'] = requests
        return context


class MemberDeleteRequestReviewView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    allowed_roles = [UserAccount.ROLE_OWNER]
    model = MemberDeleteRequest
    form_class = MemberDeleteRequestReviewForm
    template_name = 'members/member_delete_request_review.html'
    success_url = reverse_lazy('members:delete_request_list')
    success_message = 'Delete request updated successfully.'

    def form_valid(self, form):
        form.instance.reviewed_by = self.request.user
        form.instance.reviewed_at = timezone.now()
        response = super().form_valid(form)
        if form.instance.status == MemberDeleteRequest.STATUS_APPROVED:
            member = form.instance.member
            member.status = Member.STATUS_INACTIVE
            member.save(update_fields=['status'])
        return response


class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'members/member_detail.html'
    context_object_name = 'member'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        context['active_membership'] = member.active_membership
        context['recent_memberships'] = member.memberships.order_by('-start_date')[:5]
        context['latest_invoice'] = member.invoices.order_by('-invoice_date').first()
        context['open_invoices'] = member.invoices.filter(status__in=[member.invoices.model.STATUS_UNPAID, member.invoices.model.STATUS_PARTIAL]).order_by('due_date')[:5]
        context['recent_payments'] = member.payments.order_by('-payment_date')[:5]
        context['attendance_history'] = member.attendance_logs.order_by('-check_in_time')[:5]
        context['outstanding_balance'] = member.invoices.filter(status__in=[member.invoices.model.STATUS_UNPAID, member.invoices.model.STATUS_PARTIAL]).aggregate(total=Sum('balance_amount'))['total'] or 0
        context['delete_request'] = member.delete_requests.order_by('-requested_at').first()
        return context
