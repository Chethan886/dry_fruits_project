from django.contrib import admin
from .models import Payment, Reminder

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'customer', 'amount', 'payment_method', 'status', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('invoice__invoice_number', 'customer__name', 'customer__phone')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'customer', 'reminder_type', 'status', 'created_at', 'sent_at')
    list_filter = ('status', 'reminder_type', 'created_at')
    search_fields = ('invoice__invoice_number', 'customer__name', 'customer__phone')
    readonly_fields = ('created_at', 'sent_at')
