from __future__ import annotations
import pytest
from django.template import loader
from django.test import Client
from django.urls import reverse
from core.branding import DEVELOPER_NAME, COPYRIGHT_YEAR, get_locked_footer_html, verify_branding_integrity
from accounts.models import User, UserRole
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


def test_branding_integrity_and_html_helper():
    assert DEVELOPER_NAME == "Alok Kumar Kaushal"
    assert COPYRIGHT_YEAR == "2026"
    assert verify_branding_integrity() is True

    footer_html = get_locked_footer_html()
    assert "Developed By - Alok Kumar Kaushal" in footer_html
    assert "Copyright &copy; 2026" in footer_html


def test_locked_footer_in_base_jinja2_template():
    template = loader.get_template("base.html")
    rendered = template.render({"request": None})
    assert "Developed By - Alok Kumar Kaushal" in rendered
    assert "Copyright &copy; 2026" in rendered


@pytest.mark.django_db
def test_locked_footer_in_web_views():
    client = Client()

    # 1. Login view
    login_resp = client.get(reverse("accounts-login"))
    assert login_resp.status_code == 200
    assert "Developed By - Alok Kumar Kaushal" in login_resp.content.decode("utf-8")
    assert "Copyright &copy; 2026" in login_resp.content.decode("utf-8")

    # 2. Licensing status view (authenticated)
    tenant = provision_tenant(name="City Care Hospital", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    user = User.objects.create_user(
        username="city_admin",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.HOSPITAL_OWNER,
    )
    client.force_login(user)
    lic_resp = client.get(reverse("licensing-status"))
    assert lic_resp.status_code == 200
    assert "Developed By - Alok Kumar Kaushal" in lic_resp.content.decode("utf-8")
    assert "Copyright &copy; 2026" in lic_resp.content.decode("utf-8")
