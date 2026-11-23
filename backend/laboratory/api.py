from decimal import Decimal
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from clinic.models import Patient
from core.permissions import LicenseWriteAndModulePermission
from tenants.models import ModuleCode
from .models import LabOrder, LabTest
from .serializers import LabOrderSerializer, LabResultSerializer, LabSampleSerializer, LabTestSerializer
from .services import (
    create_lab_order,
    create_lab_test,
    deliver_lab_report,
    mark_sample_collected,
    record_test_result,
    verify_lab_order,
)


class LabTestListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.LABORATORY

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = LabTest.objects.filter(tenant_id=tenant_id, is_active=True)
        return Response(LabTestSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        try:
            test = create_lab_test(
                tenant_id=tenant_id,
                code=request.data.get("code") or "",
                name=request.data.get("name") or "",
                price=Decimal(str(request.data.get("price") or "0")),
                department=request.data.get("department") or "Pathology",
                sample_type=request.data.get("sample_type") or "Whole Blood / Serum",
                reference_range=request.data.get("reference_range") or "",
                unit=request.data.get("unit") or "",
                gst_rate_percent=Decimal(str(request.data.get("gst_rate_percent") or "0")),
                actor=request.user,
                request=request,
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LabTestSerializer(test).data, status=status.HTTP_201_CREATED)


class LabOrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.LABORATORY

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = LabOrder.objects.select_related("patient", "sample").prefetch_related("items__test", "items__result").filter(tenant_id=tenant_id)
        return Response(LabOrderSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        patient_id = request.data.get("patient_id") or request.data.get("patient")
        patient = Patient.objects.filter(id=patient_id, tenant_id=tenant_id).first()
        if not patient:
            return Response({"detail": "Patient not found in your organization."}, status=status.HTTP_404_NOT_FOUND)
        try:
            order = create_lab_order(
                tenant_id=tenant_id,
                patient=patient,
                test_ids=request.data.get("test_ids") or [],
                branch_id=getattr(request.user, "primary_branch_id", None),
                notes=request.data.get("notes") or "",
                actor=request.user,
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LabOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class LabOrderActionAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.LABORATORY

    def post(self, request, order_id, action):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        try:
            if action == "collect-sample":
                sample = mark_sample_collected(tenant_id=tenant_id, order_id=order_id, actor=request.user, request=request)
                return Response(LabSampleSerializer(sample).data, status=status.HTTP_200_OK)
            if action == "enter-result":
                res = record_test_result(
                    tenant_id=tenant_id,
                    order_item_id=request.data.get("order_item_id"),
                    observed_value=request.data.get("observed_value") or "",
                    is_abnormal=bool(request.data.get("is_abnormal", False)),
                    remarks=request.data.get("remarks") or "",
                    actor=request.user,
                    request=request,
                )
                return Response(LabResultSerializer(res).data, status=status.HTTP_200_OK)
            if action == "verify":
                order = verify_lab_order(tenant_id=tenant_id, order_id=order_id, actor=request.user, request=request)
                return Response(LabOrderSerializer(order).data, status=status.HTTP_200_OK)
            if action == "deliver":
                order = deliver_lab_report(tenant_id=tenant_id, order_id=order_id, actor=request.user, request=request)
                return Response(LabOrderSerializer(order).data, status=status.HTTP_200_OK)
            return Response({"detail": "Unsupported action."}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)