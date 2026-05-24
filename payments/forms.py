from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Invoice, Payment


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            'invoice_no',
            'member',
            'membership',
            'invoice_date',
            'due_date',
            'balance_amount',
            'pending_payment_status',
            'remarks',
        ]
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'readonly': 'readonly'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'invoice_date': 'Membership Start Date',
            'balance_amount': 'Pending Amount',
            'pending_payment_status': 'Pending Payment Status',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'invoice_no' in self.fields:
            self.fields['invoice_no'].widget.attrs.update({'readonly': 'readonly'})
        if 'due_date' in self.fields:
            self.fields['due_date'].widget.attrs.update({'readonly': 'readonly'})

    def clean(self):
        cleaned_data = super().clean()
        invoice_date = cleaned_data.get('invoice_date')
        balance_amount = cleaned_data.get('balance_amount')

        if balance_amount is not None and balance_amount < 0:
            raise ValidationError('Pending amount cannot be negative.')

        if invoice_date:
            cleaned_data['due_date'] = invoice_date + timedelta(days=7)

        return cleaned_data


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            'invoice',
            'member',
            'payment_date',
            'amount_paid',
            'payment_mode',
            'transaction_reference',
            'received_by',
            'notes',
        ]
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        amount_paid = cleaned_data.get('amount_paid')
        invoice = cleaned_data.get('invoice')
        member = cleaned_data.get('member')

        if amount_paid is not None and amount_paid <= 0:
            raise ValidationError('Payment amount must be greater than zero.')
        if invoice and member and member != invoice.member:
            raise ValidationError('Selected member must match the invoice member.')
        if invoice and amount_paid is not None:
            outstanding = invoice.get_balance_amount()
            if self.instance.pk:
                original_amount = self.instance.amount_paid
                outstanding += original_amount
            if amount_paid > outstanding:
                raise ValidationError('Payment amount cannot exceed the invoice balance.')
        return cleaned_data
