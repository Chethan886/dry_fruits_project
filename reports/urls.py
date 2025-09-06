from django.urls import path
from . import views

urlpatterns = [
    path('', views.report_list, name='report_list'),
    path('sales/', views.sales_report, name='sales_report'),
    path('products/', views.product_sales_report, name='product_sales_report'),
    path('customers/', views.customer_summary_report, name='customer_summary_report'),
    path('credit/', views.credit_overview_report, name='credit_overview_report'),
    path('export/credit/', views.export_credit_report, name='export_credit_report'),
    path('export/sales/', views.export_sales_report, name='export_sales_report'),
]
