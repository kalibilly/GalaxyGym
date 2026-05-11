from django.conf import settings
from django.db import models
from django.utils import timezone


class DailyFinancialReport(models.Model):
    report_date = models.DateField(unique=True)
    total_invoices = models.PositiveIntegerField(default=0)
    total_payments = models.PositiveIntegerField(default=0)
    total_paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pending_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    overdue_invoice_count = models.PositiveIntegerField(default=0)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='generated_reports',
    )

    class Meta:
        ordering = ['-report_date']
        verbose_name = 'Daily Financial Report'
        verbose_name_plural = 'Daily Financial Reports'

    def __str__(self):
        return f'Report {self.report_date.strftime("%Y-%m-%d")}'
