from django.contrib import admin

from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'speciality', 'head_name', 'head_phone_number', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'speciality', 'head_name', 'head_phone_number')
