from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid
from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone
from clinic.models import Patient
from core.audit import record_audit_log
from core.import_export import export_rows_to_csv
from .models import (
    ExpenseEntry,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    PaymentMethod,
    PaymentTransaction,
)
from core.scoping import (
    resolve_scoped_branch_id,
    validate_patient_branch_alignment,
)
from collections import defaultdict


def _q(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



def _quantize_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _generate_invoice_number() -> str:
    for _ in range(10):
        candidate = (
            f"INV-{timezone.localdate().strftime('%Y%m%d')}-"
            f"{uuid.uuid4().hex[:6].upper()}"
        )
        if not Invoice.objects.filter(invoice_number=candidate).exists():
            return candidate

    raise RuntimeError("Unable to generate a unique invoice number.")

@transaction.atomic
def create_invoice_with_items(
    *,
    tenant_id,
    items: List[Dict[str, Any]],
    patient: Optional[Patient] = None,
    customer_name: str = "",
    discount_amount: Decimal = Decimal("0.00"),
    branch_id=None,
    notes: str = "",
    actor=None,
    request=None,
) -> Invoice:
    if not items:
        raise ValueError("At least one invoice line item is required.")

    # Validate patient tenant ownership before using patient data.
    if patient is not None:
        if str(patient.tenant_id) != str(tenant_id):
            raise ValueError(
                "Patient does not belong to your organization."
            )

    # Resolve branch within the current tenant.
    scoped_branch_id = resolve_scoped_branch_id(
        tenant_id=tenant_id,
        requested_branch_id=branch_id,
        fallback_branch_id=(
            getattr(patient, "branch_id", None)
            if patient is not None
            else None
        ),
    )

    # Validate patient and invoice branch alignment.
    if patient is not None:
        validate_patient_branch_alignment(
            tenant_id=tenant_id,
            patient=patient,
            branch_id=scoped_branch_id,
        )

    clean_discount = _quantize_money(discount_amount)

    if clean_discount < Decimal("0.00"):
        raise ValueError("Discount amount cannot be negative.")

    resolved_customer = (
        (customer_name or "").strip()
        or (
            patient.full_name
            if patient
            else "Walk-in Patient"
        )
    )

    inv_no = _generate_invoice_number()

    invoice = Invoice.objects.create(
        tenant_id=tenant_id,
        branch_id=scoped_branch_id,
        invoice_number=inv_no,
        patient=patient,
        customer_name=resolved_customer,
        status=InvoiceStatus.ISSUED,
        discount_amount=clean_discount,
        notes=notes.strip(),
    )

    subtotal = Decimal("0.00")
    total_gst = Decimal("0.00")

    for raw in items:
        desc = (raw.get("description") or "").strip()
        qty = int(raw.get("quantity") or 0)

        unit_price = _quantize_money(
            Decimal(str(raw.get("unit_price") or "0.00"))
        )

        gst_rate = Decimal(
            str(raw.get("gst_rate_percent") or "0.00")
        )

        if (
            not desc
            or qty <= 0
            or unit_price < Decimal("0.00")
            or gst_rate < Decimal("0.00")
        ):
            raise ValueError(
                "Each line item requires a description, positive quantity, "
                "and non-negative unit price and GST rate."
            )

        line_base = _quantize_money(
            unit_price * Decimal(qty)
        )

        line_gst = _quantize_money(
            (line_base * gst_rate) / Decimal("100")
        )

        line_total = _quantize_money(
            line_base + line_gst
        )

        
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description=desc,
            category=(
                raw.get("category") or "GENERAL"
            ).strip().upper(),
            hsn_sac_code=(raw.get("hsn_sac_code") or "").strip(),
            quantity=qty,
            unit_price=unit_price,
            gst_rate_percent=gst_rate,
            line_total=line_total,
        )


        subtotal += line_base
        total_gst += line_gst

    gross = _quantize_money(subtotal + total_gst)

    if clean_discount > gross:
        raise ValueError(
            "Discount cannot exceed gross invoice amount."
        )

    invoice.subtotal_amount = _quantize_money(subtotal)
    invoice.gst_amount = _quantize_money(total_gst)
    invoice.total_amount = _quantize_money(
        gross - clean_discount
    )

    invoice.save(
        update_fields=[
            "subtotal_amount",
            "gst_amount",
            "total_amount",
            "updated_at",
        ]
    )

    record_audit_log(
        action="billing.invoice.created",
        resource_type="Invoice",
        resource_id=invoice.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=invoice.branch_id,
        request=request,
        metadata={
            "invoice_number": invoice.invoice_number,
            "total_amount": str(invoice.total_amount),
        },
    )

    return invoice



