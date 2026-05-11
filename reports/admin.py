from django.contrib import admin

from .models import DailyFinancialReport


@admin.register(DailyFinancialReport)
class DailyFinancialReportAdmin(admin.ModelAdmin):
    list_display = ('report_date', 'total_invoices', 'total_payments', 'total_paid_amount', 'pending_balance', 'overdue_invoice_count', 'generated_at')
    list_filter = ('report_date',)
    search_fields = ('report_date',)
    readonly_fields = ('generated_at',)
    ordering = ('-report_date',)
