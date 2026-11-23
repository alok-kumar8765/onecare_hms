from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserRole
from billing.models import InvoiceStatus, PaymentMethod
from billing.services import create_invoice_with_items, record_expense, record_invoice_payment, summarize_finance
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_invoice_partial_and_full_payment_and_overpayment_guard():
    tenant = provision_tenant(name="Lifeline Billing", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    inv = create_invoice_with_items(
        tenant_id=tenant.id,
        customer_name="Deepak Joshi",
        discount_amount=Decimal("50.00"),
        items=[
            {
                "description": "Specialist Consultation",
                "category": "OPD",
                "quantity": 1,
                "unit_price": Decimal("500.00"),
                "gst_rate_percent": Decimal("18.00"),
            }
        ],
    )
    # 500 + 90 GST - 50 discount = 540.00
    assert inv.total_amount == Decimal("540.00")

    record_invoice_payment(
        tenant_id=tenant.id,
        invoice_id=inv.id,
        amount=Decimal("200.00"),
        method=PaymentMethod.UPI,
        reference_no="UPI-12345",
    )
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PARTIALLY_PAID
    assert inv.balance_due == Decimal("340.00")

    with pytest.raises(ValueError):
        record_invoice_payment(
            tenant_id=tenant.id,
            invoice_id=inv.id,
            amount=Decimal("400.00"),
            method=PaymentMethod.CASH,
        )

    record_invoice_payment(
        tenant_id=tenant.id,
        invoice_id=inv.id,
        amount=Decimal("340.00"),
        method=PaymentMethod.CASH,
    )
    inv.refresh_from_db()
    assert inv.status == InvoiceStatus.PAID
    assert inv.balance_due == Decimal("0.00")

    record_expense(tenant_id=tenant.id, title="Clinic Power Bill", amount=Decimal("140.00"))
    summary = summarize_finance(tenant_id=tenant.id)
    assert summary["total_collected"] == Decimal("540.00")
    assert summary["total_expenses"] == Decimal("140.00")
    assert summary["net_cashflow"] == Decimal("400.00")


@pytest.mark.django_db
def test_billing_cross_tenant_isolation():
    tenant_a = provision_tenant(name="Billing A", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    tenant_b = provision_tenant(name="Billing B", deployment_preset=DeploymentPreset.STANDALONE_CLINIC)
    create_invoice_with_items(
        tenant_id=tenant_a.id,
        customer_name="Patient A",
        items=[{"description": "Consult", "quantity": 1, "unit_price": Decimal("300.00")}],
    )
    user_b = User.objects.create_user(
        username="acct_b",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.ACCOUNTANT,
    )
    client = Client()
    client.force_login(user_b)
    resp = client.get(reverse("api-billing-invoices"))
    assert resp.status_code == 200
    assert resp.json() == []