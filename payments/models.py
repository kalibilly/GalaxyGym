import re
import logging
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Invoice(TimeStampedModel):
    STATUS_UNPAID = 'unpaid'
    STATUS_PARTIAL = 'partial'
    STATUS_PAID = 'paid'
    STATUS_OVERDUE = 'overdue'

    STATUS_CHOICES = [
        (STATUS_UNPAID, 'Unpaid'),
        (STATUS_PARTIAL, 'Partial'),
        (STATUS_PAID, 'Paid'),
        (STATUS_OVERDUE, 'Overdue'),
    ]

    PAYMENT_STATUS_PAID = 'paid'
    PAYMENT_STATUS_PENDING = 'pending'
    PAYMENT_STATUS_NOT_PAID = 'not_paid'

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_PAID, 'Paid'),
        (PAYMENT_STATUS_PENDING, 'Pending'),
        (PAYMENT_STATUS_NOT_PAID, 'Not Paid'),
    ]

    invoice_no = models.CharField(max_length=32, unique=True)
    member = models.ForeignKey(
        'members.Member',
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    membership = models.ForeignKey(
        'memberships.Membership',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    membership_plan = models.ForeignKey(
        'memberships.MembershipPlan',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='invoices_by_plan',
    )
    membership_end_date = models.DateField(null=True, blank=True)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(default=timezone.localdate)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_STATUS_PENDING,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNPAID)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-invoice_date', 'invoice_no']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'

    def __str__(self):
        return f'{self.invoice_no} — {self.member.full_name}'

    @property
    def status_badge_class(self):
        return {
            self.STATUS_PARTIAL: 'warning',
            self.STATUS_PAID: 'success',
            self.STATUS_OVERDUE: 'danger',
        }.get(self.status, 'secondary')

    @classmethod
    def get_next_invoice_no(cls):
        prefix = 'INV-'
        latest = cls.objects.order_by('-invoice_no').first()
        if not latest or not latest.invoice_no:
            return f'{prefix}0001'

        match = re.search(r'(\d+)$', latest.invoice_no)
        if not match:
            return f'{prefix}0001'

        next_number = int(match.group(1)) + 1
        return f'{prefix}{next_number:04d}'

    def clean(self):
        subtotal = self.subtotal or Decimal('0.00')
        discount_amount = self.discount_amount or Decimal('0.00')
        total_amount = self.total_amount or Decimal('0.00')
        paid_amount = self.paid_amount or Decimal('0.00')
        balance_amount = self.balance_amount or Decimal('0.00')

        if self.invoice_date and self.membership_end_date and self.membership_end_date < self.invoice_date:
            raise ValidationError('Membership end date cannot be earlier than membership start date.')

        if self.due_date and self.invoice_date and self.due_date < self.invoice_date:
            raise ValidationError('Invoice due date cannot be earlier than the invoice date.')

        if subtotal < 0 or discount_amount < 0 or total_amount < 0 or paid_amount < 0 or balance_amount < 0:
            raise ValidationError('Invoice amounts cannot be negative.')

        if discount_amount > subtotal:
            raise ValidationError('Discount cannot be greater than subtotal.')

        expected_total = subtotal + (self.tax_amount or Decimal('0.00')) - discount_amount
        if total_amount != expected_total:
            raise ValidationError(f'Total amount must be equal to subtotal + tax - discount ({expected_total}).')

        if balance_amount != (total_amount - paid_amount):
            raise ValidationError('Pending amount must be equal to total amount minus paid amount.')

    def get_paid_amount(self):
        if not self.pk:
            return self.paid_amount or Decimal('0.00')
        total = self.payments.aggregate(total=models.Sum('amount_paid'))['total']
        return total or Decimal('0.00')

    def derive_status(self):
        if self.total_amount <= 0:
            return self.STATUS_PAID

        paid = self.get_paid_amount()
        balance = self.total_amount - paid
        today = timezone.localdate()

        if balance <= 0:
            return self.STATUS_PAID

        if self.pending_payment_status == self.PAYMENT_STATUS_PAID:
            return self.STATUS_PAID
        if self.pending_payment_status == self.PAYMENT_STATUS_NOT_PAID and self.due_date < today:
            return self.STATUS_OVERDUE
        if paid > 0:
            return self.STATUS_PARTIAL
        return self.STATUS_UNPAID

    def refresh_balance(self):
        self.paid_amount = self.get_paid_amount()
        self.balance_amount = self.total_amount - self.paid_amount
        self.status = self.derive_status()
        super().save(update_fields=['paid_amount', 'balance_amount', 'status'])

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            self.invoice_no = self.get_next_invoice_no()

        self.subtotal = self.subtotal or Decimal('0.00')
        self.discount_amount = self.discount_amount or Decimal('0.00')
        self.tax_amount = self.tax_amount or Decimal('0.00')

        if self.pk:
            self.paid_amount = self.get_paid_amount()
        else:
            self.paid_amount = self.paid_amount or Decimal('0.00')

        self.total_amount = max(
            self.subtotal + self.tax_amount - self.discount_amount,
            Decimal('0.00')
        )
        self.balance_amount = max(self.total_amount - self.paid_amount, Decimal('0.00'))
        self.status = self.derive_status()

        self.full_clean()
        # detect status change
        old_status = None
        if self.pk:
            try:
                old = Invoice.objects.filter(pk=self.pk).first()
                if old:
                    old_status = old.status
            except Exception:
                old_status = None

        super().save(*args, **kwargs)

        # If invoice just moved to overdue, push expired access to devices
        try:
            if self.status == self.STATUS_OVERDUE and old_status != self.STATUS_OVERDUE:
                # run a best-effort push to all AIFACE devices
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
                        logger.exception('Failed to push overdue expiry to device %s', getattr(device, 'serial_number', device.pk))
        except Exception:
            # never fail invoice save due to sync issues
            pass


class Payment(TimeStampedModel):
    PAYMENT_CASH = 'cash'
    PAYMENT_UPI = 'upi'
    PAYMENT_BANK = 'bank_transfer'
    PAYMENT_ONLINE = 'online'

    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_UPI, 'UPI'),
        (PAYMENT_BANK, 'Bank Transfer'),
        (PAYMENT_ONLINE, 'Online'),
    ]

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    member = models.ForeignKey(
        'members.Member',
        on_delete=models.PROTECT,
        related_name='payments',
    )
    payment_date = models.DateField(default=timezone.localdate)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_CASH)
    transaction_reference = models.CharField(max_length=128, blank=True)
    received_by = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'

    def __str__(self):
        return f'{self.member.full_name} — {self.amount_paid} on {self.payment_date}'

    def clean(self):
        if self.amount_paid <= 0:
            raise ValidationError('Payment amount must be greater than zero.')
        if self.invoice and self.member != self.invoice.member:
            raise ValidationError('Payment member must match the invoice member.')

        if self.invoice and self.invoice.pk:
            outstanding = self.invoice.balance_amount or Decimal('0.00')
            if self.pk:
                original_amount = Payment.objects.filter(pk=self.pk).values_list('amount_paid', flat=True).first() or Decimal('0.00')
                outstanding += original_amount
            if self.amount_paid > outstanding:
                raise ValidationError('Payment amount cannot exceed the invoice balance.')

    def save(self, *args, **kwargs):
        if self.invoice and not self.member:
            self.member = self.invoice.member
        self.clean()
        super().save(*args, **kwargs)
        self.invoice.refresh_balance()
