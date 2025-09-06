import datetime
from datetime import timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField, Value, OuterRef, Subquery
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, Coalesce
from django.http import HttpResponse
from django.utils import timezone
import json
import csv
import xlwt
import logging

# Set up logging
logger = logging.getLogger(__name__)

from authentication.decorators import executive_required
from billing.models import Invoice, InvoiceItem
from customers.models import Customer
from products.models import Product, ProductQuality
from .forms import (
    SalesReportForm, ProductReportForm, CustomerReportForm, 
    CreditReportForm, InventoryReportForm, ExportDataForm
)

@login_required
def report_list(request):
    """View for report list."""
    return render(request, 'reports/report_list.html')

@login_required
def sales_report(request):
    """View for sales report."""
    # Default to last 30 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    grouping = 'day'
    payment_type = 'all'
    customer_filter = ''
    
    # Process form data
    if request.method == 'POST':
        form = SalesReportForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['date_from']
            end_date = form.cleaned_data['date_to']
            grouping = form.cleaned_data['grouping']
            payment_type = form.cleaned_data['payment_type']
            customer_filter = form.cleaned_data['customer']
            
            # If exporting to Excel
            if 'export' in request.POST:
                return export_sales_report(request, start_date, end_date, grouping, payment_type, customer_filter)
    else:
        # Check for quick filter in GET parameters
        quick_filter = request.GET.get('quick_filter', '')
        if quick_filter == 'today':
            start_date = end_date = timezone.now().date()
        elif quick_filter == 'yesterday':
            start_date = end_date = timezone.now().date() - timedelta(days=1)
        elif quick_filter == 'this_week':
            today = timezone.now().date()
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif quick_filter == 'this_month':
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        elif quick_filter == 'last_month':
            today = timezone.now().date()
            if today.month == 1:
                start_date = today.replace(year=today.year-1, month=12, day=1)
                end_date = today.replace(year=today.year-1, month=12, day=31)
            else:
                start_date = today.replace(month=today.month-1, day=1)
                last_day = 31
                if today.month-1 in [4, 6, 9, 11]:
                    last_day = 30
                elif today.month-1 == 2:
                    if today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0):
                        last_day = 29
                    else:
                        last_day = 28
                end_date = today.replace(month=today.month-1, day=last_day)
        
        form = SalesReportForm(initial={
            'date_from': start_date,
            'date_to': end_date,
            'grouping': grouping,
            'payment_type': payment_type,
            'customer': customer_filter
        })
    
    # Get all invoices except drafts
    invoices = Invoice.objects.exclude(status='draft')
    
    # Apply date range filter
    invoices = invoices.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    
    # Apply payment type filter
    if payment_type != 'all':
        invoices = invoices.filter(payment_type=payment_type)
    
    # Apply customer filter if provided
    if customer_filter:
        invoices = invoices.filter(customer__name__icontains=customer_filter)
    
    # Determine the grouping function based on user selection
    if grouping == 'week':
        trunc_func = TruncWeek('created_at')
    elif grouping == 'month':
        trunc_func = TruncMonth('created_at')
    else:  # default to day
        trunc_func = TruncDay('created_at')
    
    # Group by selected period
    sales_data = invoices.annotate(
        period=trunc_func
    ).values('period').annotate(
        total_sale=Sum('total', default=0),
        bills=Count('id'),
        cash_sale=Sum(
            F('total'),
            filter=Q(payment_type='cash'),
            default=0
        ),
        upi_sale=Sum(
            F('total'),
            filter=Q(payment_type='upi'),
            default=0
        ),
        credit_sale=Sum(
            F('total'),
            filter=Q(payment_type='credit'),
            default=0
        )
    ).order_by('period')
    
    # Format data for template
    table_data = []
    for entry in sales_data:
        if entry['period']:
            if grouping == 'day':
                formatted_date = entry['period'].strftime('%Y-%m-%d')
            elif grouping == 'week':
                formatted_date = f"Week {entry['period'].strftime('%U')}, {entry['period'].strftime('%Y')}"
            else:  # month
                formatted_date = entry['period'].strftime('%B %Y')
                
            table_data.append({
                'date': formatted_date,
                'bills': entry['bills'],
                'total_sale': entry['total_sale'] or 0,
                'cash_sale': entry['cash_sale'] or 0,
                'upi_sale': entry['upi_sale'] or 0,
                'credit_sale': entry['credit_sale'] or 0
            })
    
    # Calculate totals
    total_bills = sum(entry['bills'] for entry in table_data) if table_data else 0
    total_sales = sum(entry['total_sale'] for entry in table_data) if table_data else 0
    total_cash = sum(entry['cash_sale'] for entry in table_data) if table_data else 0
    total_upi = sum(entry['upi_sale'] for entry in table_data) if table_data else 0
    total_credit = sum(entry['credit_sale'] for entry in table_data) if table_data else 0
    
    # Calculate percentages for payment modes
    total_paid = total_cash + total_upi + total_credit
    if total_paid > 0:
        cash_percent = round((total_cash / total_paid) * 100)
        upi_percent = round((total_upi / total_paid) * 100)
        credit_percent = round((total_credit / total_paid) * 100)
    else:
        cash_percent = upi_percent = credit_percent = 0
    
    # Format date range for display
    if start_date == end_date:
        date_range_display = start_date.strftime('%d %b %Y')
    else:
        date_range_display = f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"
    
    context = {
        'form': form,
        'table_data': table_data,
        'total_bills': total_bills,
        'total_sales': total_sales,
        'total_cash': total_cash,
        'total_upi': total_upi,
        'total_credit': total_credit,
        'cash_percent': cash_percent,
        'upi_percent': upi_percent,
        'credit_percent': credit_percent,
        'date_range_display': date_range_display,
        'start_date': start_date,
        'end_date': end_date
    }
    
    return render(request, 'reports/sales_report.html', context)

