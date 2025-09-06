import uuid
import logging
import json
import tempfile
import os
from decimal import Decimal
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum
from django.utils import timezone
from django.template.loader import render_to_string
from django.conf import settings
from authentication.decorators import executive_required
from customers.models import Customer
from products.models import Product, ProductQuality
from .models import Invoice, InvoiceItem
from .forms import InvoiceForm, InvoiceItemForm, CustomerSearchForm, ProductSearchForm, InvoiceSearchForm
from .utils import generate_invoice_pdf
from django.db import models
import whisper
import torch

# Set up logger
logger = logging.getLogger(__name__)

# Load Whisper model once at startup (use GPU if available)
try:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    whisper_model = whisper.load_model("base").to(device)
    logger.info(f"[v0] Whisper model loaded on {device}")
except Exception as e:
    logger.error(f"[v0] Failed to load Whisper model: {str(e)}")
    whisper_model = None

@login_required
@executive_required
def whisper_transcribe(request):
    """AJAX view for Whisper audio transcription using local Whisper model."""
    if request.method == 'POST':
        try:
            # Check if Whisper model is loaded
            if whisper_model is None:
                return JsonResponse({'success': False, 'error': 'Whisper model not loaded. Please install: pip install openai-whisper torch'}, status=500)
            
            # Check if audio file is present
            if 'audio' not in request.FILES:
                return JsonResponse({'success': False, 'error': 'No audio file provided'}, status=400)
            
            audio_file = request.FILES['audio']
            logger.info(f"[v0] Received audio file: {audio_file.name}, size: {audio_file.size} bytes")
            
            # Validate file size (reasonable limit for local processing)
            if audio_file.size > 50 * 1024 * 1024:  # 50MB limit for local processing
                return JsonResponse({'success': False, 'error': 'Audio file too large (max 50MB)'}, status=400)
            
            # Save audio file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                for chunk in audio_file.chunks():
                    temp_file.write(chunk)
                temp_file_path = temp_file.name
            
            try:
                logger.info("[v0] Starting local Whisper transcription...")
                result = whisper_model.transcribe(temp_file_path)
                transcript_text = result["text"].strip()
                
                logger.info(f"[v0] Whisper transcription: {transcript_text}")
                
                return JsonResponse({
                    'success': True,
                    'transcript': transcript_text
                })
                
            except Exception as e:
                logger.error(f"[v0] Whisper transcription error: {str(e)}")
                return JsonResponse({'success': False, 'error': f'Transcription failed: {str(e)}'}, status=500)
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"[v0] Error in whisper_transcribe: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@executive_required
def invoice_list(request):
    """View for listing all invoices."""
    form = InvoiceSearchForm(request.GET)
    invoices = Invoice.objects.all()
    
    if form.is_valid():
        query = form.cleaned_data.get('query')
        status = form.cleaned_data.get('status')
        payment_type = form.cleaned_data.get('payment_type')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        
        if query:
            invoices = invoices.filter(
                Q(invoice_number__icontains=query) | 
                Q(customer__name__icontains=query) |
                Q(customer__phone__icontains=query)
            )
        
        if status:
            invoices = invoices.filter(status=status)
        
        if payment_type:
            invoices = invoices.filter(payment_type=payment_type)
        
        if date_from:
            invoices = invoices.filter(created_at__date__gte=date_from)
        
        if date_to:
            invoices = invoices.filter(created_at__date__lte=date_to)
    
    # Get summary statistics
    total_amount = invoices.aggregate(total=Sum('total'))['total'] or 0
    paid_amount = invoices.aggregate(paid=Sum('amount_paid'))['paid'] or 0
    pending_amount = total_amount - paid_amount
    
    return render(request, 'billing/invoice_list.html', {
        'invoices': invoices,
        'form': form,
        'total_amount': total_amount,
        'paid_amount': paid_amount,
        'pending_amount': pending_amount,
    })

@login_required
@executive_required
def product_selection(request):
    """View for selecting products to add to cart."""
    # Clear cart if starting a new bill
    if request.GET.get('clear_cart') == 'true':
        if 'cart' in request.session:
            del request.session['cart']
            request.session.modified = True
    
    # Initialize cart if it doesn't exist
    if 'cart' not in request.session:
        request.session['cart'] = []
    
    # Get all products with their qualities
    products = Product.objects.all().prefetch_related('qualities')
    
    # Search functionality
    query = request.GET.get('query', '')
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query)
        )
    
    # Get cart count
    cart_count = len(request.session.get('cart', []))
    
    return render(request, 'billing/product_selection.html', {
        'products': products,
        'query': query,
        'cart_count': cart_count,
    })

