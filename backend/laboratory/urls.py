# backend/laboratory/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path("dashboard/", laboratory_dashboard_view, name="laboratory-dashboard"),
    path("orders/<uuid:order_id>/print/", lab_report_print_view, name="laboratory-report-print"),
]