def export_sales_report(request, start_date=None, end_date=None, grouping='day', payment_type='all', customer_filter=''):
    """Export sales report to Excel."""
    # Get all invoices except drafts
    invoices = Invoice.objects.exclude(status='draft')
    
    # Apply date range filter if provided
    if start_date and end_date:
        invoices = invoices.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
    
    # Apply payment type filter
    if payment_type != 'all':
        invoices = invoices.filter(payment_type=payment_type)
    
    # Apply customer filter if provided
    if customer_filter:
        invoices = invoices.filter(customer__name__icontains=customer_filter)
    
    # Determine the grouping function based on user selection
    if grouping == 'week':
        trunc_func = TruncWeek('created_at')
    elif grouping == 'month':
        trunc_func = TruncMonth('created_at')
    else:  # default to day
        trunc_func = TruncDay('created_at')
    
    # Group by selected period
    sales_data = invoices.annotate(
        period=trunc_func
    ).values('period').annotate(
        bills=Count('id'),
        total_sale=Sum('total', default=0),
        cash_sale=Sum('total', filter=Q(payment_type='cash'), default=0),
        upi_sale=Sum('total', filter=Q(payment_type='upi'), default=0),
        credit_sale=Sum('total', filter=Q(payment_type='credit'), default=0)
    ).order_by('period')
    
    # Create workbook and add a worksheet
    workbook = xlwt.Workbook(encoding='utf-8')
    worksheet = workbook.add_sheet('Sales Report')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    date_style = xlwt.easyxf('align: wrap on, vert centre, horiz center', num_format_str='DD-MM-YYYY')
    amount_style = xlwt.easyxf('align: wrap on, vert centre, horiz right', num_format_str='#,##0.00')
    
    # Write header row
    headers = [
        'Date', 'Bills Generated', 'Total Sale', 
        'Cash', 'UPI/Card', 'Credit'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_style)
        worksheet.col(col).width = 4000  # Set column width
    
    # Write data rows
    for row, entry in enumerate(sales_data, 1):
        if grouping == 'day':
            date_value = entry['period'].date()
        else:
            # For week and month, just use the string representation
            date_value = str(entry['period'])
        
        worksheet.write(row, 0, date_value, date_style if isinstance(date_value, (datetime.date, datetime.datetime)) else None)
        worksheet.write(row, 1, entry['bills'])
        worksheet.write(row, 2, float(entry['total_sale'] or 0), amount_style)
        worksheet.write(row, 3, float(entry['cash_sale'] or 0), amount_style)
        worksheet.write(row, 4, float(entry['upi_sale'] or 0), amount_style)
        worksheet.write(row, 5, float(entry['credit_sale'] or 0), amount_style)
    
    # Write totals row
    row = len(sales_data) + 1
    worksheet.write(row, 0, 'Total', header_style)
    worksheet.write(row, 1, sum(entry['bills'] for entry in sales_data), header_style)
    worksheet.write(row, 2, float(sum(entry['total_sale'] or 0 for entry in sales_data)), amount_style)
    worksheet.write(row, 3, float(sum(entry['cash_sale'] or 0 for entry in sales_data)), amount_style)
    worksheet.write(row, 4, float(sum(entry['upi_sale'] or 0 for entry in sales_data)), amount_style)
    worksheet.write(row, 5, float(sum(entry['credit_sale'] or 0 for entry in sales_data)), amount_style)
    
    # Create HTTP response with Excel file
    response = HttpResponse(content_type='application/ms-excel')
    current_date = timezone.now().strftime('%Y-%m-%d')
    
    # Include filter information in filename
    filename_parts = ['Sales_Report']
    if start_date and end_date:
        if start_date == end_date:
            filename_parts.append(start_date.strftime('%Y-%m-%d'))
        else:
            filename_parts.append(f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}")
    
    if payment_type != 'all':
        filename_parts.append(payment_type)
    
    filename_parts.append(current_date)
    filename = '_'.join(filename_parts) + '.xls'
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    
    return response

def product_sales_report(request):
    """View for product-wise sales report."""
    # Default to last 30 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    sort_by = 'quantity'  # Default sort by quantity sold
    product_search = ''
    variant_filter = ''
    min_quantity = ''
    
    # Process form data
    if request.method == 'POST':
        form = ProductReportForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['date_from']
            end_date = form.cleaned_data['date_to']
            sort_by = form.cleaned_data['sort_by']
            
            # Get additional filter parameters
            product_search = request.POST.get('product_search', '')
            variant_filter = request.POST.get('variant_filter', '')
            min_quantity = request.POST.get('min_quantity', '')
            
            # If exporting to Excel
            if 'export' in request.POST:
                return export_product_report(
                    request, 
                    start_date, 
                    end_date, 
                    sort_by, 
                    product_search, 
                    variant_filter, 
                    min_quantity
                )
    else:
        # Check for quick filter in GET parameters
        quick_filter = request.GET.get('quick_filter', '')
        if quick_filter == 'today':
            start_date = end_date = timezone.now().date()
        elif quick_filter == 'yesterday':
            start_date = end_date = timezone.now().date() - timedelta(days=1)
        elif quick_filter == 'this_week':
            today = timezone.now().date()
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif quick_filter == 'this_month':
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        elif quick_filter == 'last_month':
            today = timezone.now().date()
            if today.month == 1:
                start_date = today.replace(year=today.year-1, month=12, day=1)
                end_date = today.replace(year=today.year-1, month=12, day=31)
            else:
                start_date = today.replace(month=today.month-1, day=1)
                last_day = 31
                if today.month-1 in [4, 6, 9, 11]:
                    last_day = 30
                elif today.month-1 == 2:
                    if today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0):
                        last_day = 29
                    else:
                        last_day = 28
                end_date = today.replace(month=today.month-1, day=last_day)
        
        form = ProductReportForm(initial={
            'date_from': start_date,
            'date_to': end_date,
            'sort_by': sort_by
        })
    
    # Get invoices within date range
    invoices = Invoice.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).exclude(status='draft')
    
    # Get invoice items from these invoices
    invoice_items = InvoiceItem.objects.filter(
        invoice__in=invoices
    )
    
    # Apply product search filter if provided
    if product_search:
        invoice_items = invoice_items.filter(product__name__icontains=product_search)
    
    # Apply variant filter if provided
    if variant_filter:
        invoice_items = invoice_items.filter(product_quality__quality=variant_filter)
    
    # Aggregate data by product and variant
    product_data = invoice_items.values(
        'product__name', 'product_quality__quality'
    ).annotate(
        product=F('product__name'),
        variant=F('product_quality__quality'),
        quantity_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price'))
    )
    
    # Apply minimum quantity filter if provided
    if min_quantity and min_quantity.isdigit():
        min_qty = float(min_quantity)
        product_data = product_data.filter(quantity_sold__gte=min_qty)
    
    # Sort data based on user selection
    if sort_by == 'quantity':
        product_data = product_data.order_by('-quantity_sold')
    elif sort_by == 'revenue':
        product_data = product_data.order_by('-revenue')
    else:  # name
        product_data = product_data.order_by('product')
    
    # Convert to list for template
    table_data = list(product_data)
    
    # Calculate totals
    total_quantity = sum(item['quantity_sold'] for item in table_data) if table_data else 0
    total_revenue = sum(item['revenue'] for item in table_data) if table_data else 0
    
    # Prepare chart data for top 5 products
    top_products = sorted(table_data, key=lambda x: x['revenue'], reverse=True)[:5]
    chart_data = [{'name': item['product'], 'value': float(item['revenue'])} for item in top_products]
    
    # Get all unique variants for the filter dropdown
    all_variants = ProductQuality.objects.values_list('quality', flat=True).distinct()
    
    context = {
        'form': form,
        'table_data': table_data,
        'total_quantity': total_quantity,
        'total_revenue': total_revenue,
        'start_date': start_date,
        'end_date': end_date,
        'chart_data': json.dumps(chart_data),
        'product_search': product_search,
        'variant_filter': variant_filter,
        'min_quantity': min_quantity,
        'all_variants': all_variants,
    }
    
    return render(request, 'reports/product_sales_report.html', context)

def customer_summary_report(request):
    """View for customer summary report."""
    # Default to last 90 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=90)
    customer_type = 'all'
    sort_by = 'purchases'
    include_inactive = False
    
    # Process form data
    if request.method == 'POST':
        form = CustomerReportForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['date_from']
            end_date = form.cleaned_data['date_to']
            customer_type = form.cleaned_data['customer_type']
            sort_by = form.cleaned_data['sort_by']
            include_inactive = form.cleaned_data['include_inactive']
            
            # If exporting to Excel
            if 'export' in request.POST:
                return export_customer_report(request, start_date, end_date, customer_type, sort_by, include_inactive)
    else:
        form = CustomerReportForm(initial={
            'date_from': start_date,
            'date_to': end_date,
            'customer_type': customer_type,
            'sort_by': sort_by,
            'include_inactive': include_inactive
        })
    
    # Start with all customers
    customers = Customer.objects.all()
    
    # Filter by customer type if specified
    if customer_type != 'all':
        customers = customers.filter(customer_type=customer_type)
    
    # Filter out inactive customers if specified
    if not include_inactive:
        # Get customers with invoices in the date range
        active_customer_ids = Invoice.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values_list('customer_id', flat=True).distinct()
        
        customers = customers.filter(id__in=active_customer_ids)
    
    # Get invoices within date range
    invoices = Invoice.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).exclude(status='draft')
    
    # Debug: Log all invoices to see what's available
    logger.debug(f"Total invoices in date range: {invoices.count()}")
    for inv in invoices:
        logger.debug(f"Invoice {inv.invoice_number}: payment_type={inv.payment_type}, status={inv.status}, total={inv.total}, amount_paid={inv.amount_paid}")
    
    # Aggregate customer data
    customer_data = []
    
    for customer in customers:
        # Get customer's invoices in the date range
        customer_invoices = invoices.filter(customer=customer)
        
        # Calculate metrics
        total_orders = customer_invoices.count()
        total_value = customer_invoices.aggregate(total=Sum('total'))['total'] or 0
        
        # Calculate pending payments - FIX: Include all invoices with amount_paid < total
        pending_payment = 0
        for invoice in customer_invoices:
            if invoice.total > invoice.amount_paid:
                pending_payment += (invoice.total - invoice.amount_paid)
        
        # Only include customers with orders in the period
        if total_orders > 0 or include_inactive:
            customer_data.append({
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'total_orders': total_orders,
                'total_value': total_value,
                'pending_payment': pending_payment
            })
    
    # Sort data based on user selection
    if sort_by == 'purchases':
        customer_data = sorted(customer_data, key=lambda x: x['total_value'], reverse=True)
    elif sort_by == 'name':
        customer_data = sorted(customer_data, key=lambda x: x['name'])
    elif sort_by == 'last_purchase':
        # This would require additional query to get last purchase date
        # For now, we'll just sort by total value
        customer_data = sorted(customer_data, key=lambda x: x['total_value'], reverse=True)
    
    # Calculate totals
    total_customers = len(customer_data)
    total_orders = sum(item['total_orders'] for item in customer_data)
    total_value = sum(item['total_value'] for item in customer_data)
    total_pending = sum(item['pending_payment'] for item in customer_data)
    
    # Prepare chart data for top 5 customers
    top_customers = sorted(customer_data, key=lambda x: x['total_value'], reverse=True)[:5]
    chart_data = []
    
    # Only add to chart data if there are values
    for item in top_customers:
        if item['total_value'] > 0:
            chart_data.append({
                'name': item['name'],
                'value': float(item['total_value'])
            })
    
    context = {
        'form': form,
        'table_data': customer_data,
        'total_customers': total_customers,
        'total_orders': total_orders,
        'total_value': total_value,
        'total_pending': total_pending,
        'start_date': start_date,
        'end_date': end_date,
        'chart_data': json.dumps(chart_data)
    }
    
    return render(request, 'reports/customer_summary_report.html', context)

