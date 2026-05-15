from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction

from .forms import UserAccountChangeForm, UserAccountCreationForm
from .models import UserAccount, GymIssuedID, SignupRequest
from .services.whatsapp import send_approval_notification, send_rejection_notification


class UserAccountAdmin(admin.ModelAdmin):
    add_form = UserAccountCreationForm
    form = UserAccountChangeForm
    model = UserAccount
    list_display = ('login_id', 'full_name', 'get_role_display', 'phone_number', 'is_active', 'is_verified', 'date_joined')
    list_filter = ('role', 'is_active', 'is_verified', 'date_joined')
    search_fields = ('login_id', 'full_name', 'phone_number', 'email')
    fieldsets = (
        ('Login Info', {
            'fields': ('login_id', 'password')
        }),
        ('Personal Info', {
            'fields': ('full_name', 'email', 'phone_number')
        }),
        ('Account Settings', {
            'fields': ('role', 'is_active', 'is_verified', 'is_staff', 'is_superuser')
        }),
        ('Important Dates', {
            'fields': ('date_joined', 'last_login'),
            'classes': ('collapse',)
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('login_id', 'password1', 'password2', 'full_name', 'phone_number', 'email', 'role', 'is_active'),
        }),
    )
    ordering = ('-date_joined',)

    def get_role_display(self, obj):
        return obj.get_role_display()
    get_role_display.short_description = 'Role'


