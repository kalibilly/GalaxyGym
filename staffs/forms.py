from django import forms

from .models import Staff


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = [
            'staff_id',
            'full_name',
            'phone_number',
            'email',
            'gender',
            'photo',
            'department',
            'designation',
            'date_of_joining',
            'is_active',
            'notes',
        ]
        widgets = {
            'date_of_joining': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
