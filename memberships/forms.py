from django import forms

from .models import Membership, MembershipPlan


class MembershipPlanForm(forms.ModelForm):
    class Meta:
        model = MembershipPlan
        fields = ['name', 'duration_days', 'price', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
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
            'renewed_from',
            'remarks',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }
