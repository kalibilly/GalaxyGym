from django.contrib import admin
from .models import MembershipPlan, Membership


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_days', 'cardio_included', 'price', 'is_active', 'created_at')
    list_filter = ('cardio_included', 'is_active', 'duration_days')
    search_fields = ('name', 'description')
    ordering = ('duration_days', 'cardio_included')


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    # Fixed 'final_amount' to 'total_amount' to match your model field configuration
    list_display = (
        'entry_number', 
        'member', 
        'plan', 
        'start_date', 
        'end_date', 
        'total_amount', 
        'paid_amount', 
        'payment_status', 
        'status'
    )
    
    list_filter = ('status', 'payment_status', 'plan', 'start_date', 'end_date')
    search_fields = ('entry_number', 'member__full_name', 'member__member_id', 'remarks')
    
    # Removed 'renewed_from' from raw_id_fields since it's not defined in your models.py
    raw_id_fields = ('member', 'plan')
    
    date_hierarchy = 'start_date'
    ordering = ('-start_date', '-created_at')
    
    readonly_fields = ('total_amount',)

    def save_model(self, request, obj, form, change):
        # Auto-compute fields handled by model's custom save before commit
        super().save_model(request, obj, form, change)
