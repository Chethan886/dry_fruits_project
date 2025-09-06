from django.urls import path
from . import views

urlpatterns = [
    path('', views.pending_payment_list, name='payment_list'),
    path('all/', views.payment_list, name='all_payments'),
    path('pending/', views.pending_payment_list, name='pending_payment_list'),
    path('invoice/<int:invoice_id>/payment/create/', views.payment_create, name='payment_create'),
    path('payment/<int:pk>/', views.payment_detail, name='payment_detail'),
    path('payment/<int:pk>/update/', views.payment_update, name='payment_update'),
    path('payment/<int:pk>/cancel/', views.payment_cancel, name='payment_cancel'),
    path('invoice/<int:invoice_id>/reminder/create/', views.reminder_create, name='reminder_create'),
    path('customer/<int:customer_id>/payment-history/', views.customer_payment_history, name='customer_payment_history'),
    path('bulk-reminder/', views.bulk_reminder, name='bulk_reminder'),
]
