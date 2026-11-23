from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from accounts.models import User, UserRole
from clinic.services import register_patient
from laboratory.models import LabOrderStatus
from laboratory.services import (
    create_lab_order,
    create_lab_test,
    deliver_lab_report,
    mark_sample_collected,
    record_test_result,
    verify_lab_order,
)
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_lab_workflow_verification_gate_and_role_enforcement():
    tenant = provision_tenant(name="DiagnoCare Labs", deployment_preset=DeploymentPreset.CLINIC_LAB)
    tech = User.objects.create_user(
        username="lab_tech_1",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.LAB_TECHNICIAN,
    )
    manager = User.objects.create_user(
        username="lab_mgr_1",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.LAB_MANAGER,
    )

    patient, _ = register_patient(tenant_id=tenant.id, full_name="Kavita Joshi", phone_number="+919833333333")
    hb_test = create_lab_test(
        tenant_id=tenant.id,
        code="HB",
        name="Hemoglobin",
        price=Decimal("250.00"),
        reference_range="12.0 - 15.5",
        unit="g/dL",
        gst_rate_percent=Decimal("0.00"),
    )

    order = create_lab_order(tenant_id=tenant.id, patient=patient, test_ids=[str(hb_test.id)], actor=tech)
    assert order.sample.barcode.startswith("SMP-")
    assert order.total_amount == Decimal("250.00")

    mark_sample_collected(tenant_id=tenant.id, order_id=order.id, actor=tech)
    item = order.items.first()
    record_test_result(tenant_id=tenant.id, order_item_id=item.id, observed_value="13.4", actor=tech)

    # Unverified report cannot be delivered
    with pytest.raises(ValueError):
        deliver_lab_report(tenant_id=tenant.id, order_id=order.id, actor=tech)

    # Lab technician cannot self-verify
    with pytest.raises(PermissionError):
        verify_lab_order(tenant_id=tenant.id, order_id=order.id, actor=tech)

    # Lab manager verifies and delivers report
    verified = verify_lab_order(tenant_id=tenant.id, order_id=order.id, actor=manager)
    assert verified.status == LabOrderStatus.VERIFIED
    delivered = deliver_lab_report(tenant_id=tenant.id, order_id=order.id, actor=manager)
    assert delivered.status == LabOrderStatus.DELIVERED


@pytest.mark.django_db
def test_laboratory_cross_tenant_isolation():
    tenant_a = provision_tenant(name="Lab A", deployment_preset=DeploymentPreset.STANDALONE_LAB)
    tenant_b = provision_tenant(name="Lab B", deployment_preset=DeploymentPreset.STANDALONE_LAB)

    create_lab_test(tenant_id=tenant_a.id, code="CBC", name="Complete Blood Count", price=Decimal("400.00"))
    user_b = User.objects.create_user(
        username="lab_b_user",
        password="StrongPassword123!",
        tenant_id=tenant_b.id,
        role=UserRole.LAB_TECHNICIAN,
    )

    client = Client()
    client.force_login(user_b)
    resp = client.get(reverse("api-lab-tests"))
    assert resp.status_code == 200
    assert resp.json() == []