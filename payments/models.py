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
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(default=timezone.localdate)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNPAID)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-invoice_date', 'invoice_no']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'

    def __str__(self):
        return f'{self.invoice_no} — {self.member.full_name}'

    def clean(self):
        if self.due_date < self.invoice_date:
            raise ValidationError('Invoice due date cannot be earlier than the invoice date.')
        if self.subtotal < 0 or self.discount_amount < 0 or self.tax_amount < 0:
            raise ValidationError('Invoice amounts cannot be negative.')

    def get_paid_amount(self):
        if not self.pk:
            return self.paid_amount
        total = self.payments.aggregate(total=models.Sum('amount_paid'))['total']
        return total or 0

    def get_balance_amount(self):
        return self.total_amount - self.get_paid_amount()

    def derive_status(self):
        if self.total_amount <= 0:
            return self.STATUS_PAID

        paid = self.get_paid_amount()
        balance = self.total_amount - paid
        today = timezone.localdate()

        if balance <= 0:
            return self.STATUS_PAID
        if self.due_date < today:
            return self.STATUS_OVERDUE
        if paid > 0:
            return self.STATUS_PARTIAL
        return self.STATUS_UNPAID

    def refresh_balance(self):
        self.paid_amount = self.get_paid_amount()
        self.balance_amount = self.total_amount - self.paid_amount
        self.status = self.derive_status()
        self.save(update_fields=['paid_amount', 'balance_amount', 'status'])

    def save(self, *args, **kwargs):
        self.clean()
        self.total_amount = max(self.subtotal + self.tax_amount - self.discount_amount, 0)
        if self.pk:
            self.paid_amount = self.get_paid_amount()
        self.balance_amount = self.total_amount - self.paid_amount
        self.status = self.derive_status()
        super().save(*args, **kwargs)


class Payment(TimeStampedModel):
    PAYMENT_CASH = 'cash'
    PAYMENT_UPI = 'upi'
    PAYMENT_BANK = 'bank_transfer'

    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_UPI, 'UPI'),
        (PAYMENT_BANK, 'Bank Transfer'),
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
            outstanding = self.invoice.get_balance_amount()
            if self.pk:
                original_amount = Payment.objects.filter(pk=self.pk).values_list('amount_paid', flat=True).first() or 0
                outstanding += original_amount
            if self.amount_paid > outstanding:
                raise ValidationError('Payment amount cannot exceed the invoice balance.')

    def save(self, *args, **kwargs):
        if self.invoice and not self.member:
            self.member = self.invoice.member
        self.clean()
        super().save(*args, **kwargs)
        self.invoice.refresh_balance()
