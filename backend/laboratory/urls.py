# backend/laboratory/urls.py
from django.urls import path
from .views import laboratory_dashboard_view

urlpatterns = [
    path("dashboard/", laboratory_dashboard_view, name="laboratory-dashboard"),
]