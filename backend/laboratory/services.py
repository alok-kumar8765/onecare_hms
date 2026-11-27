from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from accounts.models import UserRole
from clinic.models import Patient
from core.audit import record_audit_log
from core.import_export import export_rows_to_csv
from .models import LabOrder, LabOrderItem, LabOrderStatus, LabResult, LabSample, LabTest

VERIFIER_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.HOSPITAL_OWNER,
    UserRole.HOSPITAL_ADMIN,
    UserRole.LAB_MANAGER,
    UserRole.DOCTOR,
}
from core.scoping import resolve_scoped_branch_id, validate_patient_branch_alignment

def _quantize_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def create_lab_test(
    *,
    tenant_id,
    code: str,
    name: str,
    price: Decimal,
    department: str = "Pathology",
    sample_type: str = "Whole Blood / Serum",
    reference_range: str = "",
    unit: str = "",
    gst_rate_percent: Decimal = Decimal("0.00"),
    actor=None,
    request=None,
) -> LabTest:
    clean_code = code.strip().upper()
    if not clean_code or not name.strip():
        raise ValueError("Test code and name are required.")
    test, _ = LabTest.objects.update_or_create(
        tenant_id=tenant_id,
        code=clean_code,
        defaults={
            "name": name.strip(),
            "department": department.strip() or "Pathology",
            "sample_type": sample_type.strip() or "Whole Blood / Serum",
            "reference_range": reference_range.strip(),
            "unit": unit.strip(),
            "price": _quantize_money(price),
            "gst_rate_percent": gst_rate_percent,
            "is_active": True,
        },
    )
    record_audit_log(
        action="lab.test.saved",
        resource_type="LabTest",
        resource_id=test.id,
        actor=actor,
        tenant_id=tenant_id,
        request=request,
        metadata={"code": test.code, "name": test.name},
    )
    return test


@transaction.atomic
def create_lab_order(
    *,
    tenant_id,
    patient: Patient,
    test_ids: List[str],
    branch_id=None,
    notes: str = "",
    actor=None,
    request=None,
) -> LabOrder:
    
    scoped_branch_id = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id,
    fallback_branch_id=getattr(patient, "branch_id", None) if patient else None,
    )
    validate_patient_branch_alignment(
        tenant_id=tenant_id,
        patient=patient,
        branch_id=scoped_branch_id,
    )
    if not test_ids:
        raise ValueError("At least one lab test must be selected.")
    tests = list(LabTest.objects.filter(tenant_id=tenant_id, id__in=test_ids, is_active=True))
    if not tests:
        raise ValueError("No valid lab tests found for your organization.")

    order_no = f"LAB-{timezone.localdate().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    order = LabOrder.objects.create(
        tenant_id=tenant_id,
        branch_id=scoped_branch_id or patient.branch_id,
        order_number=order_no,
        patient=patient,
        ordered_by=actor,
        status=LabOrderStatus.ORDERED,
        notes=notes.strip(),
    )

    subtotal = Decimal("0.00")
    total_gst = Decimal("0.00")
    sample_types = []

    for test in tests:
        base_price = _quantize_money(test.price)
        line_gst = _quantize_money((base_price * test.gst_rate_percent) / Decimal("100"))
        LabOrderItem.objects.create(
            order=order,
            test=test,
            price=base_price,
            gst_amount=line_gst,
        )
        subtotal += base_price
        total_gst += line_gst
        if test.sample_type and test.sample_type not in sample_types:
            sample_types.append(test.sample_type)

    order.subtotal_amount = _quantize_money(subtotal)
    order.gst_amount = _quantize_money(total_gst)
    order.total_amount = _quantize_money(subtotal + total_gst)
    order.save(update_fields=["subtotal_amount", "gst_amount", "total_amount", "updated_at"])

    barcode = f"SMP-{uuid.uuid4().hex[:10].upper()}"
    LabSample.objects.create(
        tenant_id=tenant_id,
        branch_id=order.branch_id,
        order=order,
        barcode=barcode,
        sample_type=", ".join(sample_types) or "Blood",
    )

    record_audit_log(
        action="lab.order.created",
        resource_type="LabOrder",
        resource_id=order.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=order.branch_id,
        request=request,
        metadata={"order_number": order.order_number, "barcode": barcode, "test_count": len(tests)},
    )
    return order


#@transaction.atomic
#def mark_sample_collected(*, tenant_id, order_id, actor=None, request=None) -> LabSample:
#    order = LabOrder.objects.select_related("sample").filter(id=order_id, tenant_id=tenant_id).first()
#    if not order:
#        raise ValueError("Lab order not found in your organization.")
#    sample = order.sample
#    sample.collected_at = timezone.now()
#    sample.collected_by = actor
#    sample.save(update_fields=["collected_at", "collected_by", "updated_at"])

#    order.status = LabOrderStatus.SAMPLE_COLLECTED
#    order.save(update_fields=["status", "updated_at"])

#    record_audit_log(
#        action="lab.sample.collected",
#        resource_type="LabSample",
#        resource_id=sample.id,
#        actor=actor,
#        tenant_id=tenant_id,
#        branch_id=order.branch_id,
#        request=request,
#        metadata={"barcode": sample.barcode, "order_number": order.order_number},
#    )
#    return sample

@transaction.atomic
def mark_sample_collected(*, tenant_id, order_id, actor=None, request=None) -> LabSample:
    order = LabOrder.objects.select_related("sample").filter(id=order_id, tenant_id=tenant_id).first()
    if not order:
        raise ValueError("Lab order not found in your organization.")
    sample = getattr(order, "sample", None)
    if not sample:
        raise ValueError("No sample record found for this lab order.")

    sample.collected_at = timezone.now()
    sample.collected_by = actor
    sample.save(update_fields=["collected_at", "collected_by", "updated_at"])

    order.status = LabOrderStatus.SAMPLE_COLLECTED
    order.save(update_fields=["status", "updated_at"])

    record_audit_log(
        action="lab.sample.collected",
        resource_type="LabSample",
        resource_id=sample.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=order.branch_id,
        request=request,
        metadata={"barcode": sample.barcode, "order_number": order.order_number},
    )
    return sample


@transaction.atomic
def record_test_result(
    *,
    tenant_id,
    order_item_id,
    observed_value: str,
    is_abnormal: bool = False,
    remarks: str = "",
    actor=None,
    request=None,
) -> LabResult:
    item = (
        LabOrderItem.objects.select_related("order", "test")
        .filter(id=order_item_id, order__tenant_id=tenant_id)
        .first()
    )

    if not item:
        raise ValueError(
            "Lab order item not found in your organization."
        )

    # Prevent modifications after order verification or delivery.
    if item.order.status in {
        LabOrderStatus.VERIFIED,
        LabOrderStatus.DELIVERED,
    }:
        raise ValueError(
            "Cannot modify results after a lab order is verified or delivered."
        )

    # Prevent modifications to an already verified result.
    existing_result = getattr(item, "result", None)

    if existing_result and getattr(existing_result, "is_verified", False):
        raise ValueError(
            "Cannot modify an already verified lab result."
        )

    if not observed_value or not observed_value.strip():
        raise ValueError("Observed result value is required.")

    result, _ = LabResult.objects.update_or_create(
        order_item=item,
        defaults={
            "tenant_id": tenant_id,
            "branch_id": item.order.branch_id,
            "observed_value": observed_value.strip(),
            "unit": item.test.unit,
            "reference_range": item.test.reference_range,
            "is_abnormal": is_abnormal,
            "remarks": remarks.strip(),
            "entered_by": actor,
            "entered_at": timezone.now(),
            "is_verified": False,
            "verified_by": None,
            "verified_at": None,
        },
    )

    if item.order.status in {
        LabOrderStatus.ORDERED,
        LabOrderStatus.SAMPLE_COLLECTED,
    }:
        item.order.status = LabOrderStatus.IN_PROGRESS
        item.order.save(
            update_fields=["status", "updated_at"]
        )

    record_audit_log(
        action="lab.result.entered",
        resource_type="LabResult",
        resource_id=result.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=item.order.branch_id,
        request=request,
        metadata={
            "test_code": item.test.code,
            "is_abnormal": is_abnormal,
        },
    )

    return result

@transaction.atomic
def verify_lab_order(*, tenant_id, order_id, actor=None, request=None) -> LabOrder:
    if actor is not None and getattr(actor, "role", None) not in VERIFIER_ROLES:
        raise PermissionError("Only Lab Manager, Pathologist/Doctor, or Hospital Admin can verify lab reports.")

    order = (
        LabOrder.objects.prefetch_related("items__result")
        .filter(id=order_id, tenant_id=tenant_id)
        .first()
    )
    if not order:
        raise ValueError("Lab order not found in your organization.")

    items = list(order.items.all())
    if not items:
        raise ValueError("Lab order has no test items.")

    now = timezone.now()
    for item in items:
        result = getattr(item, "result", None)
        if not result:
            raise ValueError(f"Cannot verify order: missing result for {item.test.name}.")
        result.is_verified = True
        result.verified_by = actor
        result.verified_at = now
        result.save(update_fields=["is_verified", "verified_by", "verified_at", "updated_at"])

    order.status = LabOrderStatus.VERIFIED
    order.save(update_fields=["status", "updated_at"])

    record_audit_log(
        action="lab.order.verified",
        resource_type="LabOrder",
        resource_id=order.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=order.branch_id,
        request=request,
        metadata={"order_number": order.order_number},
    )
    return order


@transaction.atomic
def deliver_lab_report(*, tenant_id, order_id, actor=None, request=None) -> LabOrder:
    order = LabOrder.objects.filter(id=order_id, tenant_id=tenant_id).first()
    if not order:
        raise ValueError("Lab order not found in your organization.")
    if order.status != LabOrderStatus.VERIFIED:
        raise ValueError("Report must be verified before delivery to patient.")

    order.status = LabOrderStatus.DELIVERED
    order.delivered_at = timezone.now()
    order.save(update_fields=["status", "delivered_at", "updated_at"])

    record_audit_log(
        action="lab.report.delivered",
        resource_type="LabOrder",
        resource_id=order.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=order.branch_id,
        request=request,
        metadata={"order_number": order.order_number},
    )
    return order


def export_lab_orders_csv(orders_qs: QuerySet) -> str:
    headers = ["order_number", "patient_uhid", "patient_name", "status", "total_amount", "created_at"]
    rows: List[Dict[str, Any]] = []
    for o in orders_qs:
        rows.append({
            "order_number": o.order_number,
            "patient_uhid": o.patient.uhid,
            "patient_name": o.patient.full_name,
            "status": o.status,
            "total_amount": str(o.total_amount),
            "created_at": o.created_at.isoformat(),
        })
    return export_rows_to_csv(headers, rows)