@login_required
def credit_overview_report(request):
    """View for credit overview report."""
    # Default values
    sort_by = 'due_date'
    include_paid = False
    
    # Process form data
    if request.method == 'POST':
        form = CreditReportForm(request.POST)
        if form.is_valid():
            sort_by = form.cleaned_data['sort_by']
            include_paid = form.cleaned_data['include_paid']
            
            # If exporting to Excel
            if 'export' in request.POST:
                return export_credit_report(request, include_paid)
    else:
        form = CreditReportForm(initial={
            'sort_by': sort_by,
            'include_paid': include_paid
        })
    
    # Debug: Log all invoices to see what's available
    all_invoices = Invoice.objects.all()
    logger.debug(f"Total invoices in system: {all_invoices.count()}")
    for inv in all_invoices:
        logger.debug(f"Invoice {inv.invoice_number}: payment_type={inv.payment_type}, status={inv.status}, total={inv.total}, amount_paid={inv.amount_paid}")
    
    # Get all invoices with pending payments
    # We'll be more inclusive in our query to catch all possible pending payments
    invoices = Invoice.objects.all()
    
    # Log the query for debugging
    logger.debug(f"Initial query count: {invoices.count()}")
    
    # Filter out paid invoices if specified
    if not include_paid:
        # Only include invoices that are not fully paid
        invoices = invoices.exclude(status='paid')
        logger.debug(f"After excluding paid: {invoices.count()}")
    
    # Prepare data for template
    table_data = []
    
    for invoice in invoices:
        amount_due = invoice.total - invoice.amount_paid
        
        # Skip if there's no amount due and we're not including paid invoices
        if amount_due <= 0 and not include_paid:
            continue
        
        # Calculate days overdue
        days_overdue = 0
        due_date = invoice.payment_due_date or invoice.due_date
        if due_date and due_date < timezone.now().date():
            days_overdue = (timezone.now().date() - due_date).days
        
        # Determine status
        if invoice.status == 'paid':
            status = 'paid'
        elif amount_due == 0:
            status = 'paid'
        elif amount_due < invoice.total:
            status = 'partially_paid'
        elif days_overdue > 0:
            status = 'overdue'
        else:
            status = 'pending'
        
        # Only include credit invoices or invoices with pending payments
        if invoice.payment_type == 'credit' or amount_due > 0:
            table_data.append({
                'invoice_id': invoice.id,  # Add the invoice ID for URL reversing
                'invoice_number': invoice.invoice_number,
                'customer_name': invoice.customer.name,
                'customer_phone': invoice.customer.phone,
                'invoice_date': invoice.created_at,
                'due_date': due_date,
                'total_amount': invoice.total,
                'amount_paid': invoice.amount_paid,
                'amount_due': amount_due,
                'status': status,
                'days_overdue': days_overdue
            })
    
    logger.debug(f"Final table data count: {len(table_data)}")
    
    # Sort data based on user selection
    if sort_by == 'due_date':
        # Sort by due date, putting None values at the end
        table_data = sorted(table_data, key=lambda x: (x['due_date'] is None, x['due_date'] or datetime.max.date()))
    elif sort_by == 'amount':
        table_data = sorted(table_data, key=lambda x: x['amount_due'], reverse=True)
    elif sort_by == 'overdue':
        table_data = sorted(table_data, key=lambda x: x['days_overdue'], reverse=True)
    
    # Calculate totals
    total_invoices = len(table_data)
    total_amount = sum(item['total_amount'] for item in table_data)
    total_paid = sum(item['amount_paid'] for item in table_data)
    total_due = sum(item['amount_due'] for item in table_data)
    
    context = {
        'form': form,
        'table_data': table_data,
        'total_invoices': total_invoices,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_due': total_due
    }
    
    return render(request, 'reports/credit_overview_report.html', context)

