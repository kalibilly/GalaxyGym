from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm

from .models import GymIssuedID, UserAccount


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Login ID',
        widget=forms.TextInput(
            attrs={
                'autofocus': True,
                'autocomplete': 'username',
                'class': 'form-control',
            }
        ),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                'autocomplete': 'current-password',
                'class': 'form-control',
            }
        ),
    )


class SignupForm(UserCreationForm):
    gym_id = forms.CharField(
        label='Gym Issued ID',
        max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        label='Account Type',
        choices=UserAccount.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    full_name = forms.CharField(
        label='Full Name',
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    phone_number = forms.CharField(
        label='Phone Number',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    email = forms.EmailField(
        label='Email (optional)',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = UserAccount
        fields = ('login_id', 'full_name', 'phone_number', 'email', 'role', 'gym_id', 'password1', 'password2')
        widgets = {
            'login_id': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        gym_id = cleaned_data.get('gym_id')
        role = cleaned_data.get('role')

        if gym_id and role:
            try:
                gym_issued = GymIssuedID.objects.get(code=gym_id, role=role, is_used=False)
            except GymIssuedID.DoesNotExist:
                raise forms.ValidationError(
                    'The provided gym-issued ID is invalid for the selected role, already used, or has not been registered yet.'
                )
            cleaned_data['gym_issued'] = gym_issued

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data.get('full_name', '')
        user.role = self.cleaned_data.get('role', UserAccount.ROLE_MEMBER)
        user.is_active = True
        user.is_verified = True
        if user.role == UserAccount.ROLE_STAFF:
            user.is_staff = False
        if commit:
            user.save()
            gym_issued = self.cleaned_data.get('gym_issued')
            if gym_issued:
                gym_issued.is_used = True
                gym_issued.used_by = user
                gym_issued.save()
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserAccount
        fields = ('full_name', 'email', 'phone_number')
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }


class UserAccountCreationForm(UserCreationForm):
    class Meta:
        model = UserAccount
        fields = ('login_id', 'full_name', 'email', 'phone_number', 'role')
        widgets = {
            'login_id': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }


class UserAccountChangeForm(UserChangeForm):
    class Meta:
        model = UserAccount
        fields = ('login_id', 'full_name', 'email', 'phone_number', 'role', 'is_active', 'is_staff', 'is_superuser')
        widgets = {
            'login_id': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }
