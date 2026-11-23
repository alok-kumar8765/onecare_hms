# backend/pharmacy/urls.py
from django.urls import path
from .views import pharmacy_dashboard_view

urlpatterns = [
    path("dashboard/", pharmacy_dashboard_view, name="pharmacy-dashboard"),
]