@login_required
@executive_required
def add_to_cart(request):
    """AJAX view for adding a product to cart."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            product_id = int(data.get('product_id'))
            quality_id = int(data.get('quality_id'))
            quantity = float(data.get('quantity', 1))
            unit = data.get('unit', 'kg')
            
            # Convert to kg if needed
            if unit == 'g':
                quantity = quantity / 1000
            
            # Get product and quality
            product = Product.objects.get(id=product_id)
            quality = ProductQuality.objects.get(id=quality_id)
            
            # Get price based on customer type (default to retail)
            # Convert to string first to ensure proper serialization in session
            price = str(quality.retail_price)
            
            # Initialize cart if it doesn't exist
            if 'cart' not in request.session:
                request.session['cart'] = []
            
            # Check if item already exists in cart
            cart = request.session['cart']
            item_exists = False
            
            for i, item in enumerate(cart):
                if item['product_id'] == product_id and item['quality_id'] == quality_id:
                    # Update quantity
                    cart[i]['quantity'] = float(cart[i]['quantity']) + quantity
                    cart[i]['subtotal'] = str(Decimal(cart[i]['price']) * Decimal(str(cart[i]['quantity'])))
                    item_exists = True
                    break
            
            if not item_exists:
                # Add new item to cart
                cart.append({
                    'product_id': product_id,
                    'product_name': product.name,
                    'quality_id': quality_id,
                    'quality_name': quality.get_quality_display(),
                    'quantity': str(quantity),
                    'unit': 'kg',  # Always store as kg
                    'price': price,
                    'subtotal': str(Decimal(price) * Decimal(str(quantity))),
                    'image_url': product.image_url if hasattr(product, 'image_url') else None,
                })
            
            request.session['cart'] = cart
            request.session.modified = True
            
            return JsonResponse({
                'success': True, 
                'message': f'{product.name} - {quality.get_quality_display()} added to cart',
                'cart_count': len(cart)
            })
            
        except Exception as e:
            logger.error(f"Error adding to cart: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

@login_required
@executive_required
def view_cart(request):
    """View for displaying the cart."""
    cart = request.session.get('cart', [])
    
    enhanced_cart = []
    for item in cart:
        try:
            product = Product.objects.get(id=item['product_id'])
            current_quality = ProductQuality.objects.get(id=item['quality_id'])
            
            # Create enhanced item with product object
            enhanced_item = {
                'product_id': item['product_id'],
                'product': product,  # Full product object with qualities
                'product_name': item['product_name'],
                'quality_id': item['quality_id'],
                'quality': current_quality,  # Current quality object
                'quality_name': item['quality_name'],
                'quantity': item['quantity'],
                'unit': item['unit'],
                'price': item['price'],
                'subtotal': item['subtotal'],
                'image_url': item.get('image_url'),
            }
            enhanced_cart.append(enhanced_item)
        except (Product.DoesNotExist, ProductQuality.DoesNotExist) as e:
            logger.error(f"Error loading cart item: {str(e)}")
            # Skip invalid items
            continue
    
    # Calculate totals
    subtotal = Decimal('0.00')
    for item in enhanced_cart:
        subtotal += Decimal(item['subtotal'])
    
    return render(request, 'billing/view_cart.html', {
        'cart': enhanced_cart,  # Pass enhanced cart with product objects
        'subtotal': subtotal,
    })

@login_required
@executive_required
def update_cart(request):
    """AJAX view for updating cart items."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            index = int(data.get('index'))
            quantity = float(data.get('quantity'))
            unit = data.get('unit', 'kg')
            
            # Convert to kg if needed
            if unit == 'g':
                quantity = quantity / 1000
            
            cart = request.session.get('cart', [])
            
            if 0 <= index < len(cart):
                cart[index]['quantity'] = str(quantity)
                cart[index]['subtotal'] = str(Decimal(cart[index]['price']) * Decimal(str(quantity)))
                
                request.session['cart'] = cart
                request.session.modified = True
                
                return JsonResponse({
                    'success': True, 
                    'message': 'Cart updated',
                    'subtotal': cart[index]['subtotal']
                })
            else:
                return JsonResponse({'success': False, 'message': 'Invalid item index'}, status=400)
            
        except Exception as e:
            logger.error(f"Error updating cart: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

@login_required
@executive_required
def update_cart_quality(request):
    """AJAX view for updating cart item quality."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            index = int(data.get('index'))
            quality_id = int(data.get('quality_id'))
            
            cart = request.session.get('cart', [])
            
            if 0 <= index < len(cart):
                # Get the new quality and its price
                quality = ProductQuality.objects.get(id=quality_id)
                
                # Update cart item with new quality
                cart[index]['quality_id'] = quality_id
                cart[index]['quality_name'] = quality.get_quality_display()
                cart[index]['price'] = str(quality.retail_price)
                
                # Recalculate subtotal with new price
                quantity = Decimal(cart[index]['quantity'])
                new_price = Decimal(str(quality.retail_price))
                cart[index]['subtotal'] = str(new_price * quantity)
                
                request.session['cart'] = cart
                request.session.modified = True
                
                return JsonResponse({
                    'success': True,
                    'message': 'Quality updated successfully',
                    'new_price': str(quality.retail_price),
                    'new_subtotal': cart[index]['subtotal']
                })
            else:
                return JsonResponse({'success': False, 'message': 'Invalid item index'}, status=400)
                
        except ProductQuality.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Quality not found'}, status=400)
        except Exception as e:
            logger.error(f"Error updating cart quality: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

@login_required
@executive_required
def remove_from_cart(request):
    """AJAX view for removing an item from cart."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            index = int(data.get('index'))
            
            cart = request.session.get('cart', [])
            
            if 0 <= index < len(cart):
                removed_item = cart.pop(index)
                
                request.session['cart'] = cart
                request.session.modified = True
                
                return JsonResponse({
                    'success': True, 
                    'message': f'{removed_item["product_name"]} removed from cart',
                    'cart_count': len(cart)
                })
            else:
                return JsonResponse({'success': False, 'message': 'Invalid item index'}, status=400)
            
        except Exception as e:
            logger.error(f"Error removing from cart: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

@login_required
@executive_required
def checkout(request):
    """View for checkout process."""
    cart = request.session.get('cart', [])
    
    if not cart:
        messages.warning(request, 'Your cart is empty. Please add products before checkout.')
        return redirect('product_selection')
    
    if request.method == 'POST':
        logger.info(f"[v0] POST request received for checkout")
        logger.info(f"[v0] Cart contents: {cart}")
        logger.info(f"[v0] POST data: {request.POST}")
        
        form = InvoiceForm(request.POST)
        logger.info(f"[v0] Form is_valid: {form.is_valid()}")
        
        if not form.is_valid():
            logger.error(f"[v0] Form validation errors: {form.errors}")
            return render(request, 'billing/checkout.html', {'form': form, 'cart': cart})
        
        if form.is_valid():
            customer_id = form.cleaned_data.get('customer_id')
            payment_type = form.cleaned_data.get('payment_type')
            payment_due_date = form.cleaned_data.get('payment_due_date')
            
            logger.info(f"[v0] Form data - customer_id: {customer_id}, payment_type: {payment_type}, due_date: {payment_due_date}")
            
            if not customer_id:
                logger.error("[v0] No customer_id provided")
                messages.error(request, 'Please select a customer.')
                return render(request, 'billing/checkout.html', {'form': form, 'cart': cart})
            
            try:
                customer = get_object_or_404(Customer, id=customer_id)
                logger.info(f"[v0] Customer found: {customer.name} (ID: {customer.id})")
            except Exception as e:
                logger.error(f"[v0] Error finding customer: {str(e)}")
                messages.error(request, 'Customer not found.')
                return render(request, 'billing/checkout.html', {'form': form, 'cart': cart})
            
            # Calculate totals first
            subtotal = Decimal('0.00')
            for item in cart:
                subtotal += Decimal(item['subtotal'])
            
            logger.info(f"[v0] Calculated subtotal: {subtotal}")
            
            flat_discount = form.cleaned_data.get('flat_discount', Decimal('0.00'))
            tax_percentage = form.cleaned_data.get('tax_percentage', Decimal('0.00'))
            
            logger.info(f"[v0] Discount: {flat_discount}, Tax %: {tax_percentage}")
            
            # Calculate final total
            discount_amount = flat_discount
            tax_amount = (subtotal - discount_amount) * (tax_percentage / Decimal('100'))
            total = subtotal - discount_amount + tax_amount
            
            logger.info(f"[v0] Final calculations - discount_amount: {discount_amount}, tax_amount: {tax_amount}, total: {total}")
            
            if payment_type == 'credit':
                available_credit = customer.credit_limit - customer.total_pending_amount
                logger.info(f"[v0] Credit check - available: {available_credit}, required: {total}")
                
                if total > available_credit:
                    logger.warning(f"[v0] Insufficient credit - blocking bill creation")
                    messages.error(request, 
                        f'Insufficient credit limit. Available credit: ₹{available_credit:.2f}, '
                        f'Required: ₹{total:.2f}. Please reduce order amount or choose different payment method.')
                    return render(request, 'billing/checkout.html', {
                        'form': form, 
                        'cart': cart,
                        'credit_error': True,
                        'available_credit': available_credit,
                        'required_amount': total
                    })
            
            # Generate a unique invoice number
            invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
            logger.info(f"[v0] Generated invoice number: {invoice_number}")
            
            try:
                # Create the invoice
                invoice = form.save(commit=False)
                invoice.invoice_number = invoice_number
                invoice.customer = customer
                invoice.created_by = request.user
                
                invoice.subtotal = subtotal
                invoice.discount_amount = flat_discount
                invoice.tax_amount = tax_amount
                invoice.total = total
                
                if payment_type == 'cash':
                    invoice.status = 'paid'
                    invoice.amount_paid = total
                    logger.info(f"[v0] Cash payment - marking invoice as paid")
                elif payment_type == 'upi':
                    if payment_due_date and payment_due_date < timezone.now().date():
                        invoice.status = 'overdue'
                        logger.info(f"[v0] UPI payment with past due date - marking as overdue")
                    else:
                        invoice.status = 'pending_payment'
                        logger.info(f"[v0] UPI payment - marking as pending")
                    invoice.amount_paid = Decimal('0.00')
                    if payment_due_date:
                        invoice.due_date = payment_due_date
                else:  # credit
                    if payment_due_date and payment_due_date < timezone.now().date():
                        invoice.status = 'overdue'
                        logger.info(f"[v0] Credit payment with past due date - marking as overdue")
                    else:
                        invoice.status = 'pending_payment'
                        logger.info(f"[v0] Credit payment - marking as pending")
                    invoice.amount_paid = Decimal('0.00')
                    if payment_due_date:
                        invoice.due_date = payment_due_date
                
                logger.info(f"[v0] About to save invoice with status: {invoice.status}")
                invoice.save()
                logger.info(f"[v0] Invoice {invoice.invoice_number} created successfully with ID: {invoice.id}")
                
                # Process cart items
                for i, item in enumerate(cart):
                    logger.info(f"[v0] Processing cart item {i+1}: {item}")
                    
                    try:
                        product = Product.objects.get(id=item['product_id'])
                        quality = ProductQuality.objects.get(id=item['quality_id'])
                        quantity_used = Decimal(item['quantity'])
                        
                        logger.info(f"[v0] Found product: {product.name}, quality: {quality.get_quality_display()}")
                        logger.info(f"[v0] Current stock: {quality.stock_quantity}, using: {quantity_used}")
                        
                        # Reduce stock
                        if quality.stock_quantity >= quantity_used:
                            quality.stock_quantity -= quantity_used
                            quality.save()
                            logger.info(f"[v0] Reduced stock for {product.name} - {quality.get_quality_display()} by {quantity_used}kg")
                        else:
                            messages.warning(request, 
                                f'Warning: {product.name} - {quality.get_quality_display()} '
                                f'had insufficient stock. Stock reduced to 0.')
                            quality.stock_quantity = Decimal('0.00')
                            quality.save()
                            logger.warning(f"[v0] Insufficient stock for {product.name} - set to 0")
                        
                        # Create invoice item
                        invoice_item = InvoiceItem.objects.create(
                            invoice=invoice,
                            product=product,
                            product_quality=quality,
                            quantity=quantity_used,
                            unit_price=Decimal(item['price']),
                            discount_percentage=Decimal('0'),
                            discount_amount=Decimal('0'),
                            subtotal=Decimal(item['subtotal'])
                        )
                        logger.info(f"[v0] Created invoice item with ID: {invoice_item.id}")
                        
                    except Exception as e:
                        logger.error(f"[v0] Error processing cart item {i+1}: {str(e)}")
                        raise e
                
                # Clear the cart
                if 'cart' in request.session:
                    del request.session['cart']
                    request.session.modified = True
                    logger.info("[v0] Cart cleared from session")
                
                if payment_type == 'cash':
                    messages.success(request, 'Bill created and payment completed successfully!')
                elif payment_type == 'upi':
                    if invoice.status == 'overdue':
                        messages.warning(request, 'Bill created successfully! Payment is overdue.')
                    else:
                        messages.success(request, 'Bill created successfully! UPI payment is pending.')
                else:  # credit
                    if invoice.status == 'overdue':
                        messages.warning(request, 'Bill created successfully! Credit payment is overdue.')
                    else:
                        messages.success(request, 'Bill created successfully! Credit payment is pending.')
                
                logger.info(f"[v0] Redirecting to invoice detail page for invoice ID: {invoice.pk}")
                return redirect('invoice_detail', pk=invoice.pk)
                
            except Exception as e:
                logger.error(f"[v0] Critical error during invoice creation: {str(e)}")
                logger.error(f"[v0] Exception type: {type(e).__name__}")
                import traceback
                logger.error(f"[v0] Traceback: {traceback.format_exc()}")
                messages.error(request, f'Error creating bill: {str(e)}')
                return render(request, 'billing/checkout.html', {'form': form, 'cart': cart})
                
    else:
        logger.info("[v0] GET request for checkout page")
        form = InvoiceForm()
    
    # Calculate totals
    subtotal = Decimal('0.00')
    for item in cart:
        subtotal += Decimal(item['subtotal'])
    
    logger.info(f"[v0] Rendering checkout page with subtotal: {subtotal}")
    
    return render(request, 'billing/checkout.html', {
        'form': form,
        'cart': cart,
        'subtotal': subtotal,
    })

@login_required
@executive_required
def invoice_create(request):
    """Redirect to product selection to start the bill creation process."""
    return redirect('product_selection')

@login_required
@executive_required
def invoice_edit(request, pk):
    """View for editing an invoice."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status != 'draft':
        messages.warning(request, 'This invoice has already been issued and cannot be edited.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, 'Invoice updated successfully.')
            return redirect('invoice_edit', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
    
    items = invoice.items.all()
    product_form = ProductSearchForm()
    
    # Calculate totals
    subtotal = sum(item.subtotal for item in items)
    discount_amount = subtotal * (invoice.discount_percentage / 100)
    tax_amount = (subtotal - discount_amount) * (invoice.tax_percentage / 100)
    total = subtotal - discount_amount + tax_amount
    
    return render(request, 'billing/invoice_edit.html', {
        'form': form,
        'invoice': invoice,
        'items': items,
        'product_form': product_form,
        'subtotal': subtotal,
        'discount_amount': discount_amount,
        'tax_amount': tax_amount,
        'total': total,
    })

@login_required
@executive_required
def invoice_detail(request, pk):
    """View for displaying invoice details."""
    invoice = get_object_or_404(Invoice, pk=pk)
    items = invoice.items.all()
    
    # Get all invoices for this customer
    customer_invoices = Invoice.objects.filter(customer=invoice.customer).order_by('-created_at')
    
    # Pass these invoices to the template as customer_payments
    customer_payments = customer_invoices
    
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'items': items,
        'customer_payments': customer_payments,
    })

@login_required
@executive_required
def invoice_issue(request, pk):
    """View for issuing an invoice."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status != 'draft':
        messages.warning(request, 'This invoice has already been issued.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if not invoice.items.exists():
        messages.error(request, 'Cannot issue an invoice with no items.')
        return redirect('invoice_edit', pk=invoice.pk)
    
    # Calculate totals
    items = invoice.items.all()
    subtotal = sum(item.subtotal for item in items)
    discount_amount = subtotal * (invoice.discount_percentage / 100)
    tax_amount = (subtotal - discount_amount) * (invoice.tax_percentage / 100)
    total = subtotal - discount_amount + tax_amount
    
    # Update invoice
    invoice.subtotal = subtotal
    invoice.discount_amount = discount_amount
    invoice.tax_amount = tax_amount
    invoice.total = total
    
    # Set due date for credit invoices
    if invoice.payment_type == 'credit':
        if not invoice.due_date:
            invoice.due_date = timezone.now().date() + timedelta(days=30)
    
    # Set status to pending_payment instead of paid
    invoice.status = 'pending_payment'
    
    invoice.save()
    
    messages.success(request, 'Invoice issued successfully with pending payment status.')
    return redirect('invoice_detail', pk=invoice.pk)

@login_required
@executive_required
def invoice_mark_paid(request, pk):
    """View for marking an invoice as paid."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status == 'paid':
        messages.warning(request, 'This invoice is already marked as paid.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        invoice.status = 'paid'
        invoice.amount_paid = invoice.total
        invoice.save()
        
        logger.info(f"[v0] Invoice {invoice.invoice_number} marked as paid. Customer credit automatically updated.")
        
        messages.success(request, 'Invoice marked as paid successfully. Customer credit balance updated automatically.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    return render(request, 'billing/invoice_confirm_paid.html', {
        'invoice': invoice,
    })

@login_required
@executive_required
def invoice_cancel(request, pk):
    """View for cancelling an invoice."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status == 'cancelled':
        messages.warning(request, 'This invoice is already cancelled.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        invoice.status = 'cancelled'
        invoice.save()
        messages.success(request, 'Invoice cancelled successfully.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    return render(request, 'billing/invoice_confirm_cancel.html', {
        'invoice': invoice,
    })

@login_required
@executive_required
def invoice_delete(request, pk):
    """View for deleting an invoice."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if request.method == 'POST':
        invoice.delete()
        messages.success(request, 'Invoice deleted successfully.')
        return redirect('invoice_list')
    
    return render(request, 'billing/invoice_confirm_delete.html', {
        'invoice': invoice,
    })

@login_required
@executive_required
def invoice_pdf(request, pk):
    """View for generating a PDF of the invoice."""
    invoice = get_object_or_404(Invoice, pk=pk)
    items = invoice.items.all()
    
    # Generate PDF
    pdf = generate_invoice_pdf(invoice, items)
    
    # Create HTTP response with PDF
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
    return response

@login_required
@executive_required
def invoice_item_add(request, invoice_pk):
    """View for adding an item to an invoice."""
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    
    if invoice.status != 'draft':
        messages.warning(request, 'This invoice has already been issued and cannot be modified.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    # Get product_id from URL parameter
    product_id = request.GET.get('product_id')
    product = None
    
    if product_id:
        try:
            product = Product.objects.get(id=product_id)
            # Check if product has any qualities
            if not product.qualities.exists():
                messages.warning(request, f'The product "{product.name}" has no quality variants defined. Please add quality variants first.')
                return redirect('invoice_edit', pk=invoice.pk)
        except Product.DoesNotExist:
            messages.error(request, 'Selected product not found.')
            return redirect('invoice_edit', pk=invoice.pk)
    
    if request.method == 'POST':
        form = InvoiceItemForm(request.POST, product_id=product_id)
        if form.is_valid():
            product_id = form.cleaned_data.get('product_id')
            product = get_object_or_404(Product, id=product_id)
            product_quality = form.cleaned_data.get('product_quality')
            quantity = form.cleaned_data.get('quantity')
            unit_price = form.cleaned_data.get('unit_price')
            discount_percentage = form.cleaned_data.get('discount_percentage')
            
            # Calculate subtotal
            discount_amount = unit_price * quantity * (discount_percentage / 100)
            subtotal = unit_price * quantity - discount_amount
            
            # Create invoice item
            item = form.save(commit=False)
            item.invoice = invoice
            item.product = product
            item.discount_amount = discount_amount
            item.subtotal = subtotal
            item.save()
            
            messages.success(request, 'Item added to invoice successfully.')
            return redirect('invoice_edit', pk=invoice.pk)
    else:
        # Initialize form with product_id if available
        if product:
            # Pass product_id to the form to properly populate product_quality choices
            form = InvoiceItemForm(product_id=product.id, initial={'product_id': product.id, 'product_name': product.name})
        else:
            form = InvoiceItemForm()
    
    return render(request, 'billing/invoice_item_form.html', {
        'form': form,
        'invoice': invoice,
        'title': 'Add Item to Invoice',
        'product': product,  # Pass the product to the template
    })

@login_required
@executive_required
def invoice_item_edit(request, pk):
    """View for editing an invoice item."""
    item = get_object_or_404(InvoiceItem, pk=pk)
    invoice = item.invoice
    product = item.product
    
    if invoice.status != 'draft':
        messages.warning(request, 'This invoice has already been issued and cannot be modified.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        form = InvoiceItemForm(request.POST, instance=item, product_id=item.product.id)
        if form.is_valid():
            quantity = form.cleaned_data.get('quantity')
            unit_price = form.cleaned_data.get('unit_price')
            discount_percentage = form.cleaned_data.get('discount_percentage')
            
            # Calculate subtotal
            discount_amount = unit_price * quantity * (discount_percentage / 100)
            subtotal = unit_price * quantity - discount_amount
            
            # Update invoice item
            item = form.save(commit=False)
            item.discount_amount = discount_amount
            item.subtotal = subtotal
            item.save()
            
            messages.success(request, 'Invoice item updated successfully.')
            return redirect('invoice_edit', pk=invoice.pk)
    else:
        # Initialize form with the existing item data
        initial_data = {
            'product_id': item.product.id,
            'product_name': item.product.name,
            'product_quality': item.product_quality.id,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'discount_percentage': item.discount_percentage
        }
        form = InvoiceItemForm(instance=item, product_id=item.product.id, initial=initial_data)
    
    return render(request, 'billing/invoice_item_form.html', {
        'form': form,
        'invoice': invoice,
        'item': item,
        'title': 'Edit Invoice Item',
        'product': product,  # Pass the product to the template
    })

@login_required
@executive_required
def invoice_item_delete(request, pk):
    """View for deleting an invoice item."""
    item = get_object_or_404(InvoiceItem, pk=pk)
    invoice = item.invoice
    
    if invoice.status != 'draft':
        messages.warning(request, 'This invoice has already been issued and cannot be modified.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Invoice item deleted successfully.')
        return redirect('invoice_edit', pk=invoice.pk)
    
    return render(request, 'billing/invoice_item_confirm_delete.html', {
        'item': item,
        'invoice': invoice,
    })

@login_required
@executive_required
def customer_search_api(request):
    """API view for searching customers."""
    query = request.GET.get('q', '')
    logger.info(f"[v0] Customer search query: {query}")
    
    if not query or len(query) < 2:
        logger.warning("[v0] Search query too short or empty")
        return JsonResponse({'customers': [], 'message': 'Please enter at least 2 characters to search'})
    
    try:
        # Search by name or phone
        customers = Customer.objects.filter(
            Q(name__icontains=query) | Q(phone__icontains=query)
        )[:10]
        
        logger.info(f"[v0] Found {customers.count()} customers matching '{query}'")
        
        customer_list = []
        for customer in customers:
            logger.info(f"[v0] Processing customer: {customer.name} (ID: {customer.id})")
            logger.info(f"[v0] Customer credit_limit: {customer.credit_limit}")
            
            pending_amount = customer.total_pending_amount
            logger.info(f"[v0] Customer total_pending_amount: {pending_amount}")
            
            available_credit = customer.credit_limit - pending_amount
            logger.info(f"[v0] Calculated available_credit: {available_credit}")
            
            customer_data = {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'customer_type': customer.get_customer_type_display(),
                'credit_limit': float(customer.credit_limit),
                'pending_amount': float(pending_amount),
                'available_credit': float(available_credit),
                'credit_exceeded': customer.is_credit_limit_exceeded,
            }
            
            logger.info(f"[v0] Customer data being sent: {customer_data}")
            customer_list.append(customer_data)
        
        logger.info(f"[v0] Final customer_list: {customer_list}")
        return JsonResponse({'customers': customer_list})
    except Exception as e:
        logger.error(f"[v0] Error in customer search: {str(e)}")
        return JsonResponse({'customers': [], 'message': f'Error: {str(e)}'}, status=500)

@login_required
@executive_required
def product_quality_price_api(request):
    """API view for getting product quality prices."""
    quality_id = request.GET.get('quality_id', '')
    customer_type = request.GET.get('customer_type', 'retail')
    
    if not quality_id:
        return JsonResponse({'success': False, 'message': 'Quality ID is required.'})
    
    try:
        quality = ProductQuality.objects.get(id=quality_id)
        
        if customer_type == 'retail':
            price = quality.retail_price
        elif customer_type == 'wholesale':
            price = quality.wholesale_price
        elif customer_type == 'broker':
            price = quality.broker_price
        else:
            price = quality.retail_price
        
        return JsonResponse({
            'success': True,
            'price': float(price),
            'stock': float(quality.stock_quantity),
        })
    except ProductQuality.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Product quality not found.'})

@login_required
@executive_required
def product_search_api(request):
    """API view for searching products."""
    query = request.GET.get('q', '')
    logger.info(f"Product search query: {query}")
    
    if not query or len(query) < 2:
        logger.warning("Product search query too short or empty")
        return JsonResponse({'products': [], 'message': 'Please enter at least 2 characters to search'})
    
    try:
        # Search by name only (removed sku reference)
        products = Product.objects.filter(name__icontains=query)[:10]
        
        logger.info(f"Found {products.count()} products matching '{query}'")
        
        product_list = []
        for product in products:
            qualities = []
            for quality in product.qualities.all():
                qualities.append({
                    'id': quality.id,
                    'name': quality.get_quality_display(),
                    'retail_price': float(quality.retail_price),
                    'wholesale_price': float(quality.wholesale_price),
                    'broker_price': float(quality.broker_price),
                    'stock_quantity': float(quality.stock_quantity),
                })
            
            product_list.append({
                'id': product.id,
                'name': product.name,
                'image_url': product.image_url if hasattr(product, 'image_url') else None,
                'qualities': qualities,
            })
        
        return JsonResponse({'products': product_list})
    except Exception as e:
        logger.error(f"Error in product search: {str(e)}")
        return JsonResponse({'products': [], 'message': f'Error: {str(e)}'}, status=500)

@login_required
@executive_required
def set_invoice_due_date(request, pk):
    """View for setting or updating an invoice's due date."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status == 'paid' or invoice.status == 'cancelled':
        messages.warning(request, 'Cannot set due date for paid or cancelled invoices.')
        return redirect('invoice_detail', pk=invoice.pk)
    
    if request.method == 'POST':
        due_date = request.POST.get('due_date')
        try:
            # Parse the date from the form
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
            
            # Update the invoice
            invoice.due_date = due_date
            invoice.save()
            
            messages.success(request, 'Due date updated successfully.')
            return redirect('invoice_detail', pk=invoice.pk)
        except (ValueError, TypeError):
            messages.error(request, 'Invalid date format. Please use YYYY-MM-DD format.')
    
    # For GET requests or if there's an error in POST
    return render(request, 'billing/set_due_date.html', {
        'invoice': invoice,
    })

@login_required
@executive_required
def customer_create_api(request):
    """API view for creating a new customer."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            phone = data.get('phone', '').strip()
            customer_type = data.get('customer_type', 'retail')
            credit_limit = data.get('credit_limit', 0)
            
            logger.info(f"Creating customer: {name}, {phone}, {customer_type}")
            
            # Validate required fields
            if not name:
                return JsonResponse({'success': False, 'message': 'Customer name is required.'})
            
            if not phone:
                return JsonResponse({'success': False, 'message': 'Phone number is required.'})
            
            # Check if customer already exists
            existing_customer = Customer.objects.filter(
                Q(name__iexact=name) | Q(phone=phone)
            ).first()
            
            if existing_customer:
                return JsonResponse({
                    'success': False, 
                    'message': f'Customer with this name or phone already exists.',
                    'existing_customer': {
                        'id': existing_customer.id,
                        'name': existing_customer.name,
                        'phone': existing_customer.phone,
                        'customer_type': existing_customer.get_customer_type_display(),
                    }
                })
            
            # Create new customer
            customer = Customer.objects.create(
                name=name,
                phone=phone,
                customer_type=customer_type,
                credit_limit=Decimal(str(credit_limit)) if credit_limit else Decimal('0.00')
            )
            
            logger.info(f"Customer created successfully: {customer.id}")
            
            return JsonResponse({
                'success': True,
                'message': 'Customer created successfully.',
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'phone': customer.phone,
                    'customer_type': customer.get_customer_type_display(),
                    'credit_limit': float(customer.credit_limit),
                    'pending_amount': 0.0,
                }
            })
            
        except Exception as e:
            logger.error(f"Error creating customer: {str(e)}")
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)
