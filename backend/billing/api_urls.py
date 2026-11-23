from django.urls import path
from .api import ExpenseLedgerAPIView, InvoiceListCreateAPIView, InvoicePaymentAPIView

urlpatterns = [
    path("invoices/", InvoiceListCreateAPIView.as_view(), name="api-billing-invoices"),
    path("invoices/<uuid:invoice_id>/pay/", InvoicePaymentAPIView.as_view(), name="api-billing-pay"),
    path("expenses/", ExpenseLedgerAPIView.as_view(), name="api-billing-expenses"),
]