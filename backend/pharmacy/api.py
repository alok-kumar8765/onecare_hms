from datetime import date
from decimal import Decimal
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.permissions import LicenseWriteAndModulePermission
from tenants.models import ModuleCode
from .models import PharmacySale
from .serializers import MedicineBatchSerializer, MedicineSerializer, PharmacySaleSerializer
from .services import add_medicine_and_batch, dispense_fefo_sale, search_medicines


class MedicineSearchAddAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.PHARMACY

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = search_medicines(tenant_id=tenant_id, query=request.query_params.get("q") or "")
        return Response(MedicineSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)

        try:
            exp_date = date.fromisoformat(str(request.data.get("expiry_date")).strip())
            qty = int(request.data.get("quantity") or 0)
            mrp = Decimal(str(request.data.get("mrp") or "0"))
            gst = Decimal(str(request.data.get("gst_rate_percent") or "12.00"))
            med, batch = add_medicine_and_batch(
                tenant_id=tenant_id,
                branch_id=getattr(request.user, "primary_branch_id", None),
                brand_name=(request.data.get("brand_name") or "").strip(),
                generic_name=(request.data.get("generic_name") or "").strip(),
                salt_composition=(request.data.get("salt_composition") or "").strip(),
                batch_number=(request.data.get("batch_number") or "").strip(),
                expiry_date=exp_date,
                quantity=qty,
                unit_price=mrp,
                gst_rate_percent=gst,
                is_controlled_drug=bool(request.data.get("is_controlled_drug", False)),
                actor=request.user,
                request=request,
            )
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"medicine": MedicineSerializer(med).data, "batch": MedicineBatchSerializer(batch).data},
            status=status.HTTP_201_CREATED,
        )


class PharmacyDispenseAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.PHARMACY

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = PharmacySale.objects.prefetch_related("items").filter(tenant_id=tenant_id)
        return Response(PharmacySaleSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)

        items = request.data.get("items") or []
        try:
            sale = dispense_fefo_sale(
                tenant_id=tenant_id,
                branch_id=getattr(request.user, "primary_branch_id", None),
                items_requested=items,
                customer_name=(request.data.get("customer_name") or "").strip(),
                actor=request.user,
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PharmacySaleSerializer(sale).data, status=status.HTTP_201_CREATED)