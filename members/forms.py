from django import forms

from .models import Member, MemberDeleteRequest


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
