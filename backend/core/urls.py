from django.urls import path
from .backup_views import (
    backup_download_view,
    backup_drive_upload_view,
    backup_restore_view,
)

urlpatterns = [
    path("backup/download/", backup_download_view, name="core-backup-download"),
    path("backup/drive-upload/", backup_drive_upload_view, name="core-backup-drive-upload"),
    path("backup/restore/", backup_restore_view, name="core-backup-restore"),
]