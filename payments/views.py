from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum, F, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.core.paginator import Paginator
from authentication.decorators import executive_required
from customers.models import Customer
from billing.models import Invoice
from .models import Payment, Reminder
from .forms import PaymentForm, ReminderForm, PaymentSearchForm, PendingPaymentSearchForm
from datetime import timedelta

@login_required
@executive_required
def payment_list(request):
    """View for listing all payments."""
    form = PaymentSearchForm(request.GET)
    payments = Payment.objects.all()
    
    if form.is_valid():
        query = form.cleaned_data.get('query')
        status = form.cleaned_data.get('status')
        payment_method = form.cleaned_data.get('payment_method')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        
        if query:
            payments = payments.filter(
                Q(invoice__invoice_number__icontains=query) | 
                Q(customer__name__icontains=query) |
                Q(customer__phone__icontains=query)
            )
        
        if status:
            payments = payments.filter(status=status)
        
        if payment_method:
            payments = payments.filter(payment_method=payment_method)
        
        if date_from:
            payments = payments.filter(created_at__date__gte=date_from)
        
        if date_to:
            payments = payments.filter(created_at__date__lte=date_to)
    
    # Get summary statistics
    total_amount = payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    
    # Paginate the results
    paginator = Paginator(payments, 10)  # Show 10 payments per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'payments/payment_list.html', {
        'page_obj': page_obj,
        'form': form,
        'total_amount': total_amount,
    })

@login_required
@executive_required
def pending_payment_list(request):
    """View for listing pending payments."""
    form = PendingPaymentSearchForm(request.GET)
    
    # Get invoices with pending payments - anything that's not paid or cancelled
    invoices = Invoice.objects.exclude(
        Q(status='paid') | Q(status='cancelled') | Q(status='draft')
    ).order_by('-created_at')
    
    # Annotate with calculated_amount_due instead of amount_due to avoid property conflict
    invoices = invoices.annotate(
        calculated_amount_due=ExpressionWrapper(
            F('total') - F('amount_paid'),
            output_field=DecimalField()
        )
    )
    
    if form.is_valid():
        query = form.cleaned_data.get('query')
        overdue_status = form.cleaned_data.get('overdue_status')
        min_amount = form.cleaned_data.get('min_amount')
        max_amount = form.cleaned_data.get('max_amount')
        
        if query:
            invoices = invoices.filter(
                Q(invoice_number__icontains=query) | 
                Q(customer__name__icontains=query) |
                Q(customer__phone__icontains=query)
            )
        
        if overdue_status:
            today = timezone.now().date()
            if overdue_status == 'overdue':
                invoices = invoices.filter(payment_due_date__lt=today)
            elif overdue_status == 'due_soon':
                seven_days_later = today + timedelta(days=7)
                invoices = invoices.filter(payment_due_date__gte=today, payment_due_date__lte=seven_days_later)
        
        if min_amount:
            invoices = invoices.filter(calculated_amount_due__gte=min_amount)
        
        if max_amount:
            invoices = invoices.filter(calculated_amount_due__lte=max_amount)
    
    # Get summary statistics using the annotated field
    total_pending = invoices.aggregate(total=Sum('calculated_amount_due'))['total'] or 0

    # For overdue and due soon, we need to filter first then sum
    today = timezone.now().date()
    overdue_invoices = invoices.filter(payment_due_date__lt=today)
    overdue_amount = overdue_invoices.aggregate(total=Sum('calculated_amount_due'))['total'] or 0
    overdue_count = overdue_invoices.count()

    due_soon_invoices = invoices.filter(
        payment_due_date__gte=today,
        payment_due_date__lte=today + timedelta(days=7)
    )
    due_soon_amount = due_soon_invoices.aggregate(total=Sum('calculated_amount_due'))['total'] or 0
    due_soon_count = due_soon_invoices.count()

    # Also count invoices with no payment due date set
    no_due_date_invoices = invoices.filter(payment_due_date__isnull=True)
    no_due_date_count = no_due_date_invoices.count()
    no_due_date_amount = no_due_date_invoices.aggregate(total=Sum('calculated_amount_due'))['total'] or 0
    
    # Paginate the results
    paginator = Paginator(invoices, 10)  # Show 10 invoices per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'payments/pending_payments.html', {
        'page_obj': page_obj,
        'form': form,
        'total_pending': total_pending,
        'overdue_amount': overdue_amount,
        'due_soon_amount': due_soon_amount,
        'overdue_count': overdue_count,
        'due_soon_count': due_soon_count,
        'no_due_date_count': no_due_date_count,
        'no_due_date_amount': no_due_date_amount,
        'invoices': invoices,
        'today': today
    })

