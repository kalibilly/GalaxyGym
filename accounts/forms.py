from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import UserAccount


class UserAccountCreationForm(UserCreationForm):
    class Meta:
        model = UserAccount
        fields = ('login_id', 'email', 'phone_number', 'role')


class UserAccountChangeForm(UserChangeForm):
    class Meta:
        model = UserAccount
        fields = ('login_id', 'email', 'phone_number', 'role', 'is_active', 'is_staff', 'is_superuser')
