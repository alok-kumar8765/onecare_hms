# backend/billing/urls.py
from django.urls import path
from .views import billing_dashboard_view

urlpatterns = [
    path("dashboard/", billing_dashboard_view, name="billing-dashboard"),
]