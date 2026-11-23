from rest_framework import serializers
from .models import LabOrder, LabOrderItem, LabResult, LabSample, LabTest


class LabTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = [
            "id",
            "tenant_id",
            "code",
            "name",
            "department",
            "sample_type",
            "reference_range",
            "unit",
            "price",
            "gst_rate_percent",
            "is_active",
        ]
        read_only_fields = ["id", "tenant_id"]


class LabResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabResult
        fields = [
            "id",
            "observed_value",
            "unit",
            "reference_range",
            "is_abnormal",
            "remarks",
            "entered_at",
            "is_verified",
            "verified_at",
        ]
        read_only_fields = fields


class LabOrderItemSerializer(serializers.ModelSerializer):
    test_code = serializers.CharField(source="test.code", read_only=True)
    test_name = serializers.CharField(source="test.name", read_only=True)
    result = LabResultSerializer(read_only=True)

    class Meta:
        model = LabOrderItem
        fields = ["id", "test", "test_code", "test_name", "price", "gst_amount", "result"]
        read_only_fields = fields


class LabSampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabSample
        fields = ["id", "barcode", "sample_type", "collected_at"]
        read_only_fields = fields


class LabOrderSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    sample = LabSampleSerializer(read_only=True)
    items = LabOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = LabOrder
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "order_number",
            "patient",
            "patient_name",
            "status",
            "subtotal_amount",
            "gst_amount",
            "total_amount",
            "delivered_at",
            "sample",
            "items",
            "created_at",
        ]
        read_only_fields = fields