from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import DepartmentForm
from .models import Department


class DepartmentListView(LoginRequiredMixin, ListView):
    model = Department
    context_object_name = 'departments'
    template_name = 'departments/department_list.html'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by('name')
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(speciality__icontains=query)
                | Q(head_name__icontains=query)
                | Q(head_phone_number__icontains=query)
            )
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        return context


class DepartmentCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'departments/department_form.html'
    success_url = reverse_lazy('departments:list')
    success_message = 'Department created successfully.'


class DepartmentUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'departments/department_form.html'
    success_url = reverse_lazy('departments:list')
    success_message = 'Department updated successfully.'


class DepartmentDetailView(LoginRequiredMixin, DetailView):
    model = Department
    template_name = 'departments/department_detail.html'
    context_object_name = 'department'
