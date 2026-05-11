from django.contrib import admin

from .models import Staff


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('staff_id', 'full_name', 'phone_number', 'email', 'department', 'designation', 'date_of_joining', 'is_active')
    list_filter = ('department', 'is_active', 'gender')
    search_fields = ('staff_id', 'full_name', 'phone_number', 'email', 'designation')
    raw_id_fields = ('user',)
