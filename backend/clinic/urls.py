# backend/clinic/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path("dashboard/", clinic_dashboard_view, name="clinic-dashboard"),
    path("prescriptions/<uuid:prescription_id>/print/", prescription_print_view, name="clinic-prescription-print"),
]