@transaction.atomic
def record_invoice_payment(
    *,
    tenant_id,
    invoice_id,
    amount: Decimal,
    method: str = PaymentMethod.UPI,
    reference_no: str = "",
    actor=None,
    request=None,
) -> PaymentTransaction:
    pay_amount = _quantize_money(amount)
    if pay_amount <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")

    invoice = Invoice.objects.select_for_update().filter(id=invoice_id, tenant_id=tenant_id).first()
    if not invoice:
        raise ValueError("Invoice not found in your organization.")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ValueError("Cannot record payment on a cancelled invoice.")

    remaining_due = _quantize_money(invoice.total_amount - invoice.paid_amount)
    if pay_amount > remaining_due:
        raise ValueError(f"Payment amount (₹{pay_amount}) exceeds remaining balance due (₹{remaining_due}).")

    txn = PaymentTransaction.objects.create(
        tenant_id=tenant_id,
        branch_id=invoice.branch_id,
        invoice=invoice,
        method=method if method in PaymentMethod.values else PaymentMethod.UPI,
        amount=pay_amount,
        reference_no=reference_no.strip(),
        received_by=actor,
    )

    invoice.paid_amount = _quantize_money(invoice.paid_amount + pay_amount)
    if invoice.paid_amount >= invoice.total_amount:
        invoice.status = InvoiceStatus.PAID
    elif invoice.paid_amount > Decimal("0.00"):
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    invoice.save(update_fields=["paid_amount", "status", "updated_at"])

    record_audit_log(
        action="billing.payment.recorded",
        resource_type="PaymentTransaction",
        resource_id=txn.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=invoice.branch_id,
        request=request,
        metadata={"invoice_number": invoice.invoice_number, "amount": str(pay_amount), "method": txn.method},
    )
    return txn


@transaction.atomic
def record_expense(
    *,
    tenant_id,
    title: str,
    amount: Decimal,
    category: str = "OPERATIONAL",
    expense_date: Optional[date] = None,
    gst_amount: Decimal = Decimal("0.00"),
    vendor_name: str = "",
    notes: str = "",
    branch_id=None,
    actor=None,
    request=None,
) -> ExpenseEntry:
    clean_amount = _quantize_money(amount)
    if not title or not title.strip():
        raise ValueError("Expense title is required.")
    if clean_amount <= Decimal("0.00"):
        raise ValueError("Expense amount must be greater than zero.")

    scoped_branch_id = resolve_scoped_branch_id(
    tenant_id=tenant_id,
    requested_branch_id=branch_id,
    )

    entry = ExpenseEntry.objects.create(
        tenant_id=tenant_id,
        branch_id=scoped_branch_id,
        title=title.strip(),
        category=(category or "OPERATIONAL").strip().upper(),
        expense_date=expense_date or timezone.localdate(),
        amount=clean_amount,
        gst_amount=_quantize_money(gst_amount),
        vendor_name=vendor_name.strip(),
        notes=notes.strip(),
        recorded_by=actor,
    )
    record_audit_log(
        action="billing.expense.recorded",
        resource_type="ExpenseEntry",
        resource_id=entry.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=branch_id,
        request=request,
        metadata={"title": entry.title, "amount": str(entry.amount)},
    )
    return entry


def summarize_finance(*, tenant_id, branch_id=None) -> Dict[str, Decimal]:
    inv_qs = Invoice.objects.filter(tenant_id=tenant_id).exclude(status=InvoiceStatus.CANCELLED)
    exp_qs = ExpenseEntry.objects.filter(tenant_id=tenant_id)
    if branch_id:
        inv_qs = inv_qs.filter(branch_id=branch_id)
        exp_qs = exp_qs.filter(branch_id=branch_id)

    invoiced = inv_qs.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    collected = inv_qs.aggregate(s=Sum("paid_amount"))["s"] or Decimal("0.00")
    expenses = exp_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

    invoiced_q = _quantize_money(invoiced)
    collected_q = _quantize_money(collected)
    expenses_q = _quantize_money(expenses)
    receivables_q = _quantize_money(max(Decimal("0.00"), invoiced_q - collected_q))
    net_cashflow_q = _quantize_money(collected_q - expenses_q)

    return {
        "total_invoiced": invoiced_q,
        "total_collected": collected_q,
        "pending_receivables": receivables_q,
        "total_expenses": expenses_q,
        "net_cashflow": net_cashflow_q,
    }


