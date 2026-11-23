from rest_framework import serializers
from .models import Bed, IPDBillingItem, IPDAdmission, IPDRoundNote, Ward


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "code",
            "name",
            "ward_type",
            "daily_charge",
            "gst_rate_percent",
            "is_active",
        ]
        read_only_fields = ["id", "tenant_id"]


class BedSerializer(serializers.ModelSerializer):
    ward_name = serializers.CharField(source="ward.name", read_only=True)

    class Meta:
        model = Bed
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "ward",
            "ward_name",
            "bed_number",
            "status",
            "notes",
        ]
        read_only_fields = ["id", "tenant_id"]


class IPDRoundNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPDRoundNote
        fields = ["id", "admission", "vitals", "clinical_notes", "treatment_plan", "created_at"]
        read_only_fields = ["id", "created_at"]


class IPDBillingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPDBillingItem
        fields = ["id", "admission", "description", "quantity", "unit_rate", "gst_rate_percent", "line_total"]
        read_only_fields = ["id", "line_total"]


class IPDAdmissionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    ward_name = serializers.CharField(source="ward.name", read_only=True)
    bed_number = serializers.CharField(source="bed.bed_number", read_only=True)
    round_notes = IPDRoundNoteSerializer(many=True, read_only=True)
    billing_items = IPDBillingItemSerializer(many=True, read_only=True)

    class Meta:
        model = IPDAdmission
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "admission_number",
            "patient",
            "patient_name",
            "ward",
            "ward_name",
            "bed",
            "bed_number",
            "admitted_at",
            "discharged_at",
            "status",
            "admission_reason",
            "discharge_summary",
            "subtotal_amount",
            "gst_amount",
            "total_amount",
            "round_notes",
            "billing_items",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "admission_number",
            "discharged_at",
            "status",
            "subtotal_amount",
            "gst_amount",
            "total_amount",
        ]