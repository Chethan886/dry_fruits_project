from django import forms
from django.utils import timezone
from datetime import timedelta
from .models import Payment, Reminder

class PaymentForm(forms.ModelForm):
    """Form for creating and updating payments."""
    class Meta:
        model = Payment
        fields = ['amount', 'payment_method', 'reference_number', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reference number (optional)'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes...'}),
        }

class ReminderForm(forms.ModelForm):
    """Form for creating and updating reminders."""
    class Meta:
        model = Reminder
        fields = ['reminder_type', 'notes']
        widgets = {
            'reminder_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes...'}),
        }

class PaymentSearchForm(forms.Form):
    """Form for searching and filtering payments."""
    STATUS_CHOICES = (
        ('', 'All Statuses'),
    ) + Payment.STATUS_CHOICES
    
    PAYMENT_METHOD_CHOICES = (
        ('', 'All Payment Methods'),
    ) + Payment.PAYMENT_METHOD_CHOICES
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by invoice # or customer...'})
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set default date range to last 30 days
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        self.fields['date_from'].initial = thirty_days_ago
        self.fields['date_to'].initial = today

class PendingPaymentSearchForm(forms.Form):
    """Form for searching and filtering pending payments."""
    OVERDUE_CHOICES = (
        ('', 'All'),
        ('overdue', 'Overdue'),
        ('due_soon', 'Due Soon'),
    )
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by invoice # or customer...'})
    )
    overdue_status = forms.ChoiceField(
        choices=OVERDUE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    min_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min Amount', 'step': '0.01'})
    )
    max_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max Amount', 'step': '0.01'})
    )
