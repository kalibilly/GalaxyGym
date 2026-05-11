from django import forms
from django.core.exceptions import ValidationError

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
            'subtotal',
            'discount_amount',
            'tax_amount',
            'remarks',
        ]
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        subtotal = cleaned_data.get('subtotal') or 0
        discount_amount = cleaned_data.get('discount_amount') or 0
        tax_amount = cleaned_data.get('tax_amount') or 0
        invoice_date = cleaned_data.get('invoice_date')
        due_date = cleaned_data.get('due_date')

        if subtotal < 0 or discount_amount < 0 or tax_amount < 0:
            raise ValidationError('Amount fields cannot be negative.')
        if due_date and invoice_date and due_date < invoice_date:
            raise ValidationError('Due date cannot be earlier than invoice date.')
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
