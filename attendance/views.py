from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import AttendanceLogForm
from .models import AttendanceLog


class AttendanceListView(LoginRequiredMixin, ListView):
    model = AttendanceLog
    template_name = 'attendance/attendance_list.html'
    context_object_name = 'attendance_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset().select_related('member', 'staff').order_by('-date', '-check_in_time')
        person_type = self.request.GET.get('person_type')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        query = self.request.GET.get('q')

        if person_type:
            queryset = queryset.filter(person_type=person_type)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if query:
            queryset = queryset.filter(
                Q(member__full_name__icontains=query)
                | Q(member__member_id__icontains=query)
                | Q(staff__full_name__icontains=query)
                | Q(staff__staff_id__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person_type'] = self.request.GET.get('person_type', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        context['q'] = self.request.GET.get('q', '')
        return context


class AttendanceCreateView(LoginRequiredMixin, CreateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = 'attendance/attendance_form.html'
    success_url = reverse_lazy('attendance:attendance_list')


class AttendanceUpdateView(LoginRequiredMixin, UpdateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = 'attendance/attendance_form.html'
    success_url = reverse_lazy('attendance:attendance_list')


class AttendanceDetailView(LoginRequiredMixin, DetailView):
    model = AttendanceLog
    template_name = 'attendance/attendance_detail.html'
    context_object_name = 'attendance'


from members.models import Member
from staffs.models import Staff


class MemberAttendanceHistoryView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'attendance/member_history.html'
    context_object_name = 'member'

    def get_object(self):
        return get_object_or_404(Member, pk=self.kwargs['member_pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        context['attendance_list'] = member.attendance_logs.order_by('-check_in_time')[:20]
        return context


class StaffAttendanceHistoryView(LoginRequiredMixin, DetailView):
    model = Staff
    template_name = 'attendance/staff_history.html'
    context_object_name = 'staff'

    def get_object(self):
        return get_object_or_404(Staff, pk=self.kwargs['staff_pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.object
        context['attendance_list'] = staff.attendance_logs.order_by('-check_in_time')[:20]
        return context
