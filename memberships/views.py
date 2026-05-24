from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, TemplateView

from accounts.models import UserAccount
from payments.gateway import RazorpayGateway, RazorpayGatewayConfig
from payments.models import Invoice, Payment
from .forms import MembershipForm, MembershipPlanForm, MembershipPurchaseForm
from .models import Membership, MembershipPlan


def normalize_user_role(user):
    role = getattr(user, 'role', '')
    if not isinstance(role, str):
        return ''
    return role.strip().lower()


def is_member_user(user):
    return normalize_user_role(user) == UserAccount.ROLE_MEMBER


def get_member_profile(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    try:
        return user.member_profile
    except Exception:
        return None


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
        member_profile = get_member_profile(self.request.user)
        context['can_purchase'] = member_profile is not None and self.object.is_active
        return context


class MembershipPlanCatalogView(LoginRequiredMixin, ListView):
    model = MembershipPlan
    template_name = 'memberships/plan_selection.html'
    context_object_name = 'plans'

    def dispatch(self, request, *args, **kwargs):
        if not is_member_user(request.user):
            raise PermissionDenied('Only gym members can access the membership catalog.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        MembershipPlan.sync_default_plans()
        return MembershipPlan.objects.filter(is_active=True).order_by('duration_days', 'cardio_included')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member_profile = get_member_profile(self.request.user)
        context['active_membership'] = getattr(member_profile, 'active_membership', None) if member_profile else None
        return context


class MembershipPurchaseView(LoginRequiredMixin, FormView):
    template_name = 'memberships/plan_purchase.html'
    form_class = MembershipPurchaseForm

    def dispatch(self, request, *args, **kwargs):
        self.plan = get_object_or_404(MembershipPlan, pk=self.kwargs['pk'], is_active=True)
        self.member_profile = get_member_profile(request.user)
        if not is_member_user(request.user) or self.member_profile is None:
            raise PermissionDenied('Only members can purchase membership plans online.')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['plan'] = self.plan
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['plan'] = self.plan
        context['current_membership'] = getattr(self.member_profile, 'active_membership', None) if self.member_profile else None
        context['gateway_enabled'] = self._get_gateway() is not None
        return context

    def _get_gateway(self):
        api_key = getattr(settings, 'RAZORPAY_API_KEY', None)
        api_secret = getattr(settings, 'RAZORPAY_API_SECRET', None)
        if not api_key or not api_secret:
            return None
        config = RazorpayGatewayConfig(
            api_key=api_key,
            api_secret=api_secret,
            test_mode=getattr(settings, 'RAZORPAY_TEST_MODE', True),
        )
        return RazorpayGateway(config)

    def _create_razorpay_order(self, invoice, amount):
        gateway = self._get_gateway()
        if not gateway or amount <= 0:
            return None

        try:
            return gateway.create_order(
                amount_paise=int(Decimal(amount) * Decimal('100')),
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

    def form_valid(self, form):
        member = self.member_profile
        if member is None:
            raise PermissionDenied('Member profile not found for this account.')

        start_date = date.today()
        end_date = start_date + timedelta(days=self.plan.duration_days)
        payment_amount = form.cleaned_data['amount_paid']

        with transaction.atomic():
            membership = Membership.objects.create(
                member=member,
                plan=self.plan,
                start_date=start_date,
                end_date=end_date,
                membership_amount=self.plan.price,
                discount_amount=Decimal('0.00'),
                remarks=form.cleaned_data.get('remarks', ''),
            )

            invoice = Invoice.objects.create(
                invoice_no=self._generate_invoice_no(),
                member=member,
                membership=membership,
                invoice_date=date.today(),
                due_date=form.cleaned_data['balance_due_date'],
                subtotal=self.plan.price,
                discount_amount=Decimal('0.00'),
                tax_amount=Decimal('0.00'),
                remarks=f'Online membership purchase for {self.plan.name}.',
            )

            payment = Payment(
                invoice=invoice,
                member=member,
                payment_date=date.today(),
                amount_paid=payment_amount,
                payment_mode=Payment.PAYMENT_ONLINE,
                transaction_reference='',
                notes='Initial membership payment',
            )

            order_data = self._create_razorpay_order(invoice, payment_amount)
            if order_data is not None:
                payment.transaction_reference = order_data.get('id', '')
                payment.notes = 'Initial membership payment via Razorpay order.'

            payment.save()
            invoice.refresh_balance()

        messages.success(self.request, 'Membership purchase submitted successfully.')
        return redirect('memberships:purchase_success', invoice_pk=invoice.pk)

    def _generate_invoice_no(self):
        return f'INV-{date.today().strftime("%Y%m%d")}-{self.plan.duration_days}-{self.plan.cardio_included}'


class MembershipPurchaseSuccessView(LoginRequiredMixin, TemplateView):
    template_name = 'memberships/purchase_success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = get_object_or_404(Invoice, pk=self.kwargs['invoice_pk'])
        member_profile = get_member_profile(self.request.user)

        if not is_member_user(self.request.user) and normalize_user_role(self.request.user) != UserAccount.ROLE_OWNER:
            raise PermissionDenied('You are not authorized to view this purchase.')

        if normalize_user_role(self.request.user) != UserAccount.ROLE_OWNER and invoice.member != member_profile:
            raise PermissionDenied('You are not authorized to view this purchase.')

        context['invoice'] = invoice
        context['membership'] = invoice.membership
        context['payment'] = invoice.payments.order_by('-payment_date').first()
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
