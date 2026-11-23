from rest_framework import serializers
from .models import Branch, ModuleEntitlement, Tenant


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "tenant_id", "name", "code", "is_main", "is_active", "phone_number", "address"]
        read_only_fields = ["id", "tenant_id"]


class ModuleEntitlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModuleEntitlement
        fields = ["id", "tenant_id", "module_code", "is_enabled"]
        read_only_fields = ["id", "tenant_id", "module_code"]


class TenantSummarySerializer(serializers.ModelSerializer):
    branches = BranchSerializer(many=True, read_only=True)
    entitlements = ModuleEntitlementSerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "gstin", "is_active", "branches", "entitlements"]
        read_only_fields = ["id", "slug"]