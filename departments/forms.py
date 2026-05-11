from django import forms

from .models import Department


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'speciality', 'head_name', 'head_phone_number', 'is_active']
        widgets = {
            'speciality': forms.TextInput(attrs={'placeholder': 'Reception, Training, Technology...'}),
            'head_phone_number': forms.TextInput(attrs={'placeholder': '+919876543210'}),
        }
