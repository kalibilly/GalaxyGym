import re
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import ActiveStatusModel, TimeStampedModel


class MembershipPlan(TimeStampedModel, ActiveStatusModel):
    CARDIO_LABELS = {
        False: 'Without Cardio',
        True: 'With Cardio',
    }
    DURATION_LEVELS = {
        1: 1,
        3: 2,
        6: 3,
        12: 4,
    }
    ALLOWED_DURATION_DAYS = {30, 90, 180, 360}

    name = models.CharField(max_length=120, unique=True)
    duration_days = models.PositiveIntegerField(default=30)
    cardio_included = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['duration_days', 'cardio_included']
        verbose_name = 'Membership Plan'
        verbose_name_plural = 'Membership Plans'

    def __str__(self):
        return self.name

    @property
    def duration_months(self):
        return self.duration_days // 30

    @property
    def level(self):
        months = self.duration_months
        return self.DURATION_LEVELS.get(months, 1)

    @property
    def cardio_label(self):
        return self.CARDIO_LABELS.get(self.cardio_included, 'Without Cardio')

    @property
    def allow_partial_payment(self):
        return self.duration_days >= 90


class Membership(TimeStampedModel):
    STATUS_ACTIVE = 'active'
    STATUS_EXPIRING_SOON = 'expiring_soon'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXPIRING_SOON, 'Expiring Soon'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    PAYMENT_STATUS_PAID = 'paid'
    PAYMENT_STATUS_PARTIAL = 'partial'
    PAYMENT_STATUS_UNPAID = 'unpaid'

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_PAID, 'Fully Paid'),
        (PAYMENT_STATUS_PARTIAL, 'Partially Paid'),
        (PAYMENT_STATUS_UNPAID, 'Unpaid'),
    ]

    entry_number = models.CharField(max_length=50, blank=True, null=True)
    member = models.ForeignKey('members.Member', on_delete=models.CASCADE, related_name='memberships')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name='memberships')
    start_date = models.DateField()
    end_date = models.DateField()
    price_before_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_UNPAID)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date', '-created_at']
        verbose_name = 'Membership Fee Record'
        verbose_name_plural = 'Membership Fee Records'

    def __str__(self):
        return f"{self.member.full_name} - {self.plan.name} ({self.start_date} to {self.end_date})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError('The membership start date cannot be after the end date.')

    def save(self, *args, **kwargs):
        self.full_clean()
        
        if self.price_before_discount == 0 and self.plan:
            self.price_before_discount = self.plan.price
        
        self.total_amount = self.price_before_discount - self.discount_amount
        
        # Keep internal auto-calculated helper values in sync
        today = date.today()
        if self.status != self.STATUS_CANCELLED:
            if today > self.end_date:
                self.status = self.STATUS_EXPIRED
            elif today >= (self.end_date - timedelta(days=7)):
                self.status = self.STATUS_EXPIRING_SOON
            else:
                self.status = self.STATUS_ACTIVE

        super().save(*args, **kwargs)
        
        try:
            if hasattr(self.member, 'sync_biometric_status_and_push'):
                self.member.sync_biometric_status_and_push()
            else:
                from attendance.models import BiometricDevice
                from attendance.biometric import BiometricSyncService
                devices = BiometricDevice.objects.filter(device_type=BiometricDevice.DeviceType.AIFACE, is_active=True)
                member = self.member
                for device in devices:
                    try:
                        BiometricSyncService(device).update_employee_ex(member)
                    except Exception:
                        logger = logging.getLogger('biometric')
                        logger.exception('Failed to push membership expiry to device %s', getattr(device, 'serial_number', device.pk))
        except Exception:
            pass

    @property
    def duration_days_planned(self):
        return (self.end_date - self.start_date).days

    @property
    def is_current(self):
        return self.status == self.STATUS_ACTIVE

    @property
    def membership_level(self):
        return self.plan.level

    @property
    def cardio_label(self):
        return self.plan.cardio_label

    @property
    def needs_renewal_action(self):
        return self.status in {self.STATUS_EXPIRING_SOON, self.STATUS_EXPIRED}

    @property
    def renewal_badge_class(self):
        return {
            self.STATUS_ACTIVE: 'success',
            self.STATUS_EXPIRING_SOON: 'warning',
            self.STATUS_EXPIRED: 'danger',
            self.STATUS_CANCELLED: 'secondary',
        }.get(self.status, 'info')

    @property
    def balance_amount(self):
        return max(Decimal('0.00'), self.total_amount - self.paid_amount)
