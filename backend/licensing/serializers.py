from rest_framework import serializers
from .models import InstallationLicense


class InstallationLicenseSerializer(serializers.ModelSerializer):
    is_write_allowed = serializers.BooleanField(read_only=True)

    class Meta:
        model = InstallationLicense
        fields = [
            "id",
            "installation_id",
            "tenant_id",
            "provider_mode",
            "status",
            "is_write_allowed",
            "trial_started_at",
            "trial_expires_at",
            "license_expires_at",
            "last_verified_at",
            "licensed_modules",
        ]
        read_only_fields = fields