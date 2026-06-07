from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Invoice, Payment


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            'invoice_no',
            'member',
            'membership_plan',
            'invoice_date',
            'membership_end_date',
            'subtotal',
            'discount_amount',
            'total_amount',
            'balance_amount',
            'due_date',
            'pending_payment_status',
            'remarks',
        ]
        widgets = {
            'invoice_no': forms.TextInput(attrs={'readonly': 'readonly'}),
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'membership_end_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'invoice_date': 'Membership Start Date',
            'membership_plan': 'Membership Plan',
            'membership_end_date': 'Membership End Date',
            'subtotal': 'Subtotal',
            'discount_amount': 'Discount',
            'total_amount': 'Total',
            'balance_amount': 'Pending Amount',
            'due_date': 'Due Date',
            'pending_payment_status': 'Pending Payment Status',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name in ['subtotal', 'discount_amount', 'total_amount', 'balance_amount']:
            if name in self.fields:
                self.fields[name].required = False

        if 'remarks' in self.fields:
            self.fields['remarks'].required = False

    def clean_invoice_no(self):
        invoice_no = self.cleaned_data.get('invoice_no')
        if self.instance.pk:
            return self.instance.invoice_no
        return invoice_no

    def clean(self):
        cleaned_data = super().clean()

        invoice_date = cleaned_data.get('invoice_date')
        membership_end_date = cleaned_data.get('membership_end_date')
        subtotal = cleaned_data.get('subtotal')
        discount_amount = cleaned_data.get('discount_amount')
        total_amount = cleaned_data.get('total_amount')
        balance_amount = cleaned_data.get('balance_amount')
        due_date = cleaned_data.get('due_date')

        subtotal = subtotal if subtotal is not None else Decimal('0.00')
        discount_amount = discount_amount if discount_amount is not None else Decimal('0.00')
        total_amount = total_amount if total_amount is not None else Decimal('0.00')
        balance_amount = balance_amount if balance_amount is not None else Decimal('0.00')

        cleaned_data['subtotal'] = subtotal
        cleaned_data['discount_amount'] = discount_amount
        cleaned_data['total_amount'] = total_amount
        cleaned_data['balance_amount'] = balance_amount

        if invoice_date and membership_end_date and membership_end_date < invoice_date:
            raise ValidationError('Membership end date cannot be earlier than membership start date.')

        if due_date and invoice_date and due_date < invoice_date:
            raise ValidationError('Due date cannot be earlier than membership start date.')

        if subtotal < 0:
            raise ValidationError('Subtotal cannot be negative.')
        if discount_amount < 0:
            raise ValidationError('Discount cannot be negative.')
        if total_amount < 0:
            raise ValidationError('Total cannot be negative.')
        if balance_amount < 0:
            raise ValidationError('Pending amount cannot be negative.')

        if discount_amount > subtotal:
            raise ValidationError('Discount cannot be greater than subtotal.')

        expected_total = subtotal - discount_amount
        if total_amount != expected_total:
            raise ValidationError(
                f'Total must be equal to subtotal minus discount ({expected_total}).'
            )

        if balance_amount > total_amount:
            raise ValidationError('Pending amount cannot be greater than total.')

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        invoice = None

        if self.is_bound:
            invoice = self.data.get('invoice') or None
        elif self.instance.pk and self.instance.invoice_id:
            invoice = self.instance.invoice
        elif self.initial.get('invoice'):
            invoice = self.initial.get('invoice')

        if invoice and not self.is_bound:
            if hasattr(invoice, 'member'):
                self.fields['member'].initial = invoice.member
            else:
                try:
                    invoice_obj = Invoice.objects.select_related('member').get(pk=invoice)
                    self.fields['member'].initial = invoice_obj.member
                except (Invoice.DoesNotExist, ValueError, TypeError):
                    pass

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
            outstanding = invoice.balance_amount or Decimal('0.00')
            if self.instance.pk:
                original_amount = self.instance.amount_paid or Decimal('0.00')
                outstanding += original_amount

            if amount_paid > outstanding:
                raise ValidationError('Payment amount cannot exceed the invoice balance.')

        return cleaned_data
