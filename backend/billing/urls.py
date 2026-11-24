# backend/billing/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path("dashboard/", billing_dashboard_view, name="billing-dashboard"),
    path("invoices/<uuid:invoice_id>/print/", invoice_print_view, name="billing-invoice-print"),
]
