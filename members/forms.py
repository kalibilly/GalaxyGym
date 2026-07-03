from django import forms

from .models import Member, MemberDeleteRequest


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            'device_user_id',
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
            'vehicle_number_permanent',
            'vehicle_number_temporary',
            'date_of_joining',
            'status',
            'is_active',
            'notes',
        ]
        widgets = {
            'date_of_joining': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'vehicle_number_permanent': forms.TextInput(attrs={'placeholder': 'Permanent vehicle number'}),
            'vehicle_number_temporary': forms.TextInput(attrs={'placeholder': 'Temporary vehicle number'}),
            'device_user_id': forms.HiddenInput(),
            'member_id': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['device_user_id'].required = False
        self.fields['member_id'].required = False
        self.fields['full_name'].required = True
        self.fields['phone_number'].required = True
        self.fields['date_of_joining'].required = True
        self.fields['vehicle_number_permanent'].required = False
        self.fields['vehicle_number_temporary'].required = False


class MemberDeleteRequestForm(forms.ModelForm):
    class Meta:
        model = MemberDeleteRequest
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'reason': 'Reason for delete request',
        }


class MemberDeleteRequestReviewForm(forms.ModelForm):
    class Meta:
        model = MemberDeleteRequest
        fields = ['status', 'admin_comments']
        widgets = {
            'admin_comments': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'admin_comments': 'Owner comments',
        }
