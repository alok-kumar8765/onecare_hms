from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserRole
from billing.services import create_invoice_with_items
from tenants.models import DeploymentPreset
from tenants.services import create_tenant_branch, provision_tenant


@pytest.mark.django_db
def test_cross_tenant_branch_id_rejected_and_branch_filter_scopes_invoices():
    tenant_a = provision_tenant(name="Hospital Alpha", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    tenant_b = provision_tenant(name="Hospital Beta", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    branch_a2 = create_tenant_branch(tenant_id=tenant_a.id, name="Alpha East", code="AEAST")
    branch_b1 = tenant_b.branches.first()

    main_branch_a = tenant_a.branches.filter(is_main=True).first()
    create_invoice_with_items(
        tenant_id=tenant_a.id,
        branch_id=main_branch_a.id if main_branch_a else None,
        customer_name="Main Branch Patient",
        items=[{"description": "OPD Fee", "quantity": 1, "unit_price": Decimal("200.00")}],
    )
    create_invoice_with_items(
        tenant_id=tenant_a.id,
        branch_id=branch_a2.id,
        customer_name="East Branch Patient",
        items=[{"description": "Lab Fee", "quantity": 1, "unit_price": Decimal("400.00")}],
    )

    user_a = User.objects.create_user(
        username="acct_alpha",
        password="StrongPassword123!",
        tenant_id=tenant_a.id,
        role=UserRole.ACCOUNTANT,
    )
    client = Client()
    client.force_login(user_a)

    # Filtering by Alpha East returns only that branch's invoice
    resp_filtered = client.get(reverse("api-billing-invoices") + f"?branch_id={branch_a2.id}")
    assert resp_filtered.status_code == 200
    assert len(resp_filtered.json()) == 1
    assert resp_filtered.json()[0]["customer_name"] == "East Branch Patient"

    # Attempting to create an invoice under Beta's branch_id must be rejected with 400
    resp_spoof = client.post(
        reverse("api-billing-invoices"),
        data={
            "customer_name": "Spoofed Branch",
            "branch_id": str(branch_b1.id),
            "items": [{"description": "Item", "quantity": 1, "unit_price": "100.00"}],
        },
        content_type="application/json",
    )
    assert resp_spoof.status_code == 400