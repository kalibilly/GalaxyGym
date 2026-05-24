from django.contrib import admin

from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        'member_id',
        'full_name',
        'phone_number',
        'email',
        'status',
        'date_of_joining',
        'is_active',
        'created_by',
        'updated_by',
    )
    list_filter = ('status', 'is_active', 'gender')
    search_fields = ('member_id', 'full_name', 'phone_number', 'email')
    readonly_fields = ('created_by', 'updated_by')
    fields = (
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
        'created_by',
        'updated_by',
    )
    raw_id_fields = ('user', 'assigned_staff')

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
