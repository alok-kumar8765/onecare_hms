# backend/clinic/urls.py
from django.urls import path
from .views import clinic_dashboard_view

urlpatterns = [
    path("dashboard/", clinic_dashboard_view, name="clinic-dashboard"),
]