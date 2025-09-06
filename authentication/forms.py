from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, UserChangeForm, PasswordResetForm
from .models import User
import secrets
import string

class CustomUserCreationForm(UserCreationForm):
    """Form for creating new users."""
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to form fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            if field_name == 'email':
                field.widget.attrs['placeholder'] = 'Email'
            elif field_name == 'first_name':
                field.widget.attrs['placeholder'] = 'First Name'
            elif field_name == 'last_name':
                field.widget.attrs['placeholder'] = 'Last Name'
            elif field_name == 'role':
                field.widget.attrs['class'] = 'form-select'
            elif field_name in ['password1', 'password2']:
                field.widget.attrs['placeholder'] = 'Password' if field_name == 'password1' else 'Confirm Password'

class CustomUserChangeForm(UserChangeForm):
    """Form for updating a user."""
    password = None  # Remove password field from the form
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role', 'is_active')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to form fields
        for field_name, field in self.fields.items():
            if field_name == 'is_active':
                field.widget.attrs['class'] = 'form-check-input'
            else:
                field.widget.attrs['class'] = 'form-control'

class CustomAuthenticationForm(AuthenticationForm):
    """Custom authentication form."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to form fields
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['username'].widget.attrs['placeholder'] = 'Email'
        self.fields['password'].widget.attrs['class'] = 'form-control'
        self.fields['password'].widget.attrs['placeholder'] = 'Password'

def generate_random_password(length=12):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password
