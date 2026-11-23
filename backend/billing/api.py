from decimal import Decimal, InvalidOperation
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from clinic.models import Patient
from core.permissions import LicenseWriteAndModulePermission
from tenants.models import ModuleCode
from .models import ExpenseEntry, Invoice
from .serializers import ExpenseEntrySerializer, InvoiceSerializer, PaymentTransactionSerializer
from .services import create_invoice_with_items, record_expense, record_invoice_payment, summarize_finance


class InvoiceListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.BILLING

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = Invoice.objects.prefetch_related("items", "payments").filter(tenant_id=tenant_id)
        return Response(InvoiceSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        patient = None
        patient_id = request.data.get("patient_id") or request.data.get("patient")
        if patient_id:
            patient = Patient.objects.filter(id=patient_id, tenant_id=tenant_id).first()
            if not patient:
                return Response({"detail": "Patient not found in your organization."}, status=status.HTTP_404_NOT_FOUND)
        try:
            inv = create_invoice_with_items(
                tenant_id=tenant_id,
                patient=patient,
                customer_name=request.data.get("customer_name") or "",
                items=request.data.get("items") or [],
                discount_amount=Decimal(str(request.data.get("discount_amount") or "0.00")),
                branch_id=getattr(request.user, "primary_branch_id", None),
                notes=request.data.get("notes") or "",
                actor=request.user,
                request=request,
            )
        except (ValueError, InvalidOperation, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InvoiceSerializer(inv).data, status=status.HTTP_201_CREATED)


class InvoicePaymentAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.BILLING

    def post(self, request, invoice_id):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        try:
            txn = record_invoice_payment(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                amount=Decimal(str(request.data.get("amount") or "0.00")),
                method=request.data.get("method") or "UPI",
                reference_no=request.data.get("reference_no") or "",
                actor=request.user,
                request=request,
            )
        except (ValueError, InvalidOperation, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)


class ExpenseLedgerAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.BILLING

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        expenses = ExpenseEntry.objects.filter(tenant_id=tenant_id)
        summary = summarize_finance(tenant_id=tenant_id)
        return Response(
            {
                "summary": {k: str(v) for k, v in summary.items()},
                "expenses": ExpenseEntrySerializer(expenses, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        try:
            exp = record_expense(
                tenant_id=tenant_id,
                title=request.data.get("title") or "",
                amount=Decimal(str(request.data.get("amount") or "0.00")),
                category=request.data.get("category") or "OPERATIONAL",
                vendor_name=request.data.get("vendor_name") or "",
                notes=request.data.get("notes") or "",
                branch_id=getattr(request.user, "primary_branch_id", None),
                actor=request.user,
                request=request,
            )
        except (ValueError, InvalidOperation, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExpenseEntrySerializer(exp).data, status=status.HTTP_201_CREATED)