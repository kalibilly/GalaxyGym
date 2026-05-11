from django.contrib import admin

from .models import Membership, MembershipPlan


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_days', 'price', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('member', 'plan', 'start_date', 'end_date', 'final_amount', 'status')
    list_filter = ('status', 'plan')
    search_fields = ('member__member_id', 'member__full_name', 'plan__name')
    raw_id_fields = ('member', 'plan', 'renewed_from')
