from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum, F, ExpressionWrapper, DecimalField
from .models import Customer
from .forms import CustomerForm
from authentication.decorators import executive_required
from billing.models import Invoice
from payments.models import Payment

@login_required
@executive_required
def customer_list(request):
    """View for listing all customers."""
    customers = Customer.objects.all().order_by('name')
    
    # Calculate pending amount for each customer
    for customer in customers:
        # Get pending payments (invoices that are not fully paid)
        pending_payments = Invoice.objects.filter(
            customer=customer
        ).exclude(
            Q(status='paid') | Q(status='cancelled') | Q(status='draft')
        ).annotate(
            calculated_amount_due=ExpressionWrapper(
                F('total') - F('amount_paid'),
                output_field=DecimalField()
            )
        )
        
        # Calculate total pending amount and store in a temporary attribute
        customer.pending_amount = pending_payments.aggregate(total=Sum('calculated_amount_due'))['total'] or 0
    
    return render(request, 'customers/customer_list.html', {'customers': customers})

@login_required
@executive_required
def customer_create(request):
    """View for creating a new customer."""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer created successfully!')
            return redirect('customer_list')
    else:
        form = CustomerForm()
    
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Create Customer'})

@login_required
@executive_required
def customer_update(request, pk):
    """View for updating an existing customer."""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated successfully!')
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Update Customer'})

@login_required
@executive_required
def customer_detail(request, pk):
    """View for displaying customer details."""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Get all invoices for this customer
    invoices = Invoice.objects.filter(customer=customer).order_by('-created_at')
    
    # Get pending payments (invoices that are not fully paid)
    pending_payments = invoices.exclude(
        Q(status='paid') | Q(status='cancelled') | Q(status='draft')
    ).annotate(
        calculated_amount_due=ExpressionWrapper(
            F('total') - F('amount_paid'),
            output_field=DecimalField()
        )
    ).order_by('payment_due_date')
    
    # Get recent activities (5 most recent invoices or payments)
    recent_activities = []
    
    # Add recent invoices
    for invoice in invoices[:5]:
        recent_activities.append({
            'type': 'invoice',
            'date': invoice.created_at,
            'invoice': invoice,
            'description': f"Invoice #{invoice.invoice_number} created for ₹{invoice.total}"
        })
    
    # Add recent payments
    payments = Payment.objects.filter(customer=customer).order_by('-created_at')[:5]
    for payment in payments:
        recent_activities.append({
            'type': 'payment',
            'date': payment.created_at,
            'payment': payment,
            'description': f"Payment of ₹{payment.amount} made for Invoice #{payment.invoice.invoice_number}"
        })
    
    # Sort combined activities by date (most recent first) and limit to 5
    recent_activities.sort(key=lambda x: x['date'], reverse=True)
    recent_activities = recent_activities[:5]
    
    # Calculate total pending amount
    total_pending_amount = pending_payments.aggregate(total=Sum('calculated_amount_due'))['total'] or 0
    
    return render(request, 'customers/customer_detail.html', {
        'customer': customer,
        'invoices': invoices,
        'pending_payments': pending_payments,
        'recent_activities': recent_activities,
        'total_pending_amount': total_pending_amount,
    })

@login_required
@executive_required
def customer_search(request):
    """API view for searching customers by phone or name."""
    query = request.GET.get('q', '')
    
    if not query:
        return JsonResponse({'customers': []})
    
    # Search by phone or name
    customers = Customer.objects.filter(
        Q(phone__icontains=query) | Q(name__icontains=query)
    )[:10]
    
    customer_list = []
    for customer in customers:
        customer_list.append({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'customer_type': customer.get_customer_type_display(),
            'pending_amount': float(customer.total_pending_amount),
            'credit_limit': float(customer.credit_limit),
            'is_credit_limit_exceeded': customer.is_credit_limit_exceeded,
        })
    
    return JsonResponse({'customers': customer_list})
