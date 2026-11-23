from django.urls import path
from .api import LabOrderActionAPIView, LabOrderListCreateAPIView, LabTestListCreateAPIView

urlpatterns = [
    path("tests/", LabTestListCreateAPIView.as_view(), name="api-lab-tests"),
    path("orders/", LabOrderListCreateAPIView.as_view(), name="api-lab-orders"),
    path("orders/<uuid:order_id>/<str:action>/", LabOrderActionAPIView.as_view(), name="api-lab-order-action"),
]