@login_required
@executive_required
def payment_create(request, invoice_id):
    """View for creating a new payment."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    if invoice.status == 'paid':
        messages.warning(request, 'This invoice is already fully paid.')
        return redirect('invoice_detail', pk=invoice.id)
    
    if invoice.status == 'cancelled':
        messages.warning(request, 'Cannot add payment to a cancelled invoice.')
        return redirect('invoice_detail', pk=invoice.id)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data.get('amount')
            
            # Check if payment amount is valid
            if amount > invoice.amount_due:
                messages.error(request, f'Payment amount (₹{amount}) exceeds the amount due (₹{invoice.amount_due}).')
                return render(request, 'payments/payment_form.html', {
                    'form': form,
                    'invoice': invoice,
                    'title': 'Record Payment',
                })
            
            # Create the payment
            payment = form.save(commit=False)
            payment.invoice = invoice
            payment.customer = invoice.customer
            payment.created_by = request.user
            payment.save()
            
            messages.success(request, 'Payment recorded successfully.')
            return redirect('invoice_detail', pk=invoice.id)
    else:
        # Set initial amount to the amount due
        form = PaymentForm(initial={'amount': invoice.amount_due})
    
    return render(request, 'payments/payment_form.html', {
        'form': form,
        'invoice': invoice,
        'title': 'Record Payment',
    })

@login_required
@executive_required
def payment_detail(request, pk):
    """View for displaying payment details."""
    payment = get_object_or_404(Payment, pk=pk)
    
    return render(request, 'payments/payment_detail.html', {
        'payment': payment,
    })

@login_required
@executive_required
def payment_update(request, pk):
    """View for updating a payment."""
    payment = get_object_or_404(Payment, pk=pk)
    invoice = payment.invoice
    
    if payment.status != 'pending':
        messages.warning(request, 'Only pending payments can be updated.')
        return redirect('payment_detail', pk=payment.id)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            amount = form.cleaned_data.get('amount')
            
            # Check if payment amount is valid
            if amount > invoice.amount_due + payment.amount:
                messages.error(request, f'Payment amount (₹{amount}) exceeds the amount due (₹{invoice.amount_due + payment.amount}).')
                return render(request, 'payments/payment_form.html', {
                    'form': form,
                    'invoice': invoice,
                    'payment': payment,
                    'title': 'Update Payment',
                })
            
            form.save()
            messages.success(request, 'Payment updated successfully.')
            return redirect('payment_detail', pk=payment.id)
    else:
        form = PaymentForm(instance=payment)
    
    return render(request, 'payments/payment_form.html', {
        'form': form,
        'invoice': invoice,
        'payment': payment,
        'title': 'Update Payment',
    })

@login_required
@executive_required
def payment_cancel(request, pk):
    """View for cancelling a payment."""
    payment = get_object_or_404(Payment, pk=pk)
    
    if payment.status == 'cancelled':
        messages.warning(request, 'This payment is already cancelled.')
        return redirect('payment_detail', pk=payment.id)
    
    if request.method == 'POST':
        payment.status = 'cancelled'
        payment.save()
        messages.success(request, 'Payment cancelled successfully.')
        return redirect('payment_detail', pk=payment.id)
    
    return render(request, 'payments/payment_confirm_cancel.html', {
        'payment': payment,
    })

@login_required
@executive_required
def reminder_create(request, invoice_id):
    """View for creating a new reminder."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    if invoice.status == 'paid':
        messages.warning(request, 'This invoice is already fully paid.')
        return redirect('invoice_detail', pk=invoice.id)
    
    if invoice.status == 'cancelled':
        messages.warning(request, 'Cannot send reminder for a cancelled invoice.')
        return redirect('invoice_detail', pk=invoice.id)
    
    if request.method == 'POST':
        form = ReminderForm(request.POST)
        if form.is_valid():
            reminder = form.save(commit=False)
            reminder.invoice = invoice
            reminder.customer = invoice.customer
            reminder.created_by = request.user
            reminder.save()
            
            # In a real application, you would send the actual reminder here
            # For now, we'll just mark it as sent
            reminder.status = 'sent'
            reminder.sent_at = timezone.now()
            reminder.save()
            
            messages.success(request, 'Reminder sent successfully.')
            return redirect('invoice_detail', pk=invoice.id)
    else:
        form = ReminderForm()
    
    return render(request, 'payments/reminder_form.html', {
        'form': form,
        'invoice': invoice,
        'title': 'Send Reminder',
    })

@login_required
@executive_required
def customer_payment_history(request, customer_id):
    """View for displaying a customer's payment history."""
    customer = get_object_or_404(Customer, pk=customer_id)
    payments = Payment.objects.filter(customer=customer)
    invoices = Invoice.objects.filter(customer=customer)
    
    # Get summary statistics
    total_invoiced = invoices.aggregate(total=Sum('total'))['total'] or 0
    total_paid = payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    total_pending = total_invoiced - total_paid
    
    return render(request, 'payments/customer_payment_history.html', {
        'customer': customer,
        'payments': payments,
        'invoices': invoices,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'total_pending': total_pending,
    })

@login_required
@executive_required
def bulk_reminder(request):
    """View for sending reminders to multiple customers."""
    if request.method == 'POST':
        invoice_ids = request.POST.getlist('invoice_ids')
        reminder_type = request.POST.get('reminder_type')
        notes = request.POST.get('notes')
        
        if not invoice_ids:
            messages.error(request, 'No invoices selected.')
            return redirect('pending_payment_list')
        
        # Create reminders for each selected invoice
        for invoice_id in invoice_ids:
            invoice = get_object_or_404(Invoice, pk=invoice_id)
            
            reminder = Reminder(
                invoice=invoice,
                customer=invoice.customer,
                reminder_type=reminder_type,
                notes=notes,
                created_by=request.user,
                status='sent',
                sent_at=timezone.now()
            )
            reminder.save()
        
        messages.success(request, f'Reminders sent to {len(invoice_ids)} customers.')
        return redirect('pending_payment_list')
    
    return redirect('pending_payment_list')
