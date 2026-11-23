from rest_framework import serializers
from .models import Medicine, MedicineBatch, PharmacySale, PharmacySaleItem


class MedicineBatchSerializer(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = MedicineBatch
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "medicine",
            "batch_number",
            "expiry_date",
            "quantity_on_hand",
            "purchase_rate",
            "mrp",
            "is_expired",
        ]
        read_only_fields = ["id", "tenant_id", "is_expired"]


class MedicineSerializer(serializers.ModelSerializer):
    batches = MedicineBatchSerializer(many=True, read_only=True)

    class Meta:
        model = Medicine
        fields = [
            "id",
            "tenant_id",
            "brand_name",
            "generic_name",
            "salt_composition",
            "manufacturer",
            "gst_rate_percent",
            "reorder_level",
            "is_controlled_drug",
            "is_active",
            "batches",
        ]
        read_only_fields = ["id", "tenant_id"]


class PharmacySaleItemSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.brand_name", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)

    class Meta:
        model = PharmacySaleItem
        fields = ["id", "medicine", "medicine_name", "batch", "batch_number", "quantity", "unit_price", "gst_amount", "line_total"]
        read_only_fields = fields


class PharmacySaleSerializer(serializers.ModelSerializer):
    items = PharmacySaleItemSerializer(many=True, read_only=True)

    class Meta:
        model = PharmacySale
        fields = [
            "id",
            "tenant_id",
            "branch_id",
            "invoice_number",
            "customer_name",
            "subtotal_amount",
            "gst_amount",
            "total_amount",
            "items",
            "created_at",
        ]
        read_only_fields = fields