from django import forms
from django.core.exceptions import ValidationError

from .models import AttendanceLog


class AttendanceLogForm(forms.ModelForm):
    class Meta:
        model = AttendanceLog
        fields = [
            'member',
            'staff',
            'check_in_time',
            'check_out_time',
            'date',
            'source',
            'verification_mode',
            'device_id',
            'status',
            'remarks',
        ]
        widgets = {
            'check_in_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'check_out_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get('member')
        staff = cleaned_data.get('staff')
        check_in_time = cleaned_data.get('check_in_time')
        check_out_time = cleaned_data.get('check_out_time')

        if bool(member) == bool(staff):
            raise ValidationError('Select exactly one of member or staff for attendance.')
        if check_in_time and check_out_time and check_out_time < check_in_time:
            raise ValidationError('Check-out cannot be earlier than check-in.')
        return cleaned_data
