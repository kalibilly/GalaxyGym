from datetime import date, timedelta
from decimal import Decimal

from django.apps import apps
from django.db import models
from django.utils import timezone

from core.models import ActiveStatusModel, TimeStampedModel, phone_regex


class Member(TimeStampedModel, ActiveStatusModel):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_BLACKLISTED = 'blacklisted'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_BLACKLISTED, 'Blacklisted'),
    ]

    GENDER_MALE = 'male'
    GENDER_FEMALE = 'female'
    GENDER_OTHER = 'other'

    GENDER_CHOICES = [
        (GENDER_MALE, 'Male'),
        (GENDER_FEMALE, 'Female'),
        (GENDER_OTHER, 'Other'),
    ]

    user = models.OneToOneField(
        'accounts.UserAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='member_profile',
    )
    member_id = models.CharField(max_length=24, unique=True)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, validators=[phone_regex])
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    photo = models.ImageField(upload_to='member_photos/', null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[phone_regex],
    )
    assigned_staff = models.ForeignKey(
        'staffs.Staff',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_members',
    )
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    address = models.TextField(blank=True)
    date_of_joining = models.DateField(default=timezone.now)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'accounts.UserAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_members',
    )
    updated_by = models.ForeignKey(
        'accounts.UserAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_members',
    )

    class Meta:
        ordering = ['member_id']
        verbose_name = 'Member'
        verbose_name_plural = 'Members'

    def __str__(self):
        return f'{self.member_id} - {self.full_name}'

    @property
    def active_membership(self):
        return self.memberships.filter(status='active').order_by('-end_date').first()

    @property
    def pending_amount(self):
        Invoice = apps.get_model('payments', 'Invoice')
        unpaid_statuses = [Invoice.STATUS_UNPAID, Invoice.STATUS_PARTIAL, Invoice.STATUS_OVERDUE]
        total = self.invoices.filter(status__in=unpaid_statuses).aggregate(total=models.Sum('balance_amount'))['total']
        return total or Decimal('0.00')

    @property
    def overdue_days(self):
        Invoice = apps.get_model('payments', 'Invoice')
        overdue_invoice = self.invoices.filter(status=Invoice.STATUS_OVERDUE).order_by('due_date').first()
        if not overdue_invoice or not overdue_invoice.due_date:
            return 0
        return max((date.today() - overdue_invoice.due_date).days, 0)

    def has_expiring_membership(self, within_days=7):
        membership = self.active_membership
        if membership is None or membership.end_date is None:
            return False
        return (membership.end_date - date.today()).days <= within_days and membership.end_date >= date.today()

    def needs_pending_payment_warning(self):
        return self.pending_amount > Decimal('0.00')

    def should_warn_downgrade(self):
        return self.pending_amount > Decimal('0.00') and self.overdue_days > 7 and self.active_membership is not None

    def suggested_downgrade_plan(self):
        membership = self.active_membership
        if not membership or not membership.plan:
            return None
        MembershipPlan = apps.get_model('memberships', 'MembershipPlan')
        lower_plans = MembershipPlan.objects.filter(duration_days__lt=membership.plan.duration_days).order_by('-duration_days')
        return lower_plans.first() if lower_plans.exists() else None

    def get_membership_summary(self):
        membership = self.active_membership
        if not membership:
            return None
        return {
            'plan': membership.plan.name,
            'expiry_date': membership.end_date,
            'status': membership.status,
            'amount': membership.final_amount,
        }


class MemberDeleteRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name='delete_requests',
    )
    requested_by = models.ForeignKey(
        'accounts.UserAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='member_delete_requests',
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        'accounts.UserAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='member_delete_request_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_comments = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Member Delete Request'
        verbose_name_plural = 'Member Delete Requests'

    def __str__(self):
        return f'Delete request for {self.member.full_name} ({self.get_status_display()})'
