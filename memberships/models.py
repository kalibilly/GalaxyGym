from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import ActiveStatusModel, TimeStampedModel


class MembershipPlan(TimeStampedModel, ActiveStatusModel):
    name = models.CharField(max_length=120, unique=True)
    duration_days = models.PositiveIntegerField(default=30)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Membership Plan'
        verbose_name_plural = 'Membership Plans'

    def __str__(self):
        return self.name


class Membership(TimeStampedModel):
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
        return f'{self.member} — {self.plan} ({self.start_date} to {self.end_date})'

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date must be on or after start date.')

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
        self.final_amount = self.membership_amount - self.discount_amount
        self.status = self.derive_status()
        super().save(*args, **kwargs)

    @property
    def duration_days_planned(self):
        return (self.end_date - self.start_date).days

    @property
    def is_current(self):
        return self.status == self.STATUS_ACTIVE
