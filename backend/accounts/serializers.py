from rest_framework import serializers
from .models import User, UserDevice
from typing import Optional

class UserProfileSerializer(serializers.ModelSerializer):
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "tenant_id",
            "primary_branch_id",
            "phone_number",
            "two_factor_enabled",
            "totp_verified",
            "profile_photo",
            "profile_photo_url",
        ]
        read_only_fields = ["id", "role", "tenant_id", "primary_branch_id", "totp_verified", "profile_photo_url"]

    def get_profile_photo_url(self, obj: User) -> Optional[str]:
        if obj.profile_photo:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.profile_photo.url) if request else obj.profile_photo.url
        return None


class UserDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = ["id", "device_label", "ip_address", "is_trusted", "approved_at", "last_seen_at"]
        read_only_fields = ["id", "approved_at", "last_seen_at"]