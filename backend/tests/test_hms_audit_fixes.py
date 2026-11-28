import hashlib
import base64
import hmac
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from accounts.models import User, UserDevice, UserRole
from accounts.services import (
    issue_whatsapp_otp,
    verify_whatsapp_otp,
    _generate_totp_code,
    approve_user_device,
    evaluate_login_attempt,
    verify_totp_code,
)
from licensing.providers import CentralLicensingProvider
import uuid
import pytest
from django.core.management import call_command
from clinic.models import Patient
from clinic.services import (
    create_opd_encounter_with_prescription,
    register_patient,
    schedule_appointment,
)
from decimal import Decimal
from billing.services import record_expense
from ipd.services import create_ward_with_beds
from laboratory.models import LabOrder, LabOrderStatus
from laboratory.services import mark_sample_collected, record_test_result
from pharmacy.services import add_medicine_and_batch, dispense_fefo_sale
import sqlite3

from core.scoping import validate_patient_branch_alignment
from licensing.models import LicenseStatus
from licensing.services import activate_signed_license, get_or_start_installation_license

try:
    from tenants.models import Branch, Tenant
except ImportError:
    from clinic.models import Branch
    Tenant = None

# @pytest.mark.django_db
# def test_mark_sample_collected_rejects_order_without_sample():
#     tenant_id = uuid.uuid4()
#     order = LabOrder.objects.create(
#         tenant_id=tenant_id,
#         order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}",
#         status=LabOrderStatus.ORDERED,
#     )
#     with pytest.raises(ValueError, match="No sample record found"):
#         mark_sample_collected(tenant_id=tenant_id, order_id=order.id)


@pytest.mark.django_db
def test_mark_sample_collected_rejects_order_without_sample():
    tenant_id = uuid.uuid4()

    patient, _ = register_patient(tenant_id=tenant_id, full_name="Test Patient", phone_number="+919811111111",)

    order = LabOrder.objects.create(tenant_id=tenant_id, patient=patient, order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}", status=LabOrderStatus.ORDERED,)

    with pytest.raises(ValueError, match="No sample record found"):
        mark_sample_collected(tenant_id=tenant_id, order_id=order.id,)


# @pytest.mark.django_db
# def test_record_test_result_blocked_when_order_verified_or_delivered():
#     tenant_id = uuid.uuid4()
#     order = LabOrder.objects.create(
#         tenant_id=tenant_id,
#         order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}",
#         status=LabOrderStatus.VERIFIED,
#     )
#     item = order.items.first()
#     if item is not None:
#         with pytest.raises(ValueError, match="verified or delivered"):
#             record_test_result(
#                 tenant_id=tenant_id,
#                 order_item_id=item.id,
#                 observed_value="14.2",
#                 is_abnormal=False,
#             )

@pytest.mark.django_db
def test_record_test_result_blocked_when_order_verified_or_delivered():
    tenant_id = uuid.uuid4()

    patient, _ = register_patient(tenant_id=tenant_id, full_name="Test Patient", phone_number="+919822222222",)

    order = LabOrder.objects.create(tenant_id=tenant_id, patient=patient, order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}", status=LabOrderStatus.VERIFIED,)

    item = order.items.first()

    if item is not None:
        with pytest.raises(ValueError, match="verified or delivered"):
            record_test_result(tenant_id=tenant_id, order_item_id=item.id, observed_value="14.2", is_abnormal=False,)


@pytest.mark.django_db
def test_expense_and_ward_reject_nonexistent_branch():
    tenant_id = uuid.uuid4()
    missing_branch_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Selected branch does not exist"):
        record_expense(
            tenant_id=tenant_id,
            title="Generator Diesel",
            amount=Decimal("500.00"),
            branch_id=missing_branch_id,
        )

    with pytest.raises(ValueError, match="Selected branch does not exist"):
        create_ward_with_beds(
            tenant_id=tenant_id,
            branch_id=missing_branch_id,
            code="GW-1",
            name="General Ward",
            daily_charge=Decimal("1000.00"),
            bed_count=2,
        )

