from django.urls import path
from .api import MedicineSearchAddAPIView, PharmacyDispenseAPIView

urlpatterns = [
    path("medicines/", MedicineSearchAddAPIView.as_view(), name="api-pharmacy-medicines"),
    path("sales/", PharmacyDispenseAPIView.as_view(), name="api-pharmacy-sales"),
]