# backend/ipd/urls.py
from django.urls import path
from .views import ipd_dashboard_view

urlpatterns = [
    path("dashboard/", ipd_dashboard_view, name="ipd-dashboard"),
]