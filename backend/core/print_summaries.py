from decimal import Decimal, ROUND_HALF_UP
from billing.models import Invoice
from clinic.models import Prescription
from laboratory.models import LabOrder


def _q(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



def build_invoice_print_payload(*, tenant_id, invoice_id) -> dict:
    inv = (
        Invoice.objects.select_related("patient")
        .prefetch_related("items", "payments")
        .filter(id=invoice_id, tenant_id=tenant_id)
        .first()
    )
    if not inv:
        raise ValueError("Invoice not found in your organization.")

    paid = sum(
        (_q(Decimal(str(p.amount))) for p in inv.payments.all()),
        Decimal("0.00")
    )
    total = _q(Decimal(str(inv.total_amount)))

    return {
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "patient_name": inv.patient.full_name if inv.patient else (inv.customer_name or "Walk-in"),
        "subtotal": _q(Decimal(str(inv.subtotal_amount))),
        "gst_amount": _q(Decimal(str(inv.gst_amount))),
        "total_amount": total,
        "paid_amount": paid,
        "balance_due": max(Decimal("0.00"), _q(total - paid)),
        "items": [
            {
                "description": it.description,
                "hsn_sac_code": getattr(it, "hsn_sac_code", ""),
                "quantity": it.quantity,
                "line_total": _q(Decimal(str(it.line_total))),
            }
            for it in inv.items.all()
        ],
    }


def build_verified_lab_report_payload(*, tenant_id, order_id) -> dict:
    order = (
        LabOrder.objects.select_related("patient")
        .prefetch_related("items__test")
        .filter(id=order_id, tenant_id=tenant_id)
        .first()
    )
    if not order:
        raise ValueError("Lab order not found in your organization.")
    if getattr(order, "status", "") not in ("VERIFIED", "COMPLETED", "DELIVERED"):
        raise ValueError("Lab report is not verified yet and cannot be printed or released.")

    return {
        "order_number": order.order_number,
        "status": order.status,
        "patient_name": order.patient.full_name if order.patient else "",
        "results": [
            {
                "test_name": getattr(item.test, "name", str(item)),
                "result_value": getattr(item, "result_value", ""),
                "unit": getattr(item.test, "unit", ""),
                "reference_range": getattr(item.test, "reference_range", ""),
            }
            for item in order.items.all()
        ],
    }


def build_prescription_print_payload(*, tenant_id, prescription_id) -> dict:
    rx = (
        Prescription.objects.select_related("encounter__patient", "patient", "prescribed_by")
        .prefetch_related("items")
        .filter(id=prescription_id, tenant_id=tenant_id)
        .first()
    )
    if not rx:
        raise ValueError("Prescription not found in your organization.")

    patient = rx.patient or (rx.encounter.patient if rx.encounter else None)
    return {
        "prescription_id": str(rx.id),
        "patient_name": patient.full_name if patient else "",
        "allergies": getattr(patient, "allergies", "") if patient else "",
        "doctor_name": getattr(rx.prescribed_by, "get_full_name", lambda: "")() or getattr(rx.prescribed_by, "username", ""),
        "advice": getattr(rx, "advice", ""),
        "items": [
            {
                "medicine_name": getattr(it, "medicine_name", ""),
                "dosage": getattr(it, "dosage", ""),
                "frequency": getattr(it, "frequency", ""),
                "duration": getattr(it, "duration", ""),
                "quantity": getattr(it, "quantity", 1),
            }
            for it in rx.items.all()
        ],
    }