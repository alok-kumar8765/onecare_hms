import io
import os
from pathlib import Path


def _get_drive_service():
    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not creds_path or not Path(creds_path).is_file():
        raise RuntimeError("Google Drive service account JSON is not configured.")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive.file"]
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
    return build("drive", "v3", credentials=creds)


def upload_backup_to_google_drive(file_path: Path, folder_id: str = "") -> str:
    target_folder = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    service = _get_drive_service()

    from googleapiclient.http import MediaFileUpload

    metadata = {"name": file_path.name}
    if target_folder:
        metadata["parents"] = [target_folder]

    media = MediaFileUpload(str(file_path), resumable=True)
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"]


def download_backup_from_google_drive(file_id: str, dest_path: Path) -> Path:
    clean_id = (file_id or "").strip()
    if not clean_id:
        raise ValueError("Google Drive file ID is required.")

    service = _get_drive_service()

    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=clean_id)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    dest_path.write_bytes(buf.getvalue())
    return dest_path