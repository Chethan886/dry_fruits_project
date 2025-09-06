from django.db import models
from django.db.models import Sum
from django.utils import timezone
import logging

class Customer(models.Model):
    CUSTOMER_TYPE_CHOICES = (
        ('retail', 'Retail'),
        ('wholesale', 'Wholesale'),
        ('distributor', 'Distributor'),
    )
    
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPE_CHOICES, default='retail')
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    @property
    def total_pending_amount(self):
        from billing.models import Invoice
        from decimal import Decimal
        
        logger = logging.getLogger(__name__)
        
        logger.info(f"[v0] Calculating total_pending_amount for customer: {self.name} (ID: {self.id})")
        
        # Get all unpaid invoices for this customer
        unpaid_invoices = Invoice.objects.filter(
            customer=self,
            status__in=['pending_payment', 'overdue']
        )
        
        logger.info(f"[v0] Found {unpaid_invoices.count()} unpaid invoices")
        
        total_pending = Decimal('0.00')
        for invoice in unpaid_invoices:
            # Calculate amount still owed (total - amount_paid)
            amount_owed = invoice.total - (invoice.amount_paid or Decimal('0.00'))
            logger.info(f"[v0] Invoice {invoice.invoice_number}: total={invoice.total}, paid={invoice.amount_paid}, owed={amount_owed}")
            if amount_owed > 0:
                total_pending += amount_owed
        
        logger.info(f"[v0] Final total_pending_amount: {total_pending}")
        return total_pending
    
    @property
    def is_credit_limit_exceeded(self):
        return self.total_pending_amount > self.credit_limit
    
    @property
    def available_credit(self):
        logger = logging.getLogger(__name__)
        
        logger.info(f"[v0] Calculating available_credit for customer: {self.name}")
        logger.info(f"[v0] Credit limit: {self.credit_limit}")
        logger.info(f"[v0] Total pending: {self.total_pending_amount}")
        
        available = self.credit_limit - self.total_pending_amount
        result = max(0, available)
        
        logger.info(f"[v0] Available credit result: {result}")
        return result
