from decimal import Decimal
from django.db import models
from django.utils import timezone
from core.models import BranchScopedModel, TenantScopedModel, TimeStampedModel


class StockMovementType(models.TextChoices):
    PURCHASE = "PURCHASE", "Purchase In"
    SALE = "SALE", "POS Dispense Out"
    RETURN_IN = "RETURN_IN", "Sales Return In"
    ADJUSTMENT = "ADJUSTMENT", "Stock Adjustment"


class Medicine(TenantScopedModel):
    brand_name = models.CharField(max_length=160, db_index=True)
    generic_name = models.CharField(max_length=160, blank=True, db_index=True)
    salt_composition = models.CharField(max_length=255, blank=True, db_index=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("12.00"))
    reorder_level = models.PositiveIntegerField(default=10)
    is_controlled_drug = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["brand_name"]

    def __str__(self) -> str:
        return f"{self.brand_name} ({self.salt_composition or self.generic_name})"


class Supplier(TenantScopedModel):
    name = models.CharField(max_length=180, db_index=True)
    gstin = models.CharField(max_length=20, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MedicineBatch(BranchScopedModel):
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name="batches")
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
    )
    batch_number = models.CharField(max_length=60, db_index=True)
    expiry_date = models.DateField(db_index=True)
    quantity_on_hand = models.PositiveIntegerField(default=0)
    purchase_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    mrp = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["expiry_date", "created_at"]

    @property
    def is_expired(self) -> bool:
        return self.expiry_date <= timezone.localdate()

    def __str__(self) -> str:
        return f"{self.medicine.brand_name} [Batch {self.batch_number}, Exp {self.expiry_date}]"


class PharmacySale(BranchScopedModel):
    invoice_number = models.CharField(max_length=60, unique=True)
    customer_name = models.CharField(max_length=180, blank=True)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["-created_at"]


class PharmacySaleItem(TimeStampedModel):
    sale = models.ForeignKey(PharmacySale, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="sale_items")
    batch = models.ForeignKey(MedicineBatch, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2)


class StockMovement(BranchScopedModel):
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name="stock_movements")
    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=24, choices=StockMovementType.choices, db_index=True)
    quantity_delta = models.IntegerField()
    reference_id = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]