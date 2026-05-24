from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import MembershipForm, MembershipPlanForm
from .models import Membership, MembershipPlan


class MembershipPlanListView(LoginRequiredMixin, ListView):
    model = MembershipPlan
    template_name = 'memberships/plan_list.html'
    context_object_name = 'plans'
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset().order_by('name')
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        return context


class MembershipPlanCreateView(LoginRequiredMixin, CreateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'memberships/plan_form.html'
    success_url = reverse_lazy('memberships:plan_list')


class MembershipPlanUpdateView(LoginRequiredMixin, UpdateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'memberships/plan_form.html'
    success_url = reverse_lazy('memberships:plan_list')


class MembershipPlanDetailView(LoginRequiredMixin, DetailView):
    model = MembershipPlan
    template_name = 'memberships/plan_detail.html'
    context_object_name = 'plan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_purchase'] = self.object.is_active
        return context


class MembershipListView(LoginRequiredMixin, ListView):
    model = Membership
    template_name = 'memberships/membership_list.html'
    context_object_name = 'memberships'
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset().select_related('member', 'plan').order_by('-start_date')
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        if query:
            queryset = queryset.filter(
                Q(member__member_id__icontains=query)
                | Q(member__full_name__icontains=query)
                | Q(plan__name__icontains=query)
            )
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        return context


class MembershipCreateView(LoginRequiredMixin, CreateView):
    model = Membership
    form_class = MembershipForm
    template_name = 'memberships/membership_form.html'
    success_url = reverse_lazy('memberships:list')


class MembershipUpdateView(LoginRequiredMixin, UpdateView):
    model = Membership
    form_class = MembershipForm
    template_name = 'memberships/membership_form.html'
    success_url = reverse_lazy('memberships:list')


class MembershipDetailView(LoginRequiredMixin, DetailView):
    model = Membership
    template_name = 'memberships/membership_detail.html'
    context_object_name = 'membership'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['latest_invoice'] = self.object.invoices.first()
        return context
