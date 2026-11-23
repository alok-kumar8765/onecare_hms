from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List
from django.db import transaction
from django.db.models import Sum
from billing.models import Invoice, InvoiceStatus
from billing.services import create_invoice_with_items
from clinic.models import Prescription
from core.audit import record_audit_log
from ipd.models import IPDAdmission
from laboratory.models import LabOrder
from pharmacy.models import Medicine, PharmacySale
from pharmacy.services import dispense_fefo_sale
from core.allergy_checks import find_allergy_conflicts

def _q(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)




@transaction.atomic
def dispense_prescription_to_pharmacy_sale(
    *,
    tenant_id,
    prescription_id,
    default_quantity: int = 1,
    branch_id=None,
    actor=None,
    request=None,
    override_allergy_warning: bool = False,
) -> PharmacySale:
    """
    Converts an OPD prescription into a FEFO pharmacy sale.
    Checks patient allergies before dispensing.
    """

    prescription = (
        Prescription.objects.select_related("encounter__patient")
        .prefetch_related("items")
        .filter(
            id=prescription_id,
            encounter__tenant_id=tenant_id,
        )
        .first()
    )

    if not prescription:
        raise ValueError("Prescription not found in your organization.")

    line_requests = []
    medicine_objects = []

    for item in prescription.items.all():
        med = Medicine.objects.filter(
            tenant_id=tenant_id,
            brand_name__iexact=item.medicine_name.strip(),
            is_active=True,
        ).first()

        if not med:
            raise ValueError(
                f"Prescribed medicine '{item.medicine_name}' "
                "is not in pharmacy catalog."
            )

        qty = getattr(item, "quantity", None) or default_quantity

        if int(qty) <= 0:
            raise ValueError("Dispense quantity must be greater than zero.")

        line_requests.append({
            "medicine_id": str(med.id),
            "quantity": int(qty),
        })

        medicine_objects.append(med)

    if not line_requests:
        raise ValueError("Prescription has no medicine items to dispense.")

    patient = prescription.encounter.patient

    # -----------------------------------------
    # PATIENT ALLERGY CHECK
    # -----------------------------------------

    conflicts = find_allergy_conflicts(
        raw_allergies=getattr(patient, "allergies_notes", ""),
        medicine_names=[
            med.brand_name for med in medicine_objects
        ],
        salt_compositions=[
            getattr(med, "salt_composition", "") or ""
            for med in medicine_objects
        ],
    )

    if conflicts and not override_allergy_warning:
        record_audit_log(
            action="workflow.pharmacy_allergy_blocked",
            resource_type="Prescription",
            resource_id=prescription.id,
            actor=actor,
            tenant_id=tenant_id,
            branch_id=branch_id or prescription.encounter.branch_id,
            request=request,
            metadata={
                "conflicts": conflicts,
            },
        )

        raise ValueError(
            "Allergy warning: " + "; ".join(conflicts)
        )

    # -----------------------------------------
    # DISPENSE PHARMACY SALE
    # -----------------------------------------

    sale = dispense_fefo_sale(
        tenant_id=tenant_id,
        branch_id=branch_id or prescription.encounter.branch_id,
        customer_name=patient.full_name,
        items_requested=line_requests,
        actor=actor,
        request=request,
    )

    record_audit_log(
        action="workflow.prescription_to_pharmacy_sale",
        resource_type="PharmacySale",
        resource_id=sale.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=sale.branch_id,
        request=request,
        metadata={
            "prescription_id": str(prescription.id),
            "invoice_number": sale.invoice_number,
            "allergy_override": bool(conflicts and override_allergy_warning),
            "allergy_conflicts": conflicts,
        },
    )

    return sale




@transaction.atomic
def create_invoice_from_lab_order(
    *,
    tenant_id,
    lab_order_id,
    discount_amount: Decimal = Decimal("0.00"),
    actor=None,
    request=None,
) -> Invoice:
    order = (
        LabOrder.objects.select_related("patient")
        .prefetch_related("items__test")
        .filter(id=lab_order_id, tenant_id=tenant_id)
        .first()
    )
    if not order:
        raise ValueError("Lab order not found in your organization.")

    items_payload = []
    for item in order.items.all():
        items_payload.append({
            "description": f"Lab Test: {item.test.code} - {item.test.name}",
            "category": "LABORATORY",
            "quantity": 1,
            "unit_price": item.price,
            "gst_rate_percent": item.test.gst_rate_percent,
        })

    inv = create_invoice_with_items(
        tenant_id=tenant_id,
        patient=order.patient,
        customer_name=order.patient.full_name,
        discount_amount=discount_amount,
        branch_id=order.branch_id,
        items=items_payload,
        notes=f"Generated from Lab Order {order.order_number}",
        actor=actor,
        request=request,
    )
    record_audit_log(
        action="workflow.lab_order_to_invoice",
        resource_type="Invoice",
        resource_id=inv.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=inv.branch_id,
        request=request,
        metadata={"lab_order_number": order.order_number, "invoice_number": inv.invoice_number},
    )
    return inv


@transaction.atomic
def create_invoice_from_ipd_admission(
    *,
    tenant_id,
    admission_id,
    discount_amount: Decimal = Decimal("0.00"),
    actor=None,
    request=None,
) -> Invoice:
    admission = (
        IPDAdmission.objects.select_related("patient", "ward", "bed")
        .filter(id=admission_id, tenant_id=tenant_id)
        .first()
    )
    if not admission:
        raise ValueError("IPD admission not found in your organization.")
    if admission.total_amount <= Decimal("0.00"):
        raise ValueError("IPD admission has no settled charges yet. Discharge or add charges first.")

    items_payload = [
        {
            "description": f"IPD Stay & Care ({admission.admission_number} - {admission.ward.name}/{admission.bed.bed_number})",
            "category": "IPD",
            "quantity": 1,
            "unit_price": admission.subtotal_amount,
            "gst_rate_percent": Decimal("0.00"),
        }
    ]
    if admission.gst_amount > Decimal("0.00"):
        items_payload.append({
            "description": f"IPD Applicable GST ({admission.admission_number})",
            "category": "IPD_TAX",
            "quantity": 1,
            "unit_price": admission.gst_amount,
            "gst_rate_percent": Decimal("0.00"),
        })

    inv = create_invoice_with_items(
        tenant_id=tenant_id,
        patient=admission.patient,
        customer_name=admission.patient.full_name,
        discount_amount=discount_amount,
        branch_id=admission.branch_id,
        items=items_payload,
        notes=f"Generated from IPD Admission {admission.admission_number}",
        actor=actor,
        request=request,
    )
    record_audit_log(
        action="workflow.ipd_to_invoice",
        resource_type="Invoice",
        resource_id=inv.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=inv.branch_id,
        request=request,
        metadata={"admission_number": admission.admission_number, "invoice_number": inv.invoice_number},
    )
    return inv


def summarize_gst_breakup(*, tenant_id, branch_id=None) -> Dict[str, Decimal]:
    """
    Aggregates Indian GST (CGST + SGST 50/50 split) across Billing Invoices
    and Pharmacy Sales for periodic tax filing.
    """
    inv_qs = Invoice.objects.filter(tenant_id=tenant_id).exclude(status=InvoiceStatus.CANCELLED)
    sale_qs = PharmacySale.objects.filter(tenant_id=tenant_id)
    if branch_id:
        inv_qs = inv_qs.filter(branch_id=branch_id)
        sale_qs = sale_qs.filter(branch_id=branch_id)

    inv_taxable = inv_qs.aggregate(s=Sum("subtotal_amount"))["s"] or Decimal("0.00")
    inv_gst = inv_qs.aggregate(s=Sum("gst_amount"))["s"] or Decimal("0.00")

    sale_taxable = sale_qs.aggregate(s=Sum("subtotal_amount"))["s"] or Decimal("0.00")
    sale_gst = sale_qs.aggregate(s=Sum("gst_amount"))["s"] or Decimal("0.00")

    total_taxable = _q(inv_taxable + sale_taxable)
    total_gst = _q(inv_gst + sale_gst)
    cgst = _q(total_gst / Decimal("2"))
    sgst = _q(total_gst - cgst)

    return {
        "total_taxable_value": total_taxable,
        "total_gst": total_gst,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "gross_with_gst": _q(total_taxable + total_gst),
    }