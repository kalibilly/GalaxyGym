from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q, Sum
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from attendance.models import AttendanceLog
from staffs.models import Staff
from .forms import MemberForm
from .models import Member


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


class MemberUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Member profile updated successfully.'


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
        return context