def export_customer_report(request, start_date, end_date, customer_type, sort_by, include_inactive):
    """Export customer summary report to Excel."""
    # Start with all customers
    customers = Customer.objects.all()
    
    # Filter by customer type if specified
    if customer_type != 'all':
        customers = customers.filter(customer_type=customer_type)
    
    # Filter out inactive customers if specified
    if not include_inactive:
        # Get customers with invoices in the date range
        active_customer_ids = Invoice.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values_list('customer_id', flat=True).distinct()
        
        customers = customers.filter(id__in=active_customer_ids)
    
    # Get invoices within date range
    invoices = Invoice.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).exclude(status='draft')
    
    # Create workbook and add a worksheet
    workbook = xlwt.Workbook(encoding='utf-8')
    worksheet = workbook.add_sheet('Customer Summary')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    amount_style = xlwt.easyxf('align: wrap on, vert centre, horiz right', num_format_str='#,##0.00')
    
    # Write header row
    headers = [
        'Customer', 'Phone', 'Customer Type', 'Total Orders', 
        'Total Value (₹)', 'Pending Payment (₹)'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_style)
        worksheet.col(col).width = 4000  # Set column width
    
    # Write data rows
    row = 1
    for customer in customers:
        # Get customer's invoices in the date range
        customer_invoices = invoices.filter(customer=customer)
        
        # Calculate metrics
        total_orders = customer_invoices.count()
        total_value = customer_invoices.aggregate(total=Sum('total'))['total'] or 0
        pending_payment = customer_invoices.filter(
            payment_type='credit'
        ).exclude(
            status='paid'
        ).aggregate(
            pending=Sum(F('total') - F('amount_paid'))
        )['pending'] or 0
        
        # Only include customers with orders in the period
        if total_orders > 0 or include_inactive:
            worksheet.write(row, 0, customer.name)
            worksheet.write(row, 1, customer.phone)
            worksheet.write(row, 2, dict(Customer.CUSTOMER_TYPE_CHOICES).get(customer.customer_type, 'Unknown'))
            worksheet.write(row, 3, total_orders)
            worksheet.write(row, 4, float(total_value), amount_style)
            worksheet.write(row, 5, float(pending_payment), amount_style)
            row += 1
    
    # Write totals row
    worksheet.write(row, 0, 'Total', header_style)
    worksheet.write(row, 1, '', header_style)
    worksheet.write(row, 2, '', header_style)
    worksheet.write(row, 3, sum(invoices.values('customer').annotate(count=Count('id')).values_list('count', flat=True)))
    worksheet.write(row, 4, float(invoices.aggregate(total=Sum('total'))['total'] or 0), amount_style)
    worksheet.write(row, 5, float(
        invoices.filter(payment_type='credit').exclude(status='paid').aggregate(
            pending=Sum(F('total') - F('amount_paid'))
        )['pending'] or 0
    ), amount_style)
    
    # Create HTTP response with Excel file
    response = HttpResponse(content_type='application/ms-excel')
    current_date = timezone.now().strftime('%Y-%m-%d')
    response['Content-Disposition'] = f'attachment; filename="Customer_Summary_{current_date}.xls"'
    workbook.save(response)
    
    return response