def export_invoices_csv(invoices_qs: QuerySet) -> str:
    headers = [
        "invoice_number",
        "customer_name",
        "status",
        "subtotal_amount",
        "gst_amount",
        "discount_amount",
        "total_amount",
        "paid_amount",
        "balance_due",
        "created_at",
    ]
    rows: List[Dict[str, Any]] = []
    for inv in invoices_qs:
        rows.append({
            "invoice_number": inv.invoice_number,
            "customer_name": inv.customer_name,
            "status": inv.status,
            "subtotal_amount": str(inv.subtotal_amount),
            "gst_amount": str(inv.gst_amount),
            "discount_amount": str(inv.discount_amount),
            "total_amount": str(inv.total_amount),
            "paid_amount": str(inv.paid_amount),
            "balance_due": str(inv.balance_due),
            "created_at": inv.created_at.isoformat(),
        })
    return export_rows_to_csv(headers, rows)

def build_gst_return_summary(*, tenant_id, branch_id=None) -> dict:
    """
    Produces a GSTR-1 / GSTR-3B style tax summary grouped by tax rate (GSTR-3B)
    and HSN/SAC code (GSTR-1 HSN summary) for invoices in a tenant (and optional branch).
    """
    qs = Invoice.objects.prefetch_related("items").filter(tenant_id=tenant_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    rate_buckets = defaultdict(
        lambda: {
            "taxable_value": Decimal("0.00"),
            "cgst": Decimal("0.00"),
            "sgst": Decimal("0.00"),
            "total_tax": Decimal("0.00"),
            "invoice_count": 0,
        }
    )
    hsn_buckets = defaultdict(
        lambda: {
            "hsn_sac_code": "UNSPECIFIED",
            "quantity": Decimal("0.00"),
            "taxable_value": Decimal("0.00"),
            "cgst": Decimal("0.00"),
            "sgst": Decimal("0.00"),
            "total_value": Decimal("0.00"),
        }
    )

    for inv in qs:
        seen_rates_for_invoice = set()
        for item in inv.items.all():
            qty = Decimal(str(getattr(item, "quantity", 1) or 1))
            unit_price = Decimal(str(getattr(item, "unit_price", Decimal("0.00")) or Decimal("0.00")))
            #taxable = _q(qty * unit_price)
            #rate = _q(Decimal(str(getattr(item, "gst_rate_percent", Decimal("0.00")) or Decimal("0.00"))))
            taxable = _quantize_money(qty * unit_price)
            rate = _quantize_money(Decimal(str(
                getattr(item, "gst_rate_percent", Decimal("0.00"))
                or Decimal("0.00")
            )))
            tax_amt = _quantize_money((taxable * rate) / Decimal("100"))
            cgst = _quantize_money(tax_amt / Decimal("2"))
            sgst = _quantize_money(tax_amt - cgst)
            hsn = (getattr(item, "hsn_sac_code", "") or "").strip() or "UNSPECIFIED"

            r_bucket = rate_buckets[str(rate)]
            r_bucket["taxable_value"] = _quantize_money(r_bucket["taxable_value"] + taxable)
            r_bucket["cgst"] = _quantize_money(r_bucket["cgst"] + cgst)
            r_bucket["sgst"] = _quantize_money(r_bucket["sgst"] + sgst)
            r_bucket["total_tax"] = _quantize_money(r_bucket["total_tax"] + tax_amt)
            if str(rate) not in seen_rates_for_invoice:
                r_bucket["invoice_count"] += 1
                seen_rates_for_invoice.add(str(rate))

            h_bucket = hsn_buckets[hsn]
            h_bucket["hsn_sac_code"] = hsn
            h_bucket["quantity"] = _quantize_money(h_bucket["quantity"] + qty)
            h_bucket["taxable_value"] = _quantize_money(h_bucket["taxable_value"] + taxable)
            h_bucket["cgst"] = _quantize_money(h_bucket["cgst"] + cgst)
            h_bucket["sgst"] = _quantize_money(h_bucket["sgst"] + sgst)
            h_bucket["total_value"] = _quantize_money(h_bucket["total_value"] + taxable + tax_amt)

    return {
        "gstr_3b_by_rate": [
            {"gst_rate_percent": k, **v} for k, v in sorted(rate_buckets.items())
        ],
        "gstr_1_hsn_summary": [v for _, v in sorted(hsn_buckets.items())],
    }