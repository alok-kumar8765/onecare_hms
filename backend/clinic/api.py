from datetime import date
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.permissions import LicenseWriteAndModulePermission
from tenants.models import ModuleCode
from .models import Appointment, Patient
from .serializers import AppointmentSerializer, OPDEncounterSerializer, PatientSerializer
from .services import (
    create_opd_encounter_with_prescription,
    filter_encounters_queryset,
    register_patient,
    schedule_appointment,
)


def _parse_optional_date(val):
    if not val:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val).strip())


class PatientListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.CLINIC_OPD
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = Patient.objects.filter(tenant_id=tenant_id)
        search = (request.query_params.get("q") or "").strip()
        if search:
            qs = qs.filter(full_name__icontains=search) | Patient.objects.filter(
                tenant_id=tenant_id, phone_number__icontains=search
            )
        return Response(PatientSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)

        full_name = (request.data.get("full_name") or "").strip()
        if not full_name:
            return Response({"detail": "full_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dob = _parse_optional_date(request.data.get("date_of_birth"))
            allow_dup = str(request.data.get("allow_duplicate", "false")).lower() in {"true", "1", "yes"}
            patient, duplicates = register_patient(
                tenant_id=tenant_id,
                branch_id=getattr(request.user, "primary_branch_id", None),
                full_name=full_name,
                gender=request.data.get("gender") or "OTHER",
                date_of_birth=dob,
                phone_number=request.data.get("phone_number") or "",
                email=request.data.get("email") or "",
                abha_number=request.data.get("abha_number") or "",
                blood_group=request.data.get("blood_group") or "",
                address=request.data.get("address") or "",
                allergies_notes=request.data.get("allergies_notes") or "",
                photo=request.FILES.get("photo"),
                allow_duplicate=allow_dup,
                actor=request.user,
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc), "duplicate_warning": True}, status=status.HTTP_409_CONFLICT)

        return Response(
            {
                "patient": PatientSerializer(patient, context={"request": request}).data,
                "duplicate_count": len(duplicates),
            },
            status=status.HTTP_201_CREATED,
        )


class AppointmentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.CLINIC_OPD

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = Appointment.objects.select_related("patient").filter(tenant_id=tenant_id)
        return Response(AppointmentSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        patient_id = request.data.get("patient_id") or request.data.get("patient")
        patient = Patient.objects.filter(id=patient_id, tenant_id=tenant_id).first()
        if not patient:
            return Response({"detail": "Patient not found in your organization."}, status=status.HTTP_404_NOT_FOUND)

        appt = schedule_appointment(
            tenant_id=tenant_id,
            patient=patient,
            doctor=request.user if getattr(request.user, "role", None) == "DOCTOR" else None,
            branch_id=getattr(request.user, "primary_branch_id", None),
            visit_date=_parse_optional_date(request.data.get("visit_date")),
            reason=request.data.get("reason") or "",
            actor=request.user,
            request=request,
        )
        return Response(AppointmentSerializer(appt).data, status=status.HTTP_201_CREATED)


class EncounterListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, LicenseWriteAndModulePermission]
    required_module = ModuleCode.CLINIC_OPD

    def get(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        qs = filter_encounters_queryset(
            tenant_id=tenant_id,
            period=request.query_params.get("period") or "all",
            doctor_id=request.query_params.get("doctor_id") or None,
            branch_id=request.query_params.get("branch_id") or None,
            start_date=_parse_optional_date(request.query_params.get("start_date")),
            end_date=_parse_optional_date(request.query_params.get("end_date")),
        )
        return Response(OPDEncounterSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        tenant_id = getattr(request.user, "tenant_id", None)
        if not tenant_id:
            return Response({"detail": "No tenant context found."}, status=status.HTTP_403_FORBIDDEN)
        patient_id = request.data.get("patient_id") or request.data.get("patient")
        patient = Patient.objects.filter(id=patient_id, tenant_id=tenant_id).first()
        if not patient:
            return Response({"detail": "Patient not found in your organization."}, status=status.HTTP_404_NOT_FOUND)

        chief_complaint = (request.data.get("chief_complaint") or "").strip()
        if not chief_complaint:
            return Response({"detail": "chief_complaint is required."}, status=status.HTTP_400_BAD_REQUEST)

        appt = None
        appt_id = request.data.get("appointment_id")
        if appt_id:
            appt = Appointment.objects.filter(id=appt_id, tenant_id=tenant_id).first()

        encounter, prescription = create_opd_encounter_with_prescription(
            tenant_id=tenant_id,
            patient=patient,
            doctor=request.user if getattr(request.user, "role", None) == "DOCTOR" else None,
            appointment=appt,
            branch_id=getattr(request.user, "primary_branch_id", None),
            chief_complaint=chief_complaint,
            vitals_summary=request.data.get("vitals_summary") or "",
            clinical_notes=request.data.get("clinical_notes") or "",
            diagnosis=request.data.get("diagnosis") or "",
            follow_up_date=_parse_optional_date(request.data.get("follow_up_date")),
            advice=request.data.get("advice") or "",
            items=request.data.get("items") or [],
            actor=request.user,
            request=request,
        )
        return Response(
            {
                "encounter": OPDEncounterSerializer(encounter).data,
                "prescription_id": str(prescription.id),
            },
            status=status.HTTP_201_CREATED,
        )