from typing import Optional
import uuid
from django.conf import settings
from django.db import models
from core.models import TimeStampedModel


class ModuleCode(models.TextChoices):
    HOSPITAL_IPD = "HOSPITAL_IPD", "Hospital & IPD Management"
    CLINIC_OPD = "CLINIC_OPD", "Clinic, OPD & EMR"
    LABORATORY = "LABORATORY", "Laboratory & Diagnostics"
    PHARMACY = "PHARMACY", "Pharmacy & Inventory"
    BILLING = "BILLING", "Billing & Accounting"
    HR = "HR", "HR & Staff Management"
    ANALYTICS = "ANALYTICS", "Reporting & Analytics"
    IPD = "IPD", "Hospital & IPD Management"


class DeploymentPreset(models.TextChoices):
    FULL_HOSPITAL = "FULL_HOSPITAL", "Full Hospital Management"
    STANDALONE_CLINIC = "STANDALONE_CLINIC", "Standalone Clinic Management"
    CLINIC_LAB = "CLINIC_LAB", "Clinic + Laboratory"
    CLINIC_PHARMACY = "CLINIC_PHARMACY", "Clinic + Pharmacy"
    STANDALONE_PHARMACY = "STANDALONE_PHARMACY", "Standalone Pharmacy"
    STANDALONE_LAB = "STANDALONE_LAB", "Standalone Laboratory"


class SubscriptionPlan(TimeStampedModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    deployment_preset = models.CharField(
        max_length=32,
        choices=DeploymentPreset.choices,
        default=DeploymentPreset.STANDALONE_CLINIC,
    )
    max_branches = models.PositiveIntegerField(default=1)
    default_modules = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Tenant(TimeStampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    legal_name = models.CharField(max_length=220, blank=True)
    gstin = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tenants",
    )

    def __str__(self) -> str:
        return self.name


class Branch(TimeStampedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=40)
    is_main = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        unique_together = [("tenant", "code")]

    def __str__(self) -> str:
        return f"{self.tenant.name} - {self.name}"


class ModuleEntitlement(TimeStampedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="entitlements")
    module_code = models.CharField(max_length=32, choices=ModuleCode.choices, db_index=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [("tenant", "module_code")]

    def __str__(self) -> str:
        state = "ENABLED" if self.is_enabled else "DISABLED"
        return f"{self.tenant.slug}:{self.module_code} ({state})"


class UserBranchAccess(TimeStampedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="user_branch_accesses")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="user_accesses")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="branch_accesses")
    can_manage_branch = models.BooleanField(default=False)

    class Meta:
        unique_together = [("branch", "user")]

class PlatformAnnouncement(TimeStampedModel):
    title = models.CharField(max_length=180)
    message = models.TextField()
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_announcements",
    )

    class Meta:
        ordering = ["-created_at"]