from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from members.models import Member

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
        queryset = super().get_queryset().select_related('member', 'plan', 'renewed_from').order_by('-start_date')
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        if query:
            queryset = queryset.filter(
                Q(serial_number__icontains=query)
                | Q(member__member_id__icontains=query)
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

    def get_initial(self):
        initial = super().get_initial()
        member_id = self.request.GET.get('member')
        plan_id = self.request.GET.get('plan')
        renewed_from = self.request.GET.get('renewed_from')

        if member_id:
            initial['member'] = member_id
            member = Member.objects.filter(pk=member_id).first()
            if member:
                initial['member_lookup'] = member.member_id
                initial['member_name'] = member.full_name
                initial['member_phone'] = member.phone_number
                initial['member_joining'] = member.date_of_joining
        if plan_id:
            initial['plan'] = plan_id
            plan = MembershipPlan.objects.filter(pk=plan_id).first()
            if plan:
                initial['price_before_discount'] = plan.price
                initial['total_amount'] = plan.price
        if renewed_from:
            source_membership = Membership.objects.select_related('plan').filter(pk=renewed_from).first()
            if source_membership:
                next_start_date = max(timezone.localdate(), source_membership.end_date + timedelta(days=1))
                initial['member'] = source_membership.member_id
                initial['plan'] = source_membership.plan_id
                initial['start_date'] = next_start_date
                initial['end_date'] = next_start_date + timedelta(days=source_membership.plan.duration_days)
                initial['price_before_discount'] = source_membership.price_before_discount
                initial['discount_amount'] = source_membership.discount_amount
                initial['total_amount'] = source_membership.total_amount
                initial['payment_status'] = Membership.PAYMENT_STATUS_UNPAID
                initial['renewed_from'] = source_membership.pk
        return initial

    def form_valid(self, form):
        renewed_from = self.request.GET.get('renewed_from')
        if renewed_from:
            source_membership = Membership.objects.filter(pk=renewed_from).first()
            if source_membership:
                form.instance.renewed_from = source_membership
        form.instance.serial_number = form.instance.serial_number or Membership.get_next_serial_number()
        return super().form_valid(form)


class MembershipUpdateView(LoginRequiredMixin, UpdateView):
    model = Membership
    form_class = MembershipForm
    template_name = 'memberships/membership_form.html'
    success_url = reverse_lazy('memberships:list')


class MembershipRenewView(LoginRequiredMixin, View):
    def get(self, request, pk):
        return redirect(f"{reverse_lazy('memberships:create')}?renewed_from={pk}")


class MembershipDetailView(LoginRequiredMixin, DetailView):
    model = Membership
    template_name = 'memberships/membership_detail.html'
    context_object_name = 'membership'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_renew'] = self.object.needs_renewal_action
        return context


def membership_lookup_member(request):
    member_id = request.GET.get('member_id', '').strip()
    if not member_id:
        return JsonResponse({'found': False})

    member = Member.objects.filter(member_id=member_id).first() or Member.objects.filter(pk=member_id).first()
    if not member:
        return JsonResponse({'found': False})

    return JsonResponse({
        'found': True,
        'member_id': member.member_id,
        'name': member.full_name,
        'phone': member.phone_number,
        'joining_date': member.date_of_joining.strftime('%Y-%m-%d') if member.date_of_joining else '',
        'member_pk': member.pk,
    })
