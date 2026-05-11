from django.contrib import admin

from .models import Invoice, Payment


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_no',
        'member',
        'membership',
        'invoice_date',
        'due_date',
        'total_amount',
        'paid_amount',
        'balance_amount',
        'status',
    )
    list_filter = ('status', 'invoice_date', 'due_date')
    search_fields = ('invoice_no', 'member__full_name', 'member__member_id')
    readonly_fields = ('paid_amount', 'balance_amount', 'status', 'created_at', 'updated_at')
    raw_id_fields = ('member', 'membership')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'payment_date',
        'member',
        'invoice',
        'amount_paid',
        'payment_mode',
        'transaction_reference',
        'received_by',
    )
    list_filter = ('payment_mode', 'payment_date')
    search_fields = ('member__full_name', 'member__member_id', 'invoice__invoice_no', 'transaction_reference')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('member', 'invoice')
