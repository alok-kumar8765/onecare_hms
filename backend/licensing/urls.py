# backend/licensing/urls.py
from django.urls import path
from .views import license_status_view

urlpatterns = [
    path("status/", license_status_view, name="licensing-status"),
]