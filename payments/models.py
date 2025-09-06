from django.db import models
from django.core.validators import MinValueValidator
from authentication.models import User
from customers.models import Customer
from billing.models import Invoice

class Payment(models.Model):
    """Model for storing payment information."""
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('upi', 'UPI/Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('cheque', 'Cheque'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )
    
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Payment of ₹{self.amount} for Invoice #{self.invoice.invoice_number}"
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        """Override save method to update invoice amount_paid."""
        super().save(*args, **kwargs)
        
        # Update invoice amount_paid
        if self.status == 'completed':
            invoice = self.invoice
            total_paid = Payment.objects.filter(
                invoice=invoice, 
                status='completed'
            ).aggregate(models.Sum('amount'))['amount__sum'] or 0
            
            invoice.amount_paid = total_paid
            
            # Update invoice status
            if total_paid >= invoice.total:
                invoice.status = 'paid'
            elif total_paid > 0:
                invoice.status = 'partially_paid'
            else:
                invoice.status = 'issued'
            
            invoice.save()

class Reminder(models.Model):
    """Model for storing payment reminder information."""
    REMINDER_TYPE_CHOICES = (
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('call', 'Phone Call'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    )
    
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reminders')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_reminders')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.get_reminder_type_display()} Reminder for Invoice #{self.invoice.invoice_number}"
    
    class Meta:
        ordering = ['-created_at']
