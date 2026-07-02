from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from attendance.models import AttendanceLog
from departments.models import Department
from .forms import StaffForm
from .models import Staff
from attendance.biometric import BiometricSyncService
from attendance.models import BiometricDevice


class StaffListView(LoginRequiredMixin, ListView):
    model = Staff
    context_object_name = 'staff_list'
    template_name = 'staffs/staff_list.html'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().select_related('department').order_by('staff_id')
        query = self.request.GET.get('q')
        department_id = self.request.GET.get('department')
        active = self.request.GET.get('active')
        if query:
            queryset = queryset.filter(
                Q(staff_id__icontains=query)
                | Q(full_name__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(email__icontains=query)
                | Q(designation__icontains=query)
            )
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if active == 'active':
            queryset = queryset.filter(is_active=True)
        elif active == 'inactive':
            queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['department_id'] = self.request.GET.get('department', '')
        context['active'] = self.request.GET.get('active', '')
        context['departments'] = Department.objects.order_by('name')
        return context


class StaffCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Staff
    form_class = StaffForm
    template_name = 'staffs/staff_form.html'
    success_url = reverse_lazy('staffs:list')
    success_message = 'Staff member added successfully.'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        devices = BiometricDevice.objects.filter(device_type=BiometricDevice.DeviceType.AIFACE, is_active=True)
        for device in devices:
            service = BiometricSyncService(device)
            try:
                service.update_employee_ex(self.object)
            except Exception:
                pass
        messages.success(self.request, self.success_message)
        return redirect(self.success_url)
    
    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        devices = __import__('attendance.models', fromlist=['BiometricDevice']).BiometricDevice.objects.filter(
            device_type=__import__('attendance.models', fromlist=['BiometricDevice']).BiometricDevice.DeviceType.AIFACE,
            is_active=True,
        )
        from attendance.biometric import BiometricSyncService
        for device in devices:
            service = BiometricSyncService(device)
            try:
                service.update_employee_ex(self.object)
            except Exception:
                pass
        form.save_m2m()
        return super().form_valid(form)


class StaffUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Staff
    form_class = StaffForm
    template_name = 'staffs/staff_form.html'
    success_url = reverse_lazy('staffs:list')
    success_message = 'Staff member updated successfully.'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        devices = BiometricDevice.objects.filter(device_type=BiometricDevice.DeviceType.AIFACE, is_active=True)
        for device in devices:
            service = BiometricSyncService(device)
            try:
                service.update_employee_ex(self.object)
            except Exception:
                pass
        messages.success(self.request, self.success_message)
        return redirect(self.success_url)

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        devices = __import__('attendance.models', fromlist=['BiometricDevice']).BiometricDevice.objects.filter(
            device_type=__import__('attendance.models', fromlist=['BiometricDevice']).BiometricDevice.DeviceType.AIFACE,
            is_active=True,
        )
        from attendance.biometric import BiometricSyncService
        for device in devices:
            service = BiometricSyncService(device)
            try:
                service.update_employee_ex(self.object)
            except Exception:
                pass
        form.save_m2m()
        return super().form_valid(form)


class StaffDetailView(LoginRequiredMixin, DetailView):
    model = Staff
    template_name = 'staffs/staff_detail.html'
    context_object_name = 'staff'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attendance_history'] = self.object.attendance_logs.order_by('-check_in_time')[:8]
        return context
