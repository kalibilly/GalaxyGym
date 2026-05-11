from django import forms

from .models import Member


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            'member_id',
            'full_name',
            'phone_number',
            'email',
            'gender',
            'photo',
            'emergency_contact_name',
            'emergency_contact_phone',
            'assigned_staff',
            'address',
            'date_of_joining',
            'status',
            'is_active',
            'notes',
        ]
        widgets = {
            'date_of_joining': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