def _create_test_tenant_and_branch():
    tenant = None
    tenant_id = uuid.uuid4()

    if Tenant is not None:
        tenant = Tenant()
        for field in Tenant._meta.fields:
            if field.primary_key or field.auto_created:
                continue
            if field.name == "name":
                setattr(tenant, field.name, f"Test Hospital {uuid.uuid4().hex[:6]}")
            elif field.name == "slug":
                setattr(tenant, field.name, f"test-hospital-{uuid.uuid4().hex[:8]}")
            elif field.name == "code":
                setattr(tenant, field.name, f"TEN-{uuid.uuid4().hex[:6].upper()}")
            elif not field.null and not field.has_default():
                if field.get_internal_type() in ("CharField", "TextField"):
                    setattr(tenant, field.name, f"val-{uuid.uuid4().hex[:6]}")
                elif field.get_internal_type() in ("IntegerField", "BigIntegerField", "PositiveIntegerField"):
                    setattr(tenant, field.name, 1)
                elif field.get_internal_type() == "BooleanField":
                    setattr(tenant, field.name, True)
        tenant.save()
        tenant_id = tenant.id

    branch = Branch()
    for field in Branch._meta.fields:
        if field.primary_key or field.auto_created:
            continue
        if field.name == "tenant" and tenant is not None:
            setattr(branch, field.name, tenant)
        elif field.name == "tenant_id":
            setattr(branch, field.name, tenant_id)
        elif field.name == "name":
            setattr(branch, field.name, "Main OPD Branch")
        elif field.name == "code":
            setattr(branch, field.name, f"BR-{uuid.uuid4().hex[:6].upper()}")
        elif not field.null and not field.has_default():
            if field.get_internal_type() in ("CharField", "TextField"):
                setattr(branch, field.name, f"br-{uuid.uuid4().hex[:6]}")
            elif field.get_internal_type() in ("IntegerField", "BigIntegerField", "PositiveIntegerField"):
                setattr(branch, field.name, 1)
            elif field.get_internal_type() == "BooleanField":
                setattr(branch, field.name, True)
    branch.save()
    return tenant_id, branch


@pytest.mark.django_db
def test_patient_appointment_encounter_prescription_flow():
    tenant_id, branch = _create_test_tenant_and_branch()

    patient, _ = register_patient(
        tenant_id=tenant_id,
        full_name="Aarav Sharma",
        branch_id=branch.id,
        phone_number="9876543210",
        allergies_notes="Penicillin",
    )
    assert patient.tenant_id == tenant_id
    assert patient.branch_id == branch.id

    appt = schedule_appointment(
        tenant_id=tenant_id,
        patient=patient,
        branch_id=patient.branch_id,
        reason="Fever",
    )
    assert appt.token_number >= 1

    encounter, prescription = create_opd_encounter_with_prescription(
        tenant_id=tenant_id,
        patient=patient,
        appointment=appt,
        branch_id=patient.branch_id,
        chief_complaint="Fever for 2 days",
        diagnosis="Viral fever",
        items=[{"medicine_name": "Paracetamol 500mg"}],
    )
    assert encounter.id is not None
    assert prescription.items.count() == 1


@pytest.mark.django_db
def test_nonexistent_branch_rejected_on_registration():
    tenant_id = uuid.uuid4()
    missing_branch_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Selected branch does not exist"):
        register_patient(
            tenant_id=tenant_id,
            full_name="Branch Check Patient",
            branch_id=missing_branch_id,
            phone_number="9876500002",
        )


@pytest.mark.django_db
def test_cross_tenant_patient_lookup_isolated():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    patient_a, _ = register_patient(
        tenant_id=tenant_a,
        full_name="Meera Nair",
        phone_number="9876500001",
    )

    assert Patient.objects.filter(id=patient_a.id, tenant_id=tenant_b).count() == 0


def test_backup_hms_verify_detects_tampered_artifact(tmp_path):
    backup_file = tmp_path / "onecare_sqlite_test.sqlite3"
    backup_file.write_bytes(b"SQLite format 3\x00original-data")
    sha_file = tmp_path / "onecare_sqlite_test.sqlite3.sha256"

    digest = hashlib.sha256(backup_file.read_bytes()).hexdigest()
    sha_file.write_text(f"{digest}  {backup_file.name}\n", encoding="utf-8")

    call_command("backup_hms", mode="verify", file=str(backup_file))

    backup_file.write_bytes(b"SQLite format 3\x00tampered-data")
    with pytest.raises(Exception):
        call_command("backup_hms", mode="verify", file=str(backup_file))


def test_backup_and_restore_on_isolated_temp_sqlite_db(tmp_path, settings):
    source_db = tmp_path / "source_hms.sqlite3"
    backup_dir = tmp_path / "backups"
    target_db = tmp_path / "restored_hms.sqlite3"

    conn = sqlite3.connect(str(source_db))
    try:
        conn.execute("CREATE TABLE smoke_check (id INTEGER PRIMARY KEY, label TEXT)")
        conn.execute("INSERT INTO smoke_check (label) VALUES ('before-restore')")
        conn.commit()
    finally:
        conn.close()

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(source_db),
    }
    call_command("backup_hms", mode="backup", output_dir=str(backup_dir), retention_days=0)

    artifacts = [p for p in backup_dir.iterdir() if p.is_file() and not p.name.endswith(".sha256")]
    assert len(artifacts) == 1
    artifact = artifacts[0]

    call_command("backup_hms", mode="verify", file=str(artifact))

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(target_db),
    }
    call_command("backup_hms", mode="restore", file=str(artifact))

    restored_conn = sqlite3.connect(str(target_db))
    try:
        rows = restored_conn.execute("SELECT label FROM smoke_check").fetchall()
        assert rows == [("before-restore",)]
    finally:
        restored_conn.close()


@pytest.mark.django_db
def test_whatsapp_otp_issue_and_single_use_verification(settings):
    settings.SECRET_KEY = "test-secret-key-for-otp-hashing"

    # user = User.objects.create_user(
    #     username="nurse_otp",
    #     password="StrongPassword123!",
    #     phone_number="9876543211",
    # )
    user = User.objects.create_user(username=f"nurse_otp_{uuid.uuid4().hex[:8]}", password="StrongPassword123!", phone_number="9876543211",)

    challenge, otp_code = issue_whatsapp_otp(
        user,
        provider_mode="mock",
    )

    assert verify_whatsapp_otp(challenge, otp_code) is True

    challenge.refresh_from_db()
    assert challenge.is_consumed is True

    # Same OTP cannot be reused.
    assert verify_whatsapp_otp(challenge, otp_code) is False


@pytest.mark.django_db
def test_central_licensing_provider_rejects_invalid_token(settings):
    settings.LICENSE_SIGNING_SECRET = "unit-test-signing-secret"

    provider = CentralLicensingProvider()

    assert provider.verify_signed_token("not-a-valid-token") is None
    assert provider.verify_signed_token("e30=.badsignature") is None


@pytest.mark.django_db
def test_central_licensing_provider_rejects_expired_token(settings):
    secret = "unit-test-signing-secret"
    settings.LICENSE_SIGNING_SECRET = secret

    payload = {
        "license_id": "TEST-001",
        "expires_at": (
            datetime.now(dt_timezone.utc) - timedelta(days=1)
        ).isoformat(),
    }

    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("utf-8").rstrip("=")

    signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    token = f"{payload_b64}.{signature}"

    provider = CentralLicensingProvider()

    assert provider.verify_signed_token(token) is None



@pytest.mark.django_db
def test_whatsapp_otp_rejects_after_five_wrong_attempts(settings):
    settings.SECRET_KEY = "test-secret-key-for-otp-hashing"

    user = User.objects.create_user(
        username=f"nurse_attempt_{uuid.uuid4().hex[:8]}",
        password="StrongPassword123!",
        phone_number="9876543212",
    )

    challenge, otp_code = issue_whatsapp_otp(
        user,
        provider_mode="mock",
    )

    # Ensure the incorrect OTP is always different from the actual OTP.
    wrong_code = "000000" if otp_code != "000000" else "000001"

    # Five incorrect attempts should be rejected.
    for _ in range(5):
        assert verify_whatsapp_otp(challenge, wrong_code) is False

    challenge.refresh_from_db()

    assert challenge.attempts == 5
    assert challenge.is_consumed is False

    # Correct OTP must also fail after the maximum attempt limit.
    assert verify_whatsapp_otp(challenge, otp_code) is False

    challenge.refresh_from_db()
    assert challenge.attempts == 5


def _make_signed_token(payload: dict, secret: str) -> str:
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    sig_hex = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{sig_hex}"


@pytest.mark.django_db
def test_totp_lockout_and_device_approval_flow(settings):
    settings.MAX_FAILED_LOGIN_ATTEMPTS = 2
    settings.LOGIN_LOCKOUT_MINUTES = 15

    user = User.objects.create_user(
        username="doc_security_test",
        password="StrongPassword123!",
        phone_number="9876543219",
    )
    secret = user.ensure_totp_secret()
    valid_totp = _generate_totp_code(secret)
    assert verify_totp_code(secret, valid_totp) is True

    # Two bad passwords trigger account lockout
    r1 = evaluate_login_attempt(username="doc_security_test", password="wrong", ip_address="127.0.0.1")
    assert r1["ok"] is False
    r2 = evaluate_login_attempt(username="doc_security_test", password="wrong", ip_address="127.0.0.1")
    assert r2["ok"] is False

    user.refresh_from_db()
    assert user.is_account_locked is True

    # Unlock and verify login + device approval
    user.locked_until = None
    user.failed_login_attempts = 0
    user.save(update_fields=["locked_until", "failed_login_attempts"])

    ok_res = evaluate_login_attempt(
        username="doc_security_test",
        password="StrongPassword123!",
        user_agent="TestBrowser/1.0",
        ip_address="127.0.0.1",
    )
    assert ok_res["ok"] is True
    device: UserDevice = ok_res["device"]
    assert device.is_trusted is False

    approved = approve_user_device(user=user, device_id=device.id)
    assert approved is not None
    assert approved.is_trusted is True


