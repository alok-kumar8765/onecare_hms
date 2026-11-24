import os
from pathlib import Path


def upload_backup_to_google_drive(file_path: Path, folder_id: str = "") -> str:
    """
    Uploads a backup file to Google Drive when credentials are configured.
    Raises RuntimeError if Google Drive credentials are not configured.
    """
    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    target_folder = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if not creds_path or not Path(creds_path).is_file():
        raise RuntimeError("Google Drive service account JSON is not configured.")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    scopes = ["https://www.googleapis.com/auth/drive.file"]
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
    service = build("drive", "v3", credentials=creds)

    metadata = {"name": file_path.name}
    if target_folder:
        metadata["parents"] = [target_folder]

    media = MediaFileUpload(str(file_path), resumable=True)
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"]