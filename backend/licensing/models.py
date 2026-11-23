import uuid
from django.db import models
from django.utils import timezone
from core.models import TimeStampedModel


class LicenseStatus(models.TextChoices):
    TRIAL = "TRIAL", "7-Day Trial Active"
    ACTIVE = "ACTIVE", "Licensed Active"
    RESTRICTED = "RESTRICTED", "Expired — Patient-Safe Restricted Mode"
    REVOKED = "REVOKED", "Revoked"


class InstallationLicense(TimeStampedModel):
    installation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    provider_mode = models.CharField(max_length=24, default="development")
    status = models.CharField(max_length=24, choices=LicenseStatus.choices, default=LicenseStatus.TRIAL)
    trial_started_at = models.DateTimeField(default=timezone.now)
    trial_expires_at = models.DateTimeField()
    license_expires_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(default=timezone.now)
    last_seen_monotonic_ts = models.BigIntegerField(default=0)
    signed_token = models.TextField(blank=True)
    licensed_modules = models.JSONField(default=list, blank=True)

    @property
    def is_write_allowed(self) -> bool:
        return self.status in {LicenseStatus.TRIAL, LicenseStatus.ACTIVE}