@pytest.mark.django_db
def test_signed_license_activation_and_expired_rejection(settings):
    secret = "test-hmac-signing-secret-key"
    settings.LICENSE_PROVIDER = "central"
    settings.LICENSE_SIGNING_SECRET = secret

    # Create a real tenant before activating module entitlements.
    tenant = Tenant.objects.create(
        name="Test Clinic",
        slug=f"test-clinic-{uuid.uuid4().hex[:8]}",
    )
    tenant_id = tenant.id

    lic = get_or_start_installation_license(tenant_id=tenant_id)

    expired_token = _make_signed_token(
        {
            "client_name": "Test Clinic",
            "tenant_id": str(tenant_id),
            "installation_id": str(lic.installation_id),
            "expires_at": (
                timezone.now() - timedelta(days=1)
            ).isoformat(),
            "modules": ["CLINIC_OPD"],
        },
        secret,
    )

    ok_exp, _, _ = activate_signed_license(
        tenant_id=tenant_id,
        signed_token=expired_token,
    )
    assert ok_exp is False

    valid_token = _make_signed_token(
        {
            "client_name": "Test Clinic",
            "tenant_id": str(tenant_id),
            "installation_id": str(lic.installation_id),
            "expires_at": (
                timezone.now() + timedelta(days=365)
            ).isoformat(),
            "modules": ["CLINIC_OPD", "BILLING"],
        },
        secret,
    )

    ok_val, _, updated_lic = activate_signed_license(
        tenant_id=tenant_id,
        signed_token=valid_token,
    )

    assert ok_val is True
    assert updated_lic.status == LicenseStatus.ACTIVE


@pytest.mark.django_db
def test_patient_branch_alignment_rejects_mismatched_branch():
    from clinic.models import Patient

    tenant_a = uuid.uuid4()
    branch_1 = uuid.uuid4()
    branch_2 = uuid.uuid4()
    patient = Patient.objects.create(
        tenant_id=tenant_a,
        branch_id=branch_1,
        full_name="Branch Aligned Patient",
    )
    with pytest.raises(ValueError):
        validate_patient_branch_alignment(
            tenant_id=tenant_a,
            patient=patient,
            branch_id=branch_2,
        )
@pytest.mark.django_db
def test_setup_wizard_rejects_cross_tenant_branch_on_staff_creation(client):
    from django.urls import reverse

    from tenants.models import Tenant, Branch

    # Create two separate hospitals.
    tenant_a = Tenant.objects.create(
        name="Hospital Alpha",
        slug=f"hospital-alpha-{uuid.uuid4().hex[:8]}",
    )

    tenant_b = Tenant.objects.create(
        name="Hospital Beta",
        slug=f"hospital-beta-{uuid.uuid4().hex[:8]}",
    )

    # Create a branch belonging to Hospital Beta.
    branch_b = Branch.objects.create(
        tenant=tenant_b,
        name="Beta Wing",
        code=f"BW-{uuid.uuid4().hex[:6].upper()}",
    )

    # Create Hospital Alpha admin.
    admin_a = User.objects.create_user(
        username=f"admin_alpha_{uuid.uuid4().hex[:6]}",
        password="StrongPassword123!",
        role=UserRole.HOSPITAL_ADMIN,
        tenant_id=tenant_a.id,
    )

    client.force_login(admin_a)

    url = reverse("tenants-setup-wizard")

    # Try assigning Hospital Beta branch to Hospital Alpha staff.
    response = client.post(
        url,
        {
            "action": "create_staff",
            "tenant_id": str(tenant_a.id),
            "username": f"rogue_staff_{uuid.uuid4().hex[:6]}",
            "password": "StrongPassword123!",
            "role": UserRole.NURSE,
            "branch_id": str(branch_b.id),
        },
    )

    assert response.status_code == 200

    # Staff must not be created.
    assert not User.objects.filter(
        username__startswith="rogue_staff_"
    ).exists()

    # Validation error should be displayed.
    assert (
        b"Selected branch does not belong to the active organization."
        in response.content
    )