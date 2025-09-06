from django.contrib import admin
from .models import Customer

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'customer_type', 'credit_limit', 'created_at')
    list_filter = ('customer_type',)
    search_fields = ('name', 'phone', 'email')
    readonly_fields = ('created_at', 'updated_at')
