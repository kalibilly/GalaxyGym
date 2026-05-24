from datetime import date, timedelta
from decimal import Decimal
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from payments.gateway import RazorpayGateway, RazorpayGatewayConfig

from .forms import MembershipForm, MembershipPlanForm, MembershipPurchaseForm
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


class MembershipPlanCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'memberships/plan_form.html'
    success_url = reverse_lazy('memberships:plan_list')
    success_message = 'Membership plan saved successfully.'


class MembershipPlanUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'memberships/plan_form.html'
    success_url = reverse_lazy('memberships:plan_list')
    success_message = 'Membership plan updated successfully.'


class MembershipPlanDetailView(LoginRequiredMixin, DetailView):
    model = MembershipPlan
    template_name = 'memberships/plan_detail.html'
    context_object_name = 'plan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_purchase'] = getattr(self.request.user, 'member_profile', None) is not None and self.object.is_active
        return context


class MembershipPurchaseView(LoginRequiredMixin, FormView):
    template_name = 'memberships/plan_purchase.html'
    form_class = MembershipPurchaseForm

    def dispatch(self, request, *args, **kwargs):
        self.plan = get_object_or_404(MembershipPlan, pk=self.kwargs['pk'], is_active=True)
        if not getattr(request.user, 'member_profile', None):
            raise PermissionDenied('Only members can purchase membership plans online.')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['balance_due_date'] = date.today() + timedelta(days=7)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['plan'] = self.plan
        context['gateway_enabled'] = self._get_gateway() is not None
        return context

    def _get_gateway(self):
        api_key = getattr(settings, 'RAZORPAY_API_KEY', None)
        api_secret = getattr(settings, 'RAZORPAY_API_SECRET', None)
        if not api_key or not api_secret:
            return None
        config = RazorpayGatewayConfig(api_key=api_key, api_secret=api_secret, test_mode=getattr(settings, 'RAZORPAY_TEST_MODE', True))
        return RazorpayGateway(config)

    def _generate_invoice_no(self):
        return f'INV-{uuid.uuid4().hex[:8].upper()}'

    def form_valid(self, form):
        member = self.request.user.member_profile
        start_date = date.today()
        end_date = start_date + timedelta(days=self.plan.duration_days)

        membership = Membership.objects.create(
            member=member,
            plan=self.plan,
            start_date=start_date,
            end_date=end_date,
            membership_amount=self.plan.price,
            discount_amount=0,
            remarks=form.cleaned_data['remarks'],
        )

        invoice = self._create_invoice(member, membership, form.cleaned_data['balance_due_date'])
        order_data = self._create_razorpay_order(invoice)

        messages.success(self.request, 'Your membership purchase has been created. Review the invoice to complete payment.')

        context = self.get_context_data(
            form=form,
            plan=self.plan,
            purchase_created=True,
            membership=membership,
            invoice=invoice,
            order_data=order_data,
        )
        return self.render_to_response(context)

    def _create_invoice(self, member, membership, balance_due_date):
        from payments.models import Invoice

        invoice = Invoice.objects.create(
            invoice_no=self._generate_invoice_no(),
            member=member,
            membership=membership,
            invoice_date=date.today(),
            due_date=balance_due_date,
            subtotal=self.plan.price,
            discount_amount=0,
            tax_amount=0,
            remarks=f'Online membership purchase for {self.plan.name}.',
        )
        return invoice

    def _create_razorpay_order(self, invoice):
        gateway = self._get_gateway()
        if not gateway or invoice.balance_amount <= 0:
            return None

        try:
            return gateway.create_order(
                amount_paise=int(Decimal(invoice.balance_amount) * Decimal('100')),
                receipt=invoice.invoice_no,
                notes={
                    'member_id': invoice.member.member_id,
                    'membership_id': str(invoice.membership_id),
                    'invoice_id': str(invoice.pk),
                },
            )
        except Exception:
            messages.warning(self.request, 'Could not initialize Razorpay checkout at this time.')
            return None


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


class MembershipCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Membership
    form_class = MembershipForm
    template_name = 'memberships/membership_form.html'
    success_url = reverse_lazy('memberships:list')
    success_message = 'Membership assigned successfully.'


class MembershipUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Membership
    form_class = MembershipForm
    template_name = 'memberships/membership_form.html'
    success_url = reverse_lazy('memberships:list')
    success_message = 'Membership updated successfully.'


class MembershipDetailView(LoginRequiredMixin, DetailView):
    model = Membership
    template_name = 'memberships/membership_detail.html'
    context_object_name = 'membership'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['latest_invoice'] = self.object.invoices.first()
        return context
