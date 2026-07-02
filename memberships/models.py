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
        return self.DURATION_LEVELS.get(self.duration_months, 0)

    @property
    def cardio_label(self):
        return self.CARDIO_LABELS[self.cardio_included]

    @property
    def allow_partial_payment(self):
        return self.duration_months != 1

    @property
    def payment_rule_label(self):
        return 'Full payment only' if not self.allow_partial_payment else 'Partial payment allowed'

    @classmethod
    def default_plan_name(cls, duration_days, cardio_included):
        duration_months = duration_days // 30
        variant = 'With Cardio' if cardio_included else 'Without Cardio'
        return f'{duration_months} month{"s" if duration_months != 1 else ""} {variant}'

    @classmethod
    def get_default_plans(cls):
        return [
            {'duration_days': 30, 'cardio_included': False, 'price': Decimal('800'), 'description': '1 month membership without cardio.'},
            {'duration_days': 30, 'cardio_included': True, 'price': Decimal('1000'), 'description': '1 month membership with cardio.'},
            {'duration_days': 90, 'cardio_included': False, 'price': Decimal('2400'), 'description': '3 month membership without cardio.'},
            {'duration_days': 90, 'cardio_included': True, 'price': Decimal('3000'), 'description': '3 month membership with cardio.'},
            {'duration_days': 180, 'cardio_included': False, 'price': Decimal('4800'), 'description': '6 month membership without cardio.'},
            {'duration_days': 180, 'cardio_included': True, 'price': Decimal('6000'), 'description': '6 month membership with cardio.'},
            {'duration_days': 360, 'cardio_included': False, 'price': Decimal('9600'), 'description': '12 month membership without cardio.'},
            {'duration_days': 360, 'cardio_included': True, 'price': Decimal('12000'), 'description': '12 month membership with cardio.'},
        ]

    @classmethod
    def sync_default_plans(cls):
        for plan_data in cls.get_default_plans():
            name = cls.default_plan_name(plan_data['duration_days'], plan_data['cardio_included'])
            defaults = {
                'name': name,
                'price': plan_data['price'],
                'description': plan_data.get('description', ''),
                'is_active': True,
            }
            plan, created = cls.objects.update_or_create(
                duration_days=plan_data['duration_days'],
                cardio_included=plan_data['cardio_included'],
                defaults=defaults,
            )
            if not created and (plan.name != name or plan.price != plan_data['price'] or plan.is_active is not True):
                plan.name = name
                plan.price = plan_data['price']
                plan.is_active = True
                plan.description = plan_data.get('description', '')
                plan.save()

    def clean(self):
        if self.duration_days not in self.ALLOWED_DURATION_DAYS:
            raise ValidationError({'duration_days': 'Duration must be 30, 90, 180, or 360 days.'})

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.default_plan_name(self.duration_days, self.cardio_included)
        self.clean()
        super().save(*args, **kwargs)


class Membership(TimeStampedModel):
    PAYMENT_STATUS_UNPAID = 'unpaid'
    PAYMENT_STATUS_PARTIAL = 'partial'
    PAYMENT_STATUS_PAID = 'paid'

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_UNPAID, 'Unpaid'),
        (PAYMENT_STATUS_PARTIAL, 'Partial'),
        (PAYMENT_STATUS_PAID, 'Paid'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_EXPIRING_SOON = 'expiring_soon'
    STATUS_EXPIRED = 'expired'
    STATUS_FROZEN = 'frozen'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXPIRING_SOON, 'Expiring Soon'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_FROZEN, 'Frozen'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    serial_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    member = models.ForeignKey(
        'members.Member',
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    plan = models.ForeignKey(
        MembershipPlan,
        on_delete=models.PROTECT,
        related_name='memberships',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    membership_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_STATUS_UNPAID,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    renewed_from = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='renewals',
    )
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date', 'member']
        verbose_name = 'Membership'
        verbose_name_plural = 'Memberships'

    def __str__(self):
        serial = self.serial_number or 'Membership'
        return f'{serial} — {self.member} — {self.plan}'

    @classmethod
    def get_next_serial_number(cls):
        prefix = 'MBR-'
        latest = cls.objects.exclude(serial_number__isnull=True).exclude(serial_number='').order_by('-id').first()
        if not latest or not latest.serial_number:
            return f'{prefix}0001'

        match = re.search(r'(\d+)$', latest.serial_number)
        if not match:
            return f'{prefix}0001'

        next_number = int(match.group(1)) + 1
        return f'{prefix}{next_number:04d}'

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date must be on or after start date.')
        if self.membership_amount < 0:
            raise ValidationError({'membership_amount': 'Membership amount cannot be negative.'})
        if self.discount_amount < 0:
            raise ValidationError({'discount_amount': 'Discount cannot be negative.'})
        if self.discount_amount > self.membership_amount:
            raise ValidationError({'discount_amount': 'Discount cannot be greater than membership amount.'})

    def derive_status(self):
        if self.status in {self.STATUS_FROZEN, self.STATUS_CANCELLED}:
            return self.status

        today = date.today()
        if self.end_date < today:
            return self.STATUS_EXPIRED

        if self.end_date - today <= timedelta(days=7):
            return self.STATUS_EXPIRING_SOON

        return self.STATUS_ACTIVE

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = self.get_next_serial_number()
        self.final_amount = self.membership_amount - self.discount_amount
        old_status = None
        if self.pk:
            try:
                old = Membership.objects.filter(pk=self.pk).first()
                if old:
                    old_status = old.status
            except Exception:
                old_status = None

        self.status = self.derive_status()
        super().save(*args, **kwargs)

        # If membership just expired, push expiry to biometric devices
        try:
            if self.status == self.STATUS_EXPIRED and old_status != self.STATUS_EXPIRED:
                from attendance.models import BiometricDevice
                from attendance.biometric import BiometricSyncService

                devices = BiometricDevice.objects.filter(
                    device_type=BiometricDevice.DeviceType.AIFACE,
                    is_active=True,
                )
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
            self.STATUS_FROZEN: 'secondary',
            self.STATUS_CANCELLED: 'dark',
        }.get(self.status, 'secondary')
