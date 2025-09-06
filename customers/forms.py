from django import forms
from .models import Customer

class CustomerForm(forms.ModelForm):
    """Form for creating and updating customers."""
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address', 'customer_type', 'credit_limit']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer Name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email (Optional)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Address (Optional)', 'rows': 3}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Credit Limit'}),
        }
