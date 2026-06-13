from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from members.models import Member
from .forms import InvoiceForm, PaymentForm
from .models import Invoice, Payment


class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'payments/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset().select_related('member', 'membership').order_by('-invoice_date')
        status = self.request.GET.get('status')
        query = self.request.GET.get('q')

        if status:
            queryset = queryset.filter(status=status)
        if query:
            queryset = queryset.filter(
                Q(invoice_no__icontains=query)
                | Q(member__full_name__icontains=query)
                | Q(member__member_id__icontains=query)
                | Q(member__phone_number__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = self.request.GET.get('status', '')
        context['q'] = self.request.GET.get('q', '')
        return context


class InvoiceCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'payments/invoice_form.html'
    success_url = reverse_lazy('payments:invoice_list')
    success_message = 'Invoice created successfully.'

    def get_initial(self):
        initial = super().get_initial()
        initial['invoice_no'] = Invoice.get_next_invoice_no()
        initial['invoice_date'] = timezone.localdate()
        return initial


class InvoiceUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'payments/invoice_form.html'
    success_url = reverse_lazy('payments:invoice_list')
    success_message = 'Invoice updated successfully.'


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'payments/invoice_detail.html'
    context_object_name = 'invoice'


class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'payments/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset().select_related('member', 'invoice').order_by('-payment_date')
        query = self.request.GET.get('q')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if query:
            queryset = queryset.filter(
                Q(member__full_name__icontains=query)
                | Q(member__member_id__icontains=query)
                | Q(member__phone_number__icontains=query)
                | Q(invoice__invoice_no__icontains=query)
                | Q(transaction_reference__icontains=query)
            )
        if start_date:
            queryset = queryset.filter(payment_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(payment_date__lte=end_date)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        return context


class PaymentCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'payments/payment_form.html'
    success_url = reverse_lazy('payments:payment_list')
    success_message = 'Payment recorded successfully.'

    def get_initial(self):
        initial = super().get_initial()
        invoice_id = self.request.GET.get('invoice')
        if invoice_id:
            initial['invoice'] = invoice_id
        return initial


class PaymentUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'payments/payment_form.html'
    success_url = reverse_lazy('payments:payment_list')
    success_message = 'Payment updated successfully.'


class PaymentDetailView(LoginRequiredMixin, DetailView):
    model = Payment
    template_name = 'payments/payment_detail.html'
    context_object_name = 'payment'


class MemberPaymentHistoryView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'payments/member_payment_history.html'
    context_object_name = 'member'

    def get_object(self):
        return get_object_or_404(Member, pk=self.kwargs['member_pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        context['invoices'] = member.invoices.order_by('-invoice_date')[:10]
        context['payments'] = member.payments.order_by('-payment_date')[:10]
        context['open_balance'] = (
            member.invoices
            .filter(status__in=[Invoice.STATUS_UNPAID, Invoice.STATUS_PARTIAL])
            .aggregate(total=Sum('balance_amount'))['total'] or 0
        )
        return context
