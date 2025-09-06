from django import forms
from django.utils import timezone
from datetime import timedelta

class SalesReportForm(forms.Form):
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date() - timedelta(days=30)
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date()
    )
    GROUPING_CHOICES = (
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    )
    grouping = forms.ChoiceField(
        choices=GROUPING_CHOICES,
        initial='day',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    PAYMENT_TYPE_CHOICES = (
        ('all', 'All Payment Types'),
        ('cash', 'Cash Only'),
        ('upi', 'UPI/Card Only'),
        ('credit', 'Credit Only'),
    )
    payment_type = forms.ChoiceField(
        choices=PAYMENT_TYPE_CHOICES,
        initial='all',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Add customer filter if needed
    customer = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer name (optional)'})
    )

class ProductReportForm(forms.Form):
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date() - timedelta(days=30)
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date()
    )
    SORT_CHOICES = (
        ('quantity', 'Quantity Sold'),
        ('revenue', 'Revenue'),
        ('name', 'Product Name'),
    )
    sort_by = forms.ChoiceField(
        choices=SORT_CHOICES,
        initial='quantity',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class CustomerReportForm(forms.Form):
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date() - timedelta(days=90)
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date()
    )
    CUSTOMER_TYPE_CHOICES = (
        ('all', 'All Customers'),
        ('retail', 'Retail'),
        ('wholesale', 'Wholesale'),
    )
    customer_type = forms.ChoiceField(
        choices=CUSTOMER_TYPE_CHOICES,
        initial='all',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    SORT_CHOICES = (
        ('purchases', 'Purchase Value'),
        ('name', 'Customer Name'),
        ('last_purchase', 'Last Purchase Date'),
    )
    sort_by = forms.ChoiceField(
        choices=SORT_CHOICES,
        initial='purchases',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    include_inactive = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

class CreditReportForm(forms.Form):
    include_paid = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    SORT_CHOICES = (
        ('amount', 'Amount Due'),
        ('name', 'Customer Name'),
        ('due_date', 'Due Date'),
    )
    sort_by = forms.ChoiceField(
        choices=SORT_CHOICES,
        initial='amount',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class InventoryReportForm(forms.Form):
    SORT_CHOICES = (
        ('name', 'Product Name'),
        ('stock', 'Stock Level'),
        ('value', 'Inventory Value'),
    )
    sort_by = forms.ChoiceField(
        choices=SORT_CHOICES,
        initial='name',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    show_zero_stock = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

class ExportDataForm(forms.Form):
    FORMAT_CHOICES = (
        ('excel', 'Excel (.xlsx)'),
        ('csv', 'CSV'),
        ('pdf', 'PDF'),
    )
    format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        initial='excel',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
