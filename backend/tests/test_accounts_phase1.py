import uuid
import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserDevice
from accounts.services import _generate_totp_code, issue_whatsapp_otp, verify_whatsapp_otp
from core.models import AuditLog


@pytest.mark.django_db
def test_login_lockout_and_audit_log():
    tenant_a = uuid.uuid4()
    user = User.objects.create_user(
        username="dr_sharma",
        password="StrongPassword123!",
        tenant_id=tenant_a,
        role="DOCTOR",
    )
    client = Client()
    url = reverse("api-accounts-login")

    for _ in range(5):
        resp = client.post(url, {"username": "dr_sharma", "password": "WrongPassword!"}, content_type="application/json")
        assert resp.status_code == 401

    locked_resp = client.post(url, {"username": "dr_sharma", "password": "StrongPassword123!"}, content_type="application/json")
    assert locked_resp.status_code == 423
    assert locked_resp.json()["status"] == "locked"
    assert AuditLog.objects.filter(tenant_id=tenant_a, action="auth.login.locked").exists()


@pytest.mark.django_db
def test_new_device_alert_and_totp_2fa_login():
    tenant_a = uuid.uuid4()
    user = User.objects.create_user(
        username="nurse_priya",
        password="StrongPassword123!",
        tenant_id=tenant_a,
        role="NURSE",
        two_factor_enabled=True,
        totp_verified=True,
    )
    secret = user.ensure_totp_secret()
    client = Client(HTTP_USER_AGENT="Mozilla/5.0 TestBrowser", REMOTE_ADDR="10.0.0.5")
    url = reverse("api-accounts-login")

    first_resp = client.post(url, {"username": "nurse_priya", "password": "StrongPassword123!"}, content_type="application/json")
    assert first_resp.status_code == 202
    assert first_resp.json()["status"] == "2fa_required"
    assert first_resp.json()["new_device_alert"] is True

    valid_code = _generate_totp_code(secret)
    second_resp = client.post(
        url,
        {"username": "nurse_priya", "password": "StrongPassword123!", "totp_code": valid_code},
        content_type="application/json",
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["status"] == "authenticated"


@pytest.mark.django_db
def test_mock_whatsapp_otp_and_tenant_device_isolation():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_a = User.objects.create_user(username="staff_a", password="StrongPassword123!", tenant_id=tenant_a, phone_number="+919800000001")
    user_b = User.objects.create_user(username="staff_b", password="StrongPassword123!", tenant_id=tenant_b, phone_number="+919800000002")

    challenge, plain_otp = issue_whatsapp_otp(user_a, provider_mode="mock")
    assert verify_whatsapp_otp(challenge, plain_otp) is True
    assert verify_whatsapp_otp(challenge, plain_otp) is False  # Single-use enforced

    device_b = UserDevice.objects.create(
        tenant_id=tenant_b,
        user=user_b,
        device_fingerprint="fp-tenant-b",
        device_label="Tenant B Device",
    )
    client = Client()
    client.force_login(user_a)
    approve_url = reverse("api-accounts-device-approve", kwargs={"device_id": device_b.id})
    resp = client.post(approve_url, content_type="application/json")
    assert resp.status_code == 404