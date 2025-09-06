from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDay, Coalesce
from datetime import timedelta, datetime
import json
import logging
from .decorators import admin_required
from .forms import CustomUserCreationForm, CustomAuthenticationForm, CustomUserChangeForm, generate_random_password
from .models import User
from customers.models import Customer
from billing.models import Invoice
from payments.models import Payment

# Set up logging
logger = logging.getLogger(__name__)

def login_view(request):
    """View for user login."""
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.first_name}!")
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid email or password.")
        else:
            messages.error(request, "Invalid email or password.")
    else:
        form = CustomAuthenticationForm()
    return render(request, 'authentication/login.html', {'form': form})

def logout_view(request):
    """View for user logout."""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('login')

@login_required
def dashboard(request):
    """Dashboard view with enhanced data."""
    today = timezone.now()
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_of_prev_month = (start_of_month - timedelta(days=1)).replace(day=1)
    
    # Get date range for the last 7 days
    end_date = today.date()
    start_date = end_date - timedelta(days=7)
    
    # Get total sales for current month
    current_month_sales = Invoice.objects.filter(
        created_at__gte=start_of_month,
        created_at__lte=today
    ).aggregate(total_sales=Coalesce(Sum('total'), 0, output_field=DecimalField()))['total_sales']
    
    prev_month_sales = Invoice.objects.filter(
        created_at__gte=start_of_prev_month,
        created_at__lt=start_of_month
    ).aggregate(total_sales=Coalesce(Sum('total'), 0, output_field=DecimalField()))['total_sales']
    
    # Calculate sales growth
    sales_growth = 0
    if prev_month_sales > 0:
        sales_growth = round(((current_month_sales - prev_month_sales) / prev_month_sales) * 100)
    elif current_month_sales > 0 and prev_month_sales == 0:
        sales_growth = 100  # If there were no sales last month but there are this month, that's 100% growth
    
    # Get all invoices with pending payments
    # First, let's log all invoices to see what we're working with
    all_invoices = Invoice.objects.all()
    logger.info(f"Total invoices: {all_invoices.count()}")
    for invoice in all_invoices:
        logger.info(f"Invoice {invoice.id}: total={invoice.total}, amount_paid={invoice.amount_paid}, status={invoice.status}")
    
    # Get pending payments - directly calculate unpaid amounts
    # This query finds all invoices where total > amount_paid
    pending_invoices = Invoice.objects.filter(
        total__gt=F('amount_paid')
    )
    
    # Log the pending invoices for debugging
    logger.info(f"Pending invoices count: {pending_invoices.count()}")
    for invoice in pending_invoices:
        pending_amount = invoice.total - invoice.amount_paid
        logger.info(f"Pending invoice {invoice.id}: total={invoice.total}, amount_paid={invoice.amount_paid}, pending={pending_amount}")
    
    # Calculate total pending amount
    current_pending = 0
    for invoice in pending_invoices:
        current_pending += (invoice.total - invoice.amount_paid)
    
    # Get previous month's pending payments
    prev_pending_invoices = Invoice.objects.filter(
        created_at__lt=start_of_month,
        total__gt=F('amount_paid')
    )
    
    prev_pending = 0
    for invoice in prev_pending_invoices:
        prev_pending += (invoice.total - invoice.amount_paid)
    
    # Calculate pending growth
    pending_growth = 0
    if prev_pending > 0:
        pending_growth = round(((current_pending - prev_pending) / prev_pending) * 100)
    elif current_pending > 0 and prev_pending == 0:
        pending_growth = 100  # If there were no pending payments last month but there are this month
    
    # Get customer count - current vs previous month
    total_customers = Customer.objects.count()
    prev_month_customers = Customer.objects.filter(
        created_at__lt=start_of_month
    ).count()
    
    # Calculate customer growth
    customer_growth = 0
    if prev_month_customers > 0:
        customer_growth = round(((total_customers - prev_month_customers) / prev_month_customers) * 100)
    elif total_customers > 0 and prev_month_customers == 0:
        customer_growth = 100  # If there were no customers last month but there are this month
    
    # Get daily sales data for the last 7 days (similar to sales report)
    daily_sales = Invoice.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).annotate(
        date=TruncDay('created_at')
    ).values('date').annotate(
        total_sale=Coalesce(Sum('total'), 0, output_field=DecimalField()),
        bills=Count('id'),
        cash_sale=Coalesce(Sum('total', filter=Q(payment_type='cash')), 0, output_field=DecimalField()),
        upi_sale=Coalesce(Sum('total', filter=Q(payment_type='upi')), 0, output_field=DecimalField()),
        credit_sale=Coalesce(Sum('total', filter=Q(payment_type='credit')), 0, output_field=DecimalField())
    ).order_by('date')
    
    # Format data for charts
    sales_labels = []
    sales_values = []
    
    # Create a dictionary to store sales by date
    sales_by_date = {item['date'].strftime('%Y-%m-%d'): item for item in daily_sales}
    
    # Fill in missing dates with zero values
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        sales_labels.append(current_date.strftime('%Y-%m-%d'))
        
        if date_str in sales_by_date:
            sales_values.append(float(sales_by_date[date_str]['total_sale']))
        else:
            sales_values.append(0)
            
        current_date += timedelta(days=1)
    
    # Get total sales by payment type for all time
    payment_totals = Invoice.objects.aggregate(
        cash=Coalesce(Sum('total', filter=Q(payment_type='cash')), 0, output_field=DecimalField()),
        upi=Coalesce(Sum('total', filter=Q(payment_type='upi')), 0, output_field=DecimalField()),
        credit=Coalesce(Sum('total', filter=Q(payment_type='credit')), 0, output_field=DecimalField())
    )
    
    total_sales_all = payment_totals['cash'] + payment_totals['upi'] + payment_totals['credit']
    
    # Calculate percentages for pie chart
    payment_percentages = {
        'cash': round((payment_totals['cash'] / total_sales_all * 100) if total_sales_all > 0 else 0, 1),
        'upi': round((payment_totals['upi'] / total_sales_all * 100) if total_sales_all > 0 else 0, 1),
        'credit': round((payment_totals['credit'] / total_sales_all * 100) if total_sales_all > 0 else 0, 1)
    }
    
    # Get customer type data for chart
    customer_types = Customer.objects.values('customer_type').annotate(count=Count('id'))
    
    customer_labels = []
    customer_values = []
    
    if customer_types:
        for type_data in customer_types:
            customer_labels.append(type_data['customer_type'] or 'Unspecified')
            customer_values.append(type_data['count'])
    
    # Get total bills
    total_bills = Invoice.objects.count()
    
    # Prepare table data for sales report
    table_data = []
    for item in daily_sales:
        table_data.append({
            'date': item['date'].strftime('%Y-%m-%d'),
            'bills': item['bills'],
            'total_sale': item['total_sale'],
            'cash_sale': item['cash_sale'],
            'upi_sale': item['upi_sale'],
            'credit_sale': item['credit_sale']
        })
    
    # Debug information for pending payments
    debug_info = {
        'all_invoices': [
            {
                'id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'total': float(invoice.total),
                'amount_paid': float(invoice.amount_paid),
                'pending': float(invoice.total - invoice.amount_paid),
                'status': invoice.status,
                'payment_type': invoice.payment_type,
                'created_at': invoice.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            for invoice in all_invoices
        ],
        'pending_invoices': [
            {
                'id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'total': float(invoice.total),
                'amount_paid': float(invoice.amount_paid),
                'pending': float(invoice.total - invoice.amount_paid),
                'status': invoice.status,
                'payment_type': invoice.payment_type,
                'created_at': invoice.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            for invoice in pending_invoices
        ],
        'current_pending': float(current_pending),
        'prev_pending': float(prev_pending)
    }
    
    # Log debug info - convert to JSON safely
    logger.info(f"Debug info: {json.dumps(debug_info)}")
    
    context = {
        'today': today,
        'total_sales': total_sales_all,
        'sales_growth': sales_growth,
        'pending_payments': current_pending,
        'pending_growth': pending_growth,
        'total_customers': total_customers,
        'customer_growth': customer_growth,
        'sales_data': True if sales_values and any(sales_values) else False,
        'sales_labels': json.dumps(sales_labels),
        'sales_values': json.dumps(sales_values),
        'customer_data': True if customer_values and any(customer_values) else False,
        'customer_labels': json.dumps(customer_labels),
        'customer_values': json.dumps(customer_values),
        'total_bills': total_bills,
        'table_data': table_data,
        'payment_totals': payment_totals,
        'payment_percentages': payment_percentages,
        'debug_info': debug_info,  # For debugging
    }
    
    return render(request, 'dashboard.html', context)

@login_required
@admin_required
def user_list(request):
    """View for listing all users."""
    users = User.objects.all()
    return render(request, 'authentication/user_list.html', {'users': users})

@login_required
@admin_required
def user_create(request):
    """View for creating a new user."""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "User created successfully!")
            return redirect('user_list')
    else:
        form = CustomUserCreationForm()
    return render(request, 'authentication/user_create.html', {'form': form})

@login_required
@admin_required
def user_edit(request, pk):
    """View for editing a user."""
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"User {user.email} updated successfully!")
            return redirect('user_list')
    else:
        form = CustomUserChangeForm(instance=user)
    return render(request, 'authentication/user_edit.html', {'form': form, 'user_obj': user})

@login_required
@admin_required
def user_reset_password(request, pk):
    """View for resetting a user's password."""
    user = get_object_or_404(User, pk=pk)
    new_password = generate_random_password()
    user.set_password(new_password)
    user.save()
    messages.success(request, f"Password for {user.email} has been reset. New password: {new_password}")
    return redirect('user_list')

@login_required
@admin_required
def user_toggle_active(request, pk):
    """View for toggling a user's active status."""
    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save()
    status = "activated" if user.is_active else "deactivated"
    messages.success(request, f"User {user.email} has been {status}.")
    return redirect('user_list')