class GymIssuedIDAdmin(admin.ModelAdmin):
    list_display = ('code', 'role', 'is_used', 'used_by', 'created_at')
    list_filter = ('role', 'is_used', 'created_at')
    search_fields = ('code', 'used_by__login_id', 'used_by__full_name')
    readonly_fields = ('created_at', 'used_by')
    fieldsets = (
        ('ID Code', {
            'fields': ('code', 'role')
        }),
        ('Usage', {
            'fields': ('is_used', 'used_by')
        }),
        ('Dates', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


class SignupRequestAdmin(admin.ModelAdmin):
    list_display = (
        'get_full_name_link',
        'get_requested_role_display',
        'unique_id',
        'phone_number',
        'desired_login_id',
        'get_status_badge',
        'submitted_at',
    )
    list_filter = ('status', 'requested_role', 'submitted_at')
    search_fields = ('full_name', 'phone_number', 'unique_id', 'desired_login_id')
    readonly_fields = ('submitted_at', 'reviewed_at', 'reviewed_by', 'created_user', 'whatsapp_notified')
    
    fieldsets = (
        ('Request Info', {
            'fields': ('requested_role', 'unique_id', 'full_name', 'phone_number', 'email', 'desired_login_id', 'password_hash')
        }),
        ('Status & Review', {
            'fields': ('status', 'reviewed_at', 'reviewed_by', 'created_user')
        }),
        ('Rejection Details', {
            'fields': ('rejection_reason',),
            'classes': ('collapse',)
        }),
        ('Notifications', {
            'fields': ('whatsapp_notified',),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Submission Date', {
            'fields': ('submitted_at',),
            'classes': ('collapse',)
        }),
    )

    actions = ['approve_requests', 'reject_requests_action', 'send_whatsapp_notification']

    def get_full_name_link(self, obj):
        return obj.full_name
    get_full_name_link.short_description = 'Full Name'

    def get_requested_role_display(self, obj):
        return obj.get_requested_role_display()
    get_requested_role_display.short_description = 'Type'

    def get_status_badge(self, obj):
        if obj.status == SignupRequest.STATUS_APPROVED:
            color = 'green'
            label = 'Approved'
        elif obj.status == SignupRequest.STATUS_REJECTED:
            color = 'red'
            label = 'Rejected'
        else:
            color = 'orange'
            label = 'Pending'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            label
        )
    get_status_badge.short_description = 'Status'

    def approve_requests(self, request, queryset):
        """
        Admin action to approve selected signup requests.
        """
        pending_requests = queryset.filter(status=SignupRequest.STATUS_PENDING)
        approved_count = 0
        failed_count = 0

        for signup_request in pending_requests:
            try:
                with transaction.atomic():
                    user = signup_request.approve(request.user)
                    send_approval_notification(
                        phone_number=user.phone_number,
                        name=user.full_name,
                        login_id=user.login_id,
                    )
                    signup_request.whatsapp_notified = True
                    signup_request.save()
                    approved_count += 1
            except Exception as e:
                failed_count += 1
                messages.error(request, f'Failed to approve {signup_request.full_name}: {str(e)}')

        if approved_count > 0:
            messages.success(
                request,
                f'{approved_count} signup request(s) approved successfully. WhatsApp notifications sent.'
            )

    approve_requests.short_description = 'Approve selected signup requests'

    def reject_requests_action(self, request, queryset):
        """
        Redirect to rejection form for selected requests.
        """
        pending_requests = queryset.filter(status=SignupRequest.STATUS_PENDING)
        if not pending_requests.exists():
            messages.warning(request, 'No pending requests selected.')
            return

        request.session['reject_ids'] = list(pending_requests.values_list('id', flat=True))
        return redirect('admin:signup_reject')

    reject_requests_action.short_description = 'Reject selected signup requests'

    def send_whatsapp_notification(self, request, queryset):
        """
        Manually resend WhatsApp notifications.
        """
        approved_requests = queryset.filter(status=SignupRequest.STATUS_APPROVED, created_user__isnull=False)
        sent_count = 0

        for signup_request in approved_requests:
            try:
                send_approval_notification(
                    phone_number=signup_request.created_user.phone_number,
                    name=signup_request.created_user.full_name,
                    login_id=signup_request.created_user.login_id,
                )
                signup_request.whatsapp_notified = True
                signup_request.save()
                sent_count += 1
            except Exception as e:
                messages.error(request, f'Failed to send to {signup_request.full_name}: {str(e)}')

        if sent_count > 0:
            messages.success(request, f'WhatsApp notifications sent to {sent_count} user(s).')

    send_whatsapp_notification.short_description = 'Resend WhatsApp notifications'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('signup/reject/', self.admin_site.admin_view(self.reject_view), name='signup_reject'),
        ]
        return custom_urls + urls

    def reject_view(self, request):
        """
        Custom admin view for rejecting signup requests with reason.
        """
        if request.method == 'POST':
            reject_ids = request.session.pop('reject_ids', [])
            rejection_reason = request.POST.get('rejection_reason', '').strip()

            if not rejection_reason:
                messages.error(request, 'Please provide a rejection reason.')
                return redirect('admin:accounts_signuprequest_changelist')

            rejected_count = 0
            for request_id in reject_ids:
                try:
                    signup_request = SignupRequest.objects.get(id=request_id, status=SignupRequest.STATUS_PENDING)
                    signup_request.reject(request.user, rejection_reason)
                    send_rejection_notification(
                        phone_number=signup_request.phone_number,
                        name=signup_request.full_name,
                        reason=rejection_reason,
                    )
                    signup_request.whatsapp_notified = True
                    signup_request.save()
                    rejected_count += 1
                except SignupRequest.DoesNotExist:
                    pass
                except Exception as e:
                    messages.error(request, f'Error processing request: {str(e)}')

            if rejected_count > 0:
                messages.success(
                    request,
                    f'{rejected_count} signup request(s) rejected. WhatsApp notifications sent.'
                )
            return redirect('admin:accounts_signuprequest_changelist')

        reject_ids = request.session.get('reject_ids', [])
        requests_to_reject = SignupRequest.objects.filter(id__in=reject_ids)

        context = {
            'title': 'Reject Signup Requests',
            'requests': requests_to_reject,
            'opts': SignupRequest._meta,
            'has_view_permission': True,
            'site_header': self.admin_site.site_header,
            'site_title': self.admin_site.site_title,
        }
        return render(request, 'admin/reject_signup_requests.html', context)


admin.site.register(UserAccount, UserAccountAdmin)
admin.site.register(GymIssuedID, GymIssuedIDAdmin)
admin.site.register(SignupRequest, SignupRequestAdmin)

