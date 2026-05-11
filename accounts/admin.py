from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UserAccountChangeForm, UserAccountCreationForm
from .models import UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(UserAdmin):
    add_form = UserAccountCreationForm
    form = UserAccountChangeForm
    model = UserAccount
    list_display = ('login_id', 'email', 'phone_number', 'role', 'is_active', 'is_staff', 'is_superuser')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('login_id', 'email', 'phone_number')
    ordering = ('login_id',)

    fieldsets = (
        (None, {'fields': ('login_id', 'password')}),
        ('Personal Information', {'fields': ('email', 'phone_number', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('login_id', 'email', 'phone_number', 'role', 'password1', 'password2', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )
