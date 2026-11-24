from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from accounts.models import User, UserRole
from clinic.models import OPDEncounter, Prescription, PrescriptionItem
from clinic.services import register_patient
from core.allergy_checks import find_allergy_conflicts
from core.linked_workflows import dispense_prescription_to_pharmacy_sale
from ipd.models import AdmissionStatus, Bed, BedStatus, IPDAdmission, Ward
from ipd.services import compute_ipd_running_ledger, transfer_ipd_bed
from pharmacy.models import Medicine, MedicineBatch
from tenants.models import DeploymentPreset
from tenants.services import provision_tenant


@pytest.mark.django_db
def test_backup_hms_creates_verifies_and_rotates_backups(tmp_path, settings):
    # Ensure a SQLite file exists in tmp_path so backup/verify/retention can run cleanly
    sqlite_file = tmp_path / "test_hms.sqlite3"
    sqlite_file.write_bytes(b"SQLite format 3\x00sample-db-bytes")
    settings.DATABASES["default"] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": str(sqlite_file),
    "ATOMIC_REQUESTS": False,
    }

    backup_dir = tmp_path / "backups"
    out = StringIO()
    call_command(
        "backup_hms",
        mode="backup",
        output_dir=str(backup_dir),
        retention_days=14,
        stdout=out,
    )

    artifacts = list(backup_dir.glob("onecare_sqlite_*.sqlite3"))
    assert len(artifacts) == 1
    artifact = artifacts[0]
    sha_file = Path(f"{artifact}.sha256")
    assert sha_file.is_file()

    # Verification succeeds on untampered backup
    call_command("backup_hms", mode="verify", file=str(artifact), stdout=StringIO())

    # Tampering with backup file causes verify to fail
    artifact.write_bytes(b"corrupted-content")
    with pytest.raises(CommandError):
        call_command("backup_hms", mode="verify", file=str(artifact))

    # Old file beyond retention_days is rotated out during backup
    stale_file = backup_dir / "onecare_sqlite_20000101T000000Z.sqlite3"
    stale_file.write_bytes(b"old-backup")
    old_ts = (timezone.now() - timedelta(days=30)).timestamp()
    import os
    os.utime(stale_file, (old_ts, old_ts))

    call_command(
        "backup_hms",
        mode="backup",
        output_dir=str(backup_dir),
        retention_days=14,
        stdout=StringIO(),
    )
    assert not stale_file.exists()


@pytest.mark.django_db
def test_patient_allergy_blocks_dispensing_unless_overridden():
    tenant = provision_tenant(name="Allergy Care Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    doctor = User.objects.create_user(
        username="dr_allergy",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.DOCTOR,
    )
    patient, _ = register_patient(
        tenant_id=tenant.id,
        full_name="Rohan Verma",
        phone_number="+919833333333",
        allergies_notes="Amoxicillin, Sulfa",
    )

    conflicts = find_allergy_conflicts(
        raw_allergies=patient.allergies,
        medicine_names=["Moxikind-CV"],
        salt_compositions=["Amoxicillin + Clavulanic Acid"],
    )
    assert len(conflicts) >= 1

    med = Medicine.objects.create(
        tenant_id=tenant.id,
        brand_name="Moxikind-CV",
        salt_composition="Amoxicillin + Clavulanic Acid",
        #unit_price=Decimal("50.00"),
    )
    MedicineBatch.objects.create(
        tenant_id=tenant.id,
        medicine=med,
        batch_number="BATCH-01",
        expiry_date=timezone.now().date() + timedelta(days=180),
        quantity_on_hand=20,
        mrp=Decimal("30.00"),
    )

    encounter = OPDEncounter.objects.create(
        tenant_id=tenant.id,
        patient=patient,
        doctor=doctor,
        chief_complaint="Fever and throat pain",
    )
    rx = Prescription.objects.create(
        tenant_id=tenant.id,
        encounter=encounter,
        patient=patient,
        prescribed_by=doctor,
        advice="Take after meals",
    )
    PrescriptionItem.objects.create(
    prescription=rx,
    medicine_name=med.brand_name,
    dosage="500 mg",
    frequency="Twice daily",
    duration="5 days",
    instructions="Take after meals",
    )

    # Blocked by default when allergy matches
    with pytest.raises(ValueError, match="Allergy warning"):
        dispense_prescription_to_pharmacy_sale(
            tenant_id=tenant.id,
            prescription_id=rx.id,
            actor=doctor,
            override_allergy_warning=False,
        )

    # Allowed when explicitly overridden
    sale = dispense_prescription_to_pharmacy_sale(
        tenant_id=tenant.id,
        prescription_id=rx.id,
        actor=doctor,
        override_allergy_warning=True,
    )
    assert sale is not None


@pytest.mark.django_db
def test_ipd_bed_transfer_and_running_ledger():
    tenant = provision_tenant(name="IPD Care Hospital", deployment_preset=DeploymentPreset.FULL_HOSPITAL)
    nurse = User.objects.create_user(
        username="nurse_ipd",
        password="StrongPassword123!",
        tenant_id=tenant.id,
        role=UserRole.NURSE,
    )
    patient, _ = register_patient(
        tenant_id=tenant.id,
        full_name="Meera Nair",
        phone_number="+919844444444",
    )

    ward_gen = Ward.objects.create(
    tenant_id=tenant.id,
    name="General Ward",
    code="GEN",
    daily_charge=Decimal("1500.00"),
    )

    ward_pvt = Ward.objects.create(
        tenant_id=tenant.id,
        name="Private Room",
        code="PVT",
        daily_charge=Decimal("3500.00"),
    )
    bed_1 = Bed.objects.create(
        tenant_id=tenant.id,
        ward=ward_gen,
        bed_number="G-101",
        status=BedStatus.OCCUPIED,
        
    )
    bed_2 = Bed.objects.create(
        tenant_id=tenant.id,
        ward=ward_pvt,
        bed_number="P-201",
        status=BedStatus.AVAILABLE,
    )

    admission = IPDAdmission.objects.create(
        tenant_id=tenant.id,
        patient=patient,
        ward=ward_gen,
        bed=bed_1,
        admission_number="IPD-1001",
        status=AdmissionStatus.ADMITTED,
        admitted_at=timezone.now() - timedelta(days=2),
    )

    transferred = transfer_ipd_bed(
        tenant_id=tenant.id,
        admission_id=admission.id,
        target_bed_id=bed_2.id,
        transfer_reason="Upgraded to private room",
        actor=nurse,
    )

    bed_1.refresh_from_db()
    bed_2.refresh_from_db()
    assert transferred.bed_id == bed_2.id
    assert transferred.ward_id == ward_pvt.id
    assert bed_1.status == BedStatus.AVAILABLE
    assert bed_2.status == BedStatus.OCCUPIED

    ledger = compute_ipd_running_ledger(tenant_id=tenant.id, admission_id=admission.id)
    assert ledger["billable_days"] >= 2
    assert ledger["running_total"] >= Decimal("7000.00")