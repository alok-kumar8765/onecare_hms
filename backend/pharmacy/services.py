from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from core.audit import record_audit_log
from core.import_export import export_rows_to_csv
from .models import (
    Medicine,
    MedicineBatch,
    PharmacySale,
    PharmacySaleItem,
    StockMovement,
    StockMovementType,
    Supplier,
)


def _quantize_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def search_medicines(*, tenant_id, query: str = "") -> QuerySet:
    qs = Medicine.objects.filter(tenant_id=tenant_id, is_active=True)
    q = (query or "").strip()
    if not q:
        return qs
    return qs.filter(
        Q(brand_name__icontains=q)
        | Q(generic_name__icontains=q)
        | Q(salt_composition__icontains=q)
    )


@transaction.atomic
def add_medicine_and_batch(
    *,
    tenant_id,
    brand_name: str,
    batch_number: str,
    expiry_date: date,
    quantity: int,
    unit_price: Decimal,
    purchase_rate: Optional[Decimal] = None,
    generic_name: str = "",
    salt_composition: str = "",
    gst_rate_percent: Decimal = Decimal("12.00"),
    is_controlled_drug: bool = False,
    supplier: Optional[Supplier] = None,
    branch_id=None,
    actor=None,
    request=None,
) -> tuple[Medicine, MedicineBatch]:
    if quantity <= 0:
        raise ValueError("Batch quantity must be greater than zero.")
    if expiry_date <= timezone.localdate():
        raise ValueError("Cannot add an already expired batch for dispensing.")

    med, _ = Medicine.objects.get_or_create(
        tenant_id=tenant_id,
        brand_name=brand_name.strip(),
        defaults={
            "generic_name": generic_name.strip(),
            "salt_composition": salt_composition.strip(),
            "gst_rate_percent": gst_rate_percent,
            "is_controlled_drug": is_controlled_drug,
        },
    )
    if salt_composition and not med.salt_composition:
        med.salt_composition = salt_composition.strip()
        med.save(update_fields=["salt_composition", "updated_at"])

    batch = MedicineBatch.objects.create(
        tenant_id=tenant_id,
        branch_id=branch_id,
        medicine=med,
        supplier=supplier,
        batch_number=batch_number.strip(),
        expiry_date=expiry_date,
        quantity_on_hand=quantity,
        purchase_rate=_quantize_money(purchase_rate if purchase_rate is not None else unit_price),
        mrp=_quantize_money(unit_price),
    )

    StockMovement.objects.create(
        tenant_id=tenant_id,
        branch_id=branch_id,
        medicine=med,
        batch=batch,
        movement_type=StockMovementType.PURCHASE,
        quantity_delta=quantity,
        reference_id=batch.batch_number,
        notes="Initial batch stock added",
    )
    record_audit_log(
        action="pharmacy.batch.added",
        resource_type="MedicineBatch",
        resource_id=batch.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=branch_id,
        request=request,
        metadata={"medicine": med.brand_name, "batch_number": batch.batch_number, "quantity": quantity},
    )
    return med, batch


@transaction.atomic
def dispense_fefo_sale(
    *,
    tenant_id,
    items_requested: List[Dict[str, Any]],
    customer_name: str = "",
    branch_id=None,
    actor=None,
    request=None,
) -> PharmacySale:
    """
    Atomically dispenses medicines using First-Expired, First-Out (FEFO) with
    row-level locking (`select_for_update`) on non-expired batches to prevent
    concurrent overselling. Rolls back completely if any line has insufficient stock.
    """
    if not items_requested:
        raise ValueError("At least one medicine item is required for a sale.")

    today = timezone.localdate()
    allocations: List[tuple[Medicine, MedicineBatch, int]] = []

    for req in items_requested:
        med_id = req.get("medicine_id")
        qty_needed = int(req.get("quantity") or 0)
        if not med_id or qty_needed <= 0:
            raise ValueError("Each item requires a valid medicine_id and positive quantity.")

        med = Medicine.objects.filter(id=med_id, tenant_id=tenant_id, is_active=True).first()
        if not med:
            raise ValueError("Medicine not found in current organization.")

        batches_qs = (
            MedicineBatch.objects.select_for_update()
            .filter(
                tenant_id=tenant_id,
                medicine=med,
                expiry_date__gt=today,
                quantity_on_hand__gt=0,
            )
            .order_by("expiry_date", "created_at")
        )
        if branch_id:
            batches_qs = batches_qs.filter(branch_id=branch_id)

        remaining = qty_needed
        for batch in batches_qs:
            if remaining <= 0:
                break
            take = min(batch.quantity_on_hand, remaining)
            batch.quantity_on_hand -= take
            batch.save(update_fields=["quantity_on_hand", "updated_at"])
            allocations.append((med, batch, take))
            remaining -= take

        if remaining > 0:
            raise ValueError(f"Insufficient valid non-expired stock for {med.brand_name}.")

    invoice_no = f"RX-{timezone.localdate().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    sale = PharmacySale.objects.create(
        tenant_id=tenant_id,
        branch_id=branch_id,
        invoice_number=invoice_no,
        customer_name=customer_name.strip(),
    )

    subtotal = Decimal("0.00")
    total_gst = Decimal("0.00")

    for med, batch, qty in allocations:
        unit_price = _quantize_money(batch.mrp)
        line_base = _quantize_money(unit_price * Decimal(qty))
        line_gst = _quantize_money((line_base * med.gst_rate_percent) / Decimal("100"))
        line_total = _quantize_money(line_base + line_gst)

        PharmacySaleItem.objects.create(
            sale=sale,
            medicine=med,
            batch=batch,
            quantity=qty,
            unit_price=unit_price,
            gst_amount=line_gst,
            line_total=line_total,
        )
        StockMovement.objects.create(
            tenant_id=tenant_id,
            branch_id=branch_id,
            medicine=med,
            batch=batch,
            movement_type=StockMovementType.SALE,
            quantity_delta=-qty,
            reference_id=sale.invoice_number,
            notes=f"FEFO dispense from batch {batch.batch_number}",
        )
        subtotal += line_base
        total_gst += line_gst

    sale.subtotal_amount = _quantize_money(subtotal)
    sale.gst_amount = _quantize_money(total_gst)
    sale.total_amount = _quantize_money(subtotal + total_gst)
    sale.save(update_fields=["subtotal_amount", "gst_amount", "total_amount", "updated_at"])

    record_audit_log(
        action="pharmacy.sale.dispensed",
        resource_type="PharmacySale",
        resource_id=sale.id,
        actor=actor,
        tenant_id=tenant_id,
        branch_id=branch_id,
        request=request,
        metadata={"invoice_number": sale.invoice_number, "total_amount": str(sale.total_amount)},
    )
    return sale


def export_pharmacy_sales_csv(sales_qs: QuerySet) -> str:
    headers = ["invoice_number", "customer_name", "subtotal_amount", "gst_amount", "total_amount", "created_at"]
    rows: List[Dict[str, Any]] = []
    for s in sales_qs:
        rows.append({
            "invoice_number": s.invoice_number,
            "customer_name": s.customer_name,
            "subtotal_amount": str(s.subtotal_amount),
            "gst_amount": str(s.gst_amount),
            "total_amount": str(s.total_amount),
            "created_at": s.created_at.isoformat(),
        })
    return export_rows_to_csv(headers, rows)