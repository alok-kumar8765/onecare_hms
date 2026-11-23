from decimal import Decimal
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from clinic.models import Patient
from core.permissions import LicenseWriteAndModulePermission
from tenants.models import ModuleCode
from .models import Bed, IPDAdmission
from .serializers import (
    BedSerializer,
    IPDBillingItemSerializer,
    IPDAdmissionSerializer,
    IPDRoundNoteSerializer,
    WardSerializer,
)
from .services import (
    add_ipd_billing_item,
    add_ipd_round_note,
    admit_patient_to_bed,
    create_ward_with_beds,
    discharge_ipd_patient,
)


class WardBedListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.IPD

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        beds = Bed.objects.select_related("ward").filter(tenant_id=tenant_id)
        return Response(BedSerializer(beds, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        try:
            ward, beds = create_ward_with_beds(
                tenant_id=tenant_id,
                branch_id=getattr(request.user, "primary_branch_id", None),
                code=request.data.get("code") or "",
                name=request.data.get("name") or "",
                ward_type=request.data.get("ward_type") or "GENERAL",
                daily_charge=Decimal(str(request.data.get("daily_charge") or "1000.00")),
                gst_rate_percent=Decimal(str(request.data.get("gst_rate_percent") or "0.00")),
                bed_count=int(request.data.get("bed_count") or 0),
                actor=request.user,
                request=request,
            )
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"ward": WardSerializer(ward).data, "beds": BedSerializer(beds, many=True).data},
            status=status.HTTP_201_CREATED,
        )


class IPDAdmissionListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.IPD

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = (
            IPDAdmission.objects.select_related("patient", "ward", "bed")
            .prefetch_related("round_notes", "billing_items")
            .filter(tenant_id=tenant_id)
        )
        return Response(IPDAdmissionSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        patient = Patient.objects.filter(
            id=request.data.get("patient_id") or request.data.get("patient"),
            tenant_id=tenant_id,
        ).first()
        if not patient:
            return Response({"detail": "Patient not found in your organization."}, status=status.HTTP_404_NOT_FOUND)
        try:
            adm = admit_patient_to_bed(
                tenant_id=tenant_id,
                patient=patient,
                bed_id=request.data.get("bed_id") or request.data.get("bed"),
                admission_reason=request.data.get("admission_reason") or "",
                branch_id=getattr(request.user, "primary_branch_id", None),
                actor=request.user,
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(IPDAdmissionSerializer(adm).data, status=status.HTTP_201_CREATED)


class IPDAdmissionActionAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.IPD

    def post(self, request, admission_id, action):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        try:
            if action == "round-note":
                note = add_ipd_round_note(
                    tenant_id=tenant_id,
                    admission_id=admission_id,
                    vitals=request.data.get("vitals") or "",
                    clinical_notes=request.data.get("clinical_notes") or "",
                    treatment_plan=request.data.get("treatment_plan") or "",
                    actor=request.user,
                    request=request,
                )
                return Response(IPDRoundNoteSerializer(note).data, status=status.HTTP_201_CREATED)
            if action == "billing-item":
                item = add_ipd_billing_item(
                    tenant_id=tenant_id,
                    admission_id=admission_id,
                    description=request.data.get("description") or "",
                    quantity=int(request.data.get("quantity") or 1),
                    unit_rate=Decimal(str(request.data.get("unit_rate") or "0.00")),
                    gst_rate_percent=Decimal(str(request.data.get("gst_rate_percent") or "0.00")),
                )
                return Response(IPDBillingItemSerializer(item).data, status=status.HTTP_201_CREATED)
            if action == "discharge":
                adm = discharge_ipd_patient(
                    tenant_id=tenant_id,
                    admission_id=admission_id,
                    discharge_summary=request.data.get("discharge_summary") or "",
                    actor=request.user,
                    request=request,
                )
                return Response(IPDAdmissionSerializer(adm).data, status=status.HTTP_200_OK)
            return Response({"detail": "Unsupported action."}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)