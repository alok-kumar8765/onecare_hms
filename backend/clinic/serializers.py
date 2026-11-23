from rest_framework import serializers
from .models import Appointment, OPDEncounter, Patient, Prescription, PrescriptionItem
from typing import Optional

class PatientSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "uhid",
            "full_name",
            "gender",
            "date_of_birth",
            "phone_number",
            "email",
            "abha_number",
            "blood_group",
            "address",
            "allergies_notes",
            "photo",
            "photo_url",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "tenant_id", "uhid", "photo_url", "created_at"]

    def get_photo_url(self, obj: Patient) -> Optional[str]:
        if obj.photo:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "patient",
            "patient_name",
            "doctor",
            "visit_date",
            "token_number",
            "reason",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "tenant_id", "token_number", "created_at"]


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = ["id", "medicine_name", "dosage", "frequency", "duration", "instructions"]
        read_only_fields = ["id"]


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = ["id", "encounter", "patient", "prescribed_by", "advice", "items", "created_at"]
        read_only_fields = ["id", "created_at"]


class OPDEncounterSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    prescriptions = PrescriptionSerializer(many=True, read_only=True)

    class Meta:
        model = OPDEncounter
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "patient",
            "patient_name",
            "appointment",
            "doctor",
            "encounter_date",
            "chief_complaint",
            "vitals_summary",
            "clinical_notes",
            "diagnosis",
            "follow_up_date",
            "prescriptions",
            "created_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at"]