from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.contrib.auth.hashers import make_password

from .models import GymIssuedID, SignupRequest, UserAccount


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


class SignupRequestForm(forms.ModelForm):
    """
    Form for users to submit a signup request.
    Request is stored but account is not created until admin approval.
    """
    gym_id = forms.CharField(
        label='Gym Issued ID',
        max_length=32,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
    password2 = forms.CharField(
        label='Confirm Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = SignupRequest
        fields = ('requested_role', 'gym_id', 'full_name', 'phone_number', 'email', 'desired_login_id')
        widgets = {
            'requested_role': forms.Select(attrs={'class': 'form-select'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'desired_login_id': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'requested_role': 'Account Type',
            'desired_login_id': 'Login ID',
            'full_name': 'Full Name',
            'phone_number': 'Phone Number',
            'email': 'Email (optional)',
        }

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        gym_id = cleaned_data.get('gym_id')
        desired_login_id = cleaned_data.get('desired_login_id')
        phone_number = cleaned_data.get('phone_number')

        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError('Passwords do not match.')
            if len(password1) < 8:
                raise forms.ValidationError('Password must be at least 8 characters long.')

        if desired_login_id:
            if UserAccount.objects.filter(login_id=desired_login_id).exists():
                raise forms.ValidationError('This login ID is already taken.')
            if SignupRequest.objects.filter(desired_login_id=desired_login_id, status=SignupRequest.STATUS_PENDING).exists():
                raise forms.ValidationError('A pending signup request with this login ID already exists.')

        if gym_id:
            try:
                GymIssuedID.objects.get(code=gym_id, is_used=False)
            except GymIssuedID.DoesNotExist:
                raise forms.ValidationError(
                    'The provided gym-issued ID is invalid, already used, or has not been registered yet.'
                )
            cleaned_data['gym_issued'] = GymIssuedID.objects.get(code=gym_id)

        if phone_number:
            if SignupRequest.objects.filter(phone_number=phone_number, status=SignupRequest.STATUS_PENDING).exists():
                raise forms.ValidationError('A pending signup request with this phone number already exists.')

        return cleaned_data

    def save(self, commit=True):
        """
        Save the signup request without creating an active user account.
        """
        instance = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            instance.password_hash = make_password(password)

        if commit:
            instance.save()
        return instance


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

