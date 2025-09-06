from django.db import models
from django.core.validators import MinValueValidator
from authentication.models import User

class Report(models.Model):
    """Model for storing generated reports."""
    REPORT_TYPE_CHOICES = (
        ('sales', 'Sales Report'),
        ('product', 'Product Report'),
        ('customer', 'Customer Report'),
        ('payment', 'Payment Report'),
        ('credit', 'Credit Report'),
    )
    
    FORMAT_CHOICES = (
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    )
    
    name = models.CharField(max_length=100)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    file = models.FileField(upload_to='reports/')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    parameters = models.JSONField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"
    
    class Meta:
        ordering = ['-created_at']
