from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Membership, MembershipPlan


class MembershipPlanForm(forms.ModelForm):
    class Meta:
        model = MembershipPlan
        fields = ['name', 'duration_days', 'cardio_included', 'price', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'cardio_included': 'Includes Cardio',
            'duration_days': 'Duration (days)',
        }
        help_texts = {
            'duration_days': 'Allowed values: 30, 90, 180, 360.',
        }


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = [
            'member',
            'plan',
            'start_date',
            'end_date',
            'membership_amount',
            'discount_amount',
            'payment_status',
            'remarks',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
            'membership_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'discount_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
        labels = {
            'member': 'Member',
            'plan': 'Membership Plan',
            'start_date': 'Start Date',
            'end_date': 'End Date',
            'membership_amount': 'Membership Amount',
            'discount_amount': 'Discount',
            'payment_status': 'Payment Status',
            'remarks': 'Remarks',
        }

    def clean(self):
        cleaned_data = super().clean()
        membership_amount = cleaned_data.get('membership_amount')
        discount_amount = cleaned_data.get('discount_amount')

        if membership_amount is not None and membership_amount < 0:
            self.add_error('membership_amount', 'Membership amount cannot be negative.')
        if discount_amount is not None and discount_amount < 0:
            self.add_error('discount_amount', 'Discount cannot be negative.')
        if membership_amount is not None and discount_amount is not None and discount_amount > membership_amount:
            self.add_error('discount_amount', 'Discount cannot be greater than membership amount.')

        return cleaned_data


class MembershipPurchaseForm(forms.Form):
    PAYMENT_FULL = 'full'
    PAYMENT_PARTIAL = 'partial'
    PAYMENT_CHOICES = [
        (PAYMENT_FULL, 'Pay full amount'),
        (PAYMENT_PARTIAL, 'Pay partial amount'),
    ]

    payment_option = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        widget=forms.RadioSelect,
        initial=PAYMENT_FULL,
    )
    amount_paid = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        help_text='Enter the amount you want to pay now.',
    )
    balance_due_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Choose when the remaining balance will be due.',
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Any additional notes for this purchase.',
    )

    def __init__(self, *args, plan: MembershipPlan = None, **kwargs):
        self.plan = plan
        super().__init__(*args, **kwargs)

        if plan is not None:
            self.fields['amount_paid'].initial = plan.price
            self.fields['balance_due_date'].initial = date.today() + timedelta(days=7)
            if not plan.allow_partial_payment:
                self.fields['payment_option'].choices = [(self.PAYMENT_FULL, 'Pay full amount')]
                self.fields['payment_option'].initial = self.PAYMENT_FULL

    def clean(self):
        cleaned_data = super().clean()
        if self.plan is None:
            raise ValidationError('Membership plan is required to complete the purchase.')

        amount_paid = cleaned_data.get('amount_paid')
        payment_option = cleaned_data.get('payment_option')
        balance_due_date = cleaned_data.get('balance_due_date')

        if amount_paid is None:
            raise ValidationError('Please enter the amount to pay now.')

        if balance_due_date and balance_due_date < date.today():
            self.add_error('balance_due_date', 'Due date cannot be in the past.')

        if payment_option == self.PAYMENT_FULL:
            if amount_paid != self.plan.price:
                self.add_error('amount_paid', 'Full payment must equal the plan price.')
        else:
            if not self.plan.allow_partial_payment:
                self.add_error('payment_option', 'Partial payment is not available for this plan.')
            elif amount_paid >= self.plan.price:
                self.add_error('amount_paid', 'Partial payment must be less than the full price.')

        return cleaned_data
