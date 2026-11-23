from datetime import timedelta
from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, UserRole
from pharmacy.services import add_medicine_and_batch, dispense_fefo_sale, search_medicines
from tenants.models import DeploymentPreset, ModuleCode
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_fefo_dispensing_and_insufficient_stock_rollback():
    tenant = provision_tenant(name="Apollo Pharmacy", deployment_preset=DeploymentPreset.STANDALONE_PHARMACY)
    today = timezone.localdate()

    med, batch_later = add_medicine_and_batch(
        tenant_id=tenant.id,
        brand_name="Augmentin 625",
        salt_composition="Amoxicillin + Clavulanic Acid",
        batch_number="B-LATER",
        expiry_date=today + timedelta(days=180),
        quantity=10,
        unit_price=Decimal("20.00"),
        gst_rate_percent=Decimal("12.00"),
    )
    _, batch_sooner = add_medicine_and_batch(
        tenant_id=tenant.id,
        brand_name="Augmentin 625",
        salt_composition="Amoxicillin + Clavulanic Acid",
        batch_number="B-SOONER",
        expiry_date=today + timedelta(days=30),
        quantity=6,
        unit_price=Decimal("20.00"),
        gst_rate_percent=Decimal("12.00"),
    )

    sale = dispense_fefo_sale(
        tenant_id=tenant.id,
        items_requested=[{"medicine_id": str(med.id), "quantity": 8}],
        customer_name="Amit Kumar",
    )
    batch_sooner.refresh_from_db()
    batch_later.refresh_from_db()

    # Earliest-expiry batch is exhausted first (6 units), then 2 units from later batch
    assert batch_sooner.quantity_on_hand == 0
    assert batch_later.quantity_on_hand == 8
    assert sale.subtotal_amount == Decimal("160.00")
    assert sale.gst_amount == Decimal("19.20")
    assert sale.total_amount == Decimal("179.20")

    # Attempting to oversell must fail and leave remaining 8 units untouched
    with pytest.raises(ValueError):
        dispense_fefo_sale(
            tenant_id=tenant.id,
            items_requested=[{"medicine_id": str(med.id), "quantity": 9}],
        )
    batch_later.refresh_from_db()
    assert batch_later.quantity_on_hand == 8

    # Salt search works
    assert search_medicines(tenant_id=tenant.id, query="Clavulanic").count() == 1


@pytest.mark.django_db
def test_pharmacy_cross_tenant_isolation():
    tenant_a = provision_tenant(name="MedPlus A", deployment_preset=DeploymentPreset.STANDALONE_PHARMACY)
    tenant_b = provision_tenant(name="MedPlus B", deployment_preset=DeploymentPreset.STANDALONE_PHARMACY)
    today = timezone.localdate()

    add_medicine_and_batch(
        tenant_id=tenant_a.id,
        brand_name="Pan D",
        salt_composition="Pantoprazole + Domperidone",
        batch_number="B1",
        expiry_date=today + timedelta(days=90),
        quantity=20,
        unit_price=Decimal("15.00"),
    )

    user_b = User.objects.create_user(
        username="pharma_b",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.PHARMACIST,
    )
    client = Client()
    client.force_login(user_b)
    resp = client.get(reverse("api-pharmacy-medicines"))
    assert resp.status_code == 200
    assert resp.json() == []