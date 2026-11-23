from django.urls import path
from .api import LicenseActivateAPIView, LicenseStatusAPIView

urlpatterns = [
    path("status/", LicenseStatusAPIView.as_view(), name="api-licensing-status"),
    path("activate/", LicenseActivateAPIView.as_view(), name="api-licensing-activate"),
]