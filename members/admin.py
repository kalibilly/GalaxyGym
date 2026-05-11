from django.contrib import admin

from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_id', 'full_name', 'phone_number', 'email', 'status', 'date_of_joining', 'is_active')
    list_filter = ('status', 'is_active', 'gender')
    search_fields = ('member_id', 'full_name', 'phone_number', 'email')
    raw_id_fields = ('user', 'assigned_staff')