def export_credit_report(request, include_paid=False):
    """Export credit report to Excel."""
    # Get invoices with credit payment type
    invoices = Invoice.objects.filter(payment_type='credit')
    
    if not include_paid:
        invoices = invoices.exclude(status='paid')
    
    # Create workbook and add a worksheet
    workbook = xlwt.Workbook(encoding='utf-8')
    worksheet = workbook.add_sheet('Credit Overview')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    date_style = xlwt.easyxf('align: wrap on, vert centre, horiz center', num_format_str='DD-MM-YYYY')
    amount_style = xlwt.easyxf('align: wrap on, vert centre, horiz right', num_format_str='#,##0.00')
    
    # Write header row
    headers = [
        'Invoice #', 'Customer', 'Phone', 'Invoice Date', 'Due Date', 
        'Total Amount', 'Amount Paid', 'Amount Due', 'Status', 'Days Overdue'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_style)
        worksheet.col(col).width = 4000  # Set column width
    
    # Write data rows
    for row, invoice in enumerate(invoices, 1):
        amount_due = invoice.total - invoice.amount_paid
        days_overdue = (timezone.now().date() - invoice.due_date).days if invoice.due_date and invoice.due_date < timezone.now().date() else 0
        
        worksheet.write(row, 0, invoice.invoice_number)
        worksheet.write(row, 1, invoice.customer.name)
        worksheet.write(row, 2, invoice.customer.phone)
        worksheet.write(row, 3, invoice.created_at.date(), date_style)
        worksheet.write(row, 4, invoice.payment_due_date or invoice.due_date or '', date_style)
        worksheet.write(row, 5, float(invoice.total), amount_style)
        worksheet.write(row, 6, float(invoice.amount_paid), amount_style)
        worksheet.write(row, 7, float(amount_due), amount_style)
        worksheet.write(row, 8, dict(Invoice.STATUS_CHOICES).get(invoice.status, invoice.status))
        worksheet.write(row, 9, days_overdue)
    
    # Create HTTP response with Excel file
    response = HttpResponse(content_type='application/ms-excel')
    current_date = timezone.now().strftime('%Y-%m-%d')
    response['Content-Disposition'] = f'attachment; filename="Credit_Overview_Report_{current_date}.xls"'
    workbook.save(response)
    
    return response

def export_product_report(request, start_date, end_date, sort_by, product_search='', variant_filter='', min_quantity=''):
    """Export product sales report to Excel."""
    # Get invoices within date range
    invoices = Invoice.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).exclude(status='draft')
    
    # Get invoice items from these invoices
    invoice_items = InvoiceItem.objects.filter(
        invoice__in=invoices
    )
    
    # Apply product search filter if provided
    if product_search:
        invoice_items = invoice_items.filter(product__name__icontains=product_search)
    
    # Apply variant filter if provided
    if variant_filter:
        invoice_items = invoice_items.filter(product_quality__quality=variant_filter)
    
    # Aggregate data by product and variant
    product_data = invoice_items.values(
        'product__name', 'product_quality__quality'
    ).annotate(
        product=F('product__name'),
        variant=F('product_quality__quality'),
        quantity_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price'))
    )
    
    # Apply minimum quantity filter if provided
    if min_quantity and min_quantity.isdigit():
        min_qty = float(min_quantity)
        product_data = product_data.filter(quantity_sold__gte=min_qty)
    
    # Sort data based on user selection
    if sort_by == 'quantity':
        product_data = product_data.order_by('-quantity_sold')
    elif sort_by == 'revenue':
        product_data = product_data.order_by('-revenue')
    else:  # name
        product_data = product_data.order_by('product')
    
    # Create workbook and add a worksheet
    workbook = xlwt.Workbook(encoding='utf-8')
    worksheet = workbook.add_sheet('Product Sales')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    amount_style = xlwt.easyxf('align: wrap on, vert centre, horiz right', num_format_str='#,##0.00')
    
    # Write header row
    headers = [
        'Product', 'Variant', 'Qty Sold (Kg)', 'Revenue (₹)'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_style)
        worksheet.col(col).width = 4000  # Set column width
    
    # Write data rows
    for row, item in enumerate(product_data, 1):
        worksheet.write(row, 0, item['product'])
        worksheet.write(row, 1, item['variant'] or 'Standard')
        worksheet.write(row, 2, float(item['quantity_sold']), amount_style)
        worksheet.write(row, 3, float(item['revenue']), amount_style)
    
    # Write totals row
    row = len(product_data) + 1
    worksheet.write(row, 0, 'Total', header_style)
    worksheet.write(row, 1, '', header_style)
    worksheet.write(row, 2, float(sum(item['quantity_sold'] for item in product_data)), amount_style)
    worksheet.write(row, 3, float(sum(item['revenue'] for item in product_data)), amount_style)
    
    # Create HTTP response with Excel file
    response = HttpResponse(content_type='application/ms-excel')
    current_date = timezone.now().strftime('%Y-%m-%d')
    
    # Include filter information in filename
    filename_parts = ['Product_Sales']
    if start_date and end_date:
        if start_date == end_date:
            filename_parts.append(start_date.strftime('%Y-%m-%d'))
        else:
            filename_parts.append(f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}")
    
    if product_search:
        filename_parts.append(f"search_{product_search}")
    
    if variant_filter:
        filename_parts.append(f"variant_{variant_filter}")
    
    filename_parts.append(current_date)
    filename = '_'.join(filename_parts) + '.xls'
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    
    return response
