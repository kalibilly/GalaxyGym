from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Membership, MembershipPlan


class MembershipPlanSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            actual_value = getattr(value, 'value', value)
            plan = MembershipPlan.objects.filter(pk=actual_value).first()
            if plan:
                option['attrs']['data-price'] = str(plan.price)
        return option


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
    member_lookup = forms.CharField(required=False, label='Member ID')
    member_name = forms.CharField(required=False, label='Member Name', disabled=True)
    member_phone = forms.CharField(required=False, label='Member Phone', disabled=True)
    member_joining = forms.CharField(required=False, label='Date of Joining', disabled=True)

    class Meta:
        model = Membership
        fields = [
            'entry_number',
            'member',
            'plan',
            'start_date',
            'end_date',
            'price_before_discount',
            'discount_amount',
            'total_amount',
            'paid_amount',
            'payment_status',
            'remarks',
        ]
        widgets = {
            'entry_number': forms.TextInput(attrs={'placeholder': 'Auto-generated if left blank'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
            'price_before_discount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'readonly': 'readonly'}),
            'discount_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'total_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'readonly': 'readonly'}),
            'paid_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
        }
        labels = {
            'entry_number': 'Entry Number / S.No',
            'member': 'Member',
            'plan': 'Membership Plan',
            'start_date': 'Start Date',
            'end_date': 'End Date',
            'price_before_discount': 'Price Before Discount',
            'discount_amount': 'Discount Amount',
            'total_amount': 'Total Amount',
            'paid_amount': 'Paid Amount',
            'payment_status': 'Payment Status',
            'remarks': 'Remarks',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].widget = MembershipPlanSelect(choices=self.fields['plan'].choices)
        
        # CHANGED: Changed entry_number to False so it can be automatically generated if left empty
        self.fields['entry_number'].required = False
        
        self.fields['member'].required = True
        self.fields['plan'].required = True
        self.fields['start_date'].required = True
        self.fields['end_date'].required = True
        self.fields['price_before_discount'].required = True
        self.fields['discount_amount'].required = True
        self.fields['total_amount'].required = True
        self.fields['paid_amount'].required = True
        self.fields['payment_status'].required = True
        self.fields['remarks'].required = False
        self.fields['member_lookup'].required = False

        if self.instance and self.instance.pk and self.instance.plan_id:
            self.fields['price_before_discount'].initial = self.instance.plan.price if self.instance.plan else self.instance.price_before_discount

        if self.instance and self.instance.pk:
            self.fields['member_lookup'].initial = self.instance.member.member_id if self.instance.member else ''
            self.fields['member_name'].initial = self.instance.member.full_name if self.instance.member else ''
            self.fields['member_phone'].initial = self.instance.member.phone_number if self.instance.member else ''
            self.fields['member_joining'].initial = self.instance.member.date_of_joining if self.instance.member else ''

    def clean(self):
        cleaned_data = super().clean()
        price_before_discount = cleaned_data.get('price_before_discount')
        discount_amount = cleaned_data.get('discount_amount')
        total_amount = cleaned_data.get('total_amount')
        paid_amount = cleaned_data.get('paid_amount')

        if price_before_discount is not None and price_before_discount < 0:
            self.add_error('price_before_discount', 'Price before discount cannot be negative.')
        if discount_amount is not None and discount_amount < 0:
            self.add_error('discount_amount', 'Discount cannot be negative.')
        if price_before_discount is not None and discount_amount is not None and discount_amount > price_before_discount:
            self.add_error('discount_amount', 'Discount cannot be greater than the base price.')
        
        # Calculate calculated total amount for validation safety
        base_price = price_before_discount or Decimal('0.00')
        disc = discount_amount or Decimal('0.00')
        calc_total = base_price - disc

        if paid_amount is not None and paid_amount < 0:
            self.add_error('paid_amount', 'Paid amount cannot be negative.')
        if paid_amount is not None and paid_amount > calc_total:
            self.add_error('paid_amount', 'Paid amount cannot be greater than the Total Amount.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.plan_id and (instance.price_before_discount == 0 or instance.price_before_discount is None):
            instance.price_before_discount = instance.plan.price
        if instance.discount_amount is None:
            instance.discount_amount = 0
        instance.total_amount = instance.price_before_discount - instance.discount_amount
        
        # CHANGED: Auto-generate entry_number sequentially if left blank by user
        if not instance.entry_number:
            last_membership = Membership.objects.order_by('-id').first()
            if last_membership and last_membership.entry_number and last_membership.entry_number.isdigit():
                instance.entry_number = str(int(last_membership.entry_number) + 1)
            else:
                instance.entry_number = "1001" # Starting baseline serial format
                
        if commit:
            instance.save()
        return instance


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
