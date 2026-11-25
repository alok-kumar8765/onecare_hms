import shutil
import tempfile
from pathlib import Path
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.views.decorators.http import require_GET, require_POST
from .audit import record_audit_log
from .drive_backup import download_backup_from_google_drive, upload_backup_to_google_drive

ALLOWED_BACKUP_ROLES = {"ADMIN", "HR", "DOCTOR"}

def pop_backup_message(request) -> str:
    if not getattr(request, "session", None):
        return ""

    return request.session.pop("backup_message", "") or ""

def _can_manage_backups(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = str(getattr(user, "role", "") or "").upper()
    return role in ALLOWED_BACKUP_ROLES


def _backup_dir() -> Path:
    return Path(settings.BASE_DIR) / "backups"


def _latest_backup_file(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        p for p in out_dir.iterdir()
        if p.is_file() and not p.name.endswith(".sha256")
    ]
    if not candidates:
        call_command("backup_hms", mode="backup", output_dir=str(out_dir))
        candidates = [
            p for p in out_dir.iterdir()
            if p.is_file() and not p.name.endswith(".sha256")
        ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _validate_sqlite_header_if_needed(path: Path) -> None:
    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if "sqlite" in engine:
        header = path.read_bytes()[:16]
        if header != b"SQLite format 3\x00":
            raise ValueError("Uploaded or downloaded file is not a valid SQLite database.")


@login_required
@require_GET
def backup_download_view(request):
    if not _can_manage_backups(request.user):
        return HttpResponseForbidden("Access denied for backup operations.")

    out_dir = _backup_dir()
    call_command("backup_hms", mode="backup", output_dir=str(out_dir))
    artifact = _latest_backup_file(out_dir)

    record_audit_log(
        action="backup.download_local",
        resource_type="DatabaseBackup",
        resource_id=artifact.name,
        actor=request.user,
        tenant_id=getattr(request.user, "tenant_id", None),
        branch_id=getattr(request.user, "primary_branch_id", None),
        request=request,
    )
    return FileResponse(open(artifact, "rb"), as_attachment=True, filename=artifact.name)


@login_required
@require_POST
def backup_drive_upload_view(request):
    if not _can_manage_backups(request.user):
        return HttpResponseForbidden("Access denied for backup operations.")

    out_dir = _backup_dir()
    call_command("backup_hms", mode="backup", output_dir=str(out_dir))
    artifact = _latest_backup_file(out_dir)

    try:
        drive_file_id = upload_backup_to_google_drive(artifact)
        record_audit_log(
            action="backup.upload_drive",
            resource_type="DatabaseBackup",
            resource_id=drive_file_id,
            actor=request.user,
            tenant_id=getattr(request.user, "tenant_id", None),
            branch_id=getattr(request.user, "primary_branch_id", None),
            request=request,
            metadata={"file_name": artifact.name, "drive_file_id": drive_file_id},
        )
    except Exception as exc:
        request.session["backup_message"] = f"Google Drive upload failed: {exc}"
        return redirect(request.META.get("HTTP_REFERER") or "/")

    request.session["backup_message"] = f"Uploaded {artifact.name} to Google Drive (ID: {drive_file_id})."
    return redirect(request.META.get("HTTP_REFERER") or "/")


@login_required
@require_POST
def backup_restore_view(request):
    if not _can_manage_backups(request.user):
        return HttpResponseForbidden("Access denied for backup operations.")

    if request.POST.get("confirm_restore") != "1":
        request.session["backup_message"] = "Please confirm restore before proceeding."
        return redirect(request.META.get("HTTP_REFERER") or "/")

    uploaded_file = request.FILES.get("backup_file")
    drive_file_id = (request.POST.get("drive_file_id") or "").strip()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            staged_path = Path(tmpdir) / (uploaded_file.name if uploaded_file else f"drive_{drive_file_id}.sqlite3")
            if uploaded_file:
                with staged_path.open("wb") as dest:
                    for chunk in uploaded_file.chunks():
                        dest.write(chunk)
            elif drive_file_id:
                download_backup_from_google_drive(drive_file_id, staged_path)
            else:
                raise ValueError("Provide a local backup file or a Google Drive file ID.")

            _validate_sqlite_header_if_needed(staged_path)
            call_command("backup_hms", mode="restore", file=str(staged_path))

        record_audit_log(
            action="backup.restore",
            resource_type="DatabaseBackup",
            resource_id=drive_file_id or (uploaded_file.name if uploaded_file else "local"),
            actor=request.user,
            tenant_id=getattr(request.user, "tenant_id", None),
            branch_id=getattr(request.user, "primary_branch_id", None),
            request=request,
            metadata={"source": "drive" if drive_file_id else "local_upload"},
        )
        request.session["backup_message"] = "Database backup restored successfully."
    except Exception as exc:
        request.session["backup_message"] = f"Restore failed: {exc}"

    return redirect(request.META.get("HTTP_REFERER") or "/")