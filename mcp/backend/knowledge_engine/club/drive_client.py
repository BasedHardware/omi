"""
Google Drive Client for Club Knowledge

Fixes vs original:
  • Module-level singleton removed — instantiation deferred to
    get_drive_client() so a missing service-account file doesn't crash
    every module that imports from knowledge_engine.club.
"""

import io
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from knowledge_engine.club.config import club_config

logger = logging.getLogger(__name__)


class ClubDriveClient:
    """
    Google Drive client for downloading club documents.

    Expected folder structure in Drive:
        RoboticsClub/
        ├── Events/
        │   └── <EventName>/
        │       ├── overview.md
        │       ├── problem_statement.pdf
        │       ├── rules.md
        │       └── metadata.json
        ├── Announcements/
        │   ├── announcements.md
        │   └── pinned.md
        ├── Coordinators/
        │   └── coordinators.csv
        └── Archives/   ← ignored
    """

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    SUPPORTED_MIME_TYPES = {
        "application/pdf": ".pdf",
        "application/vnd.google-apps.document": ".docx",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "text/csv": ".csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }

    EXPORT_MIME_TYPES = {
        "application/vnd.google-apps.document": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        "application/vnd.google-apps.spreadsheet": "text/csv",
    }

    def __init__(self):
        self.service_account_file = club_config.CLUB_DRIVE_SERVICE_ACCOUNT_FILE
        self.root_folder_id = club_config.CLUB_DRIVE_FOLDER_ID
        self.service = None
        logger.info("Initialising ClubDriveClient")
        self._authenticate()

    def _authenticate(self):
        if not self.service_account_file.exists():
            raise FileNotFoundError(
                f"Service account file not found: {self.service_account_file}. "
                "Add the JSON key file to backend/credentials/"
            )
        credentials = service_account.Credentials.from_service_account_file(
            str(self.service_account_file), scopes=self.SCOPES
        )
        self.service = build("drive", "v3", credentials=credentials)
        logger.info("✓ Authenticated with Google Drive")

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def download_all_documents(self) -> Dict[str, Any]:
        """
        Download all documents from the RoboticsClub folder structure.

        Returns:
            {
                "total_files": int,
                "downloaded" : int,
                "skipped"    : int,
                "errors"     : int,
                "files"      : [{"path", "local_path", "category", "metadata"}, …],
                "timestamp"  : str,
            }
        """
        logger.info(f"Starting download from folder ID: {self.root_folder_id}")

        result: Dict[str, Any] = {
            "total_files": 0,
            "downloaded": 0,
            "skipped": 0,
            "errors": 0,
            "files": [],
            "timestamp": datetime.now().isoformat(),
        }

        try:
            for folder_name in [
                club_config.CLUB_EVENTS_FOLDER,
                club_config.CLUB_ANNOUNCEMENTS_FOLDER,
                club_config.CLUB_COORDINATORS_FOLDER,
            ]:
                folder_id = self._find_folder(folder_name, self.root_folder_id)
                if not folder_id:
                    logger.warning(f"Folder '{folder_name}' not found — skipping")
                    continue

                fr = self._download_folder_recursive(
                    folder_id=folder_id,
                    folder_name=folder_name,
                    category=folder_name.lower(),
                    parent_path="",
                )
                result["total_files"] += fr["total_files"]
                result["downloaded"]  += fr["downloaded"]
                result["skipped"]     += fr["skipped"]
                result["errors"]      += fr["errors"]
                result["files"].extend(fr["files"])

            logger.info(
                f"Download complete: {result['downloaded']} downloaded, "
                f"{result['skipped']} skipped, {result['errors']} errors"
            )
            return result

        except Exception as exc:
            logger.error(f"Error during download: {exc}")
            result["errors"] += 1
            return result

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _find_folder(self, folder_name: str, parent_id: str) -> Optional[str]:
        try:
            query = (
                f"name='{folder_name}' and "
                f"'{parent_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            results = self.service.files().list(
                q=query, fields="files(id, name)"
            ).execute()
            files = results.get("files", [])
            return files[0]["id"] if files else None
        except HttpError as exc:
            logger.error(f"Error finding folder '{folder_name}': {exc}")
            return None

    def _download_folder_recursive(
        self,
        folder_id: str,
        folder_name: str,
        category: str,
        parent_path: str,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "total_files": 0,
            "downloaded": 0,
            "skipped": 0,
            "errors": 0,
            "files": [],
        }

        try:
            resp = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, modifiedTime, parents)",
                pageSize=1000,
            ).execute()

            current_path = f"{parent_path}/{folder_name}" if parent_path else folder_name

            for item in resp.get("files", []):
                name = item["name"]
                mime = item["mimeType"]

                if name in club_config.CLUB_IGNORED_FILES:
                    result["skipped"] += 1
                    continue

                if mime == "application/vnd.google-apps.folder":
                    if name in club_config.CLUB_IGNORED_FOLDERS:
                        continue
                    sub = self._download_folder_recursive(
                        folder_id=item["id"],
                        folder_name=name,
                        category=category,
                        parent_path=current_path,
                    )
                    for k in ("total_files", "downloaded", "skipped", "errors"):
                        result[k] += sub[k]
                    result["files"].extend(sub["files"])
                    continue

                result["total_files"] += 1

                if not self._is_supported(mime, name):
                    result["skipped"] += 1
                    continue

                file_path = f"{current_path}/{name}"
                downloaded = self._download_file(item, file_path, category)
                if downloaded:
                    result["downloaded"] += 1
                    result["files"].append(downloaded)
                else:
                    result["errors"] += 1

            return result

        except HttpError as exc:
            logger.error(f"Error listing folder '{folder_name}': {exc}")
            result["errors"] += 1
            return result

    def _is_supported(self, mime_type: str, filename: str) -> bool:
        if mime_type in self.SUPPORTED_MIME_TYPES:
            return True
        return Path(filename).suffix.lower() in {".md", ".txt", ".pdf", ".csv", ".docx"}

    def _download_file(
        self, file_item: Dict[str, Any], relative_path: str, category: str
    ) -> Optional[Dict[str, Any]]:
        try:
            file_id = file_item["id"]
            file_name = file_item["name"]
            mime_type = file_item["mimeType"]

            if mime_type in self.EXPORT_MIME_TYPES:
                export_mime = self.EXPORT_MIME_TYPES[mime_type]
                request = self.service.files().export_media(
                    fileId=file_id, mimeType=export_mime
                )
                ext = self.SUPPORTED_MIME_TYPES.get(export_mime, ".txt")
                file_name = Path(file_name).stem + ext
            else:
                request = self.service.files().get_media(fileId=file_id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            local_path = club_config.CLUB_UPLOADS_DIR / relative_path.lstrip("/")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(fh.getvalue())

            logger.info(f"✓ Downloaded: {relative_path}")

            event_name = None
            if category == "events":
                parts = Path(relative_path).parts
                if len(parts) >= 2:
                    event_name = parts[1]

            return {
                "path": relative_path,
                "local_path": str(local_path),
                "category": category,
                "metadata": {
                    "source": relative_path,
                    "category": category,
                    "event_name": event_name,
                    "file_id": file_id,
                    "modified_time": file_item.get("modifiedTime"),
                    "mime_type": mime_type,
                    "filename": file_name,
                },
            }

        except Exception as exc:
            logger.error(f"Error downloading {relative_path}: {exc}")
            return None


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------
_drive_client: Optional[ClubDriveClient] = None


def get_drive_client() -> ClubDriveClient:
    """Return the shared ClubDriveClient, creating it on first call."""
    global _drive_client
    if _drive_client is None:
        _drive_client = ClubDriveClient()
    return _drive_client


# Backward-compat alias (not imported at module load — only used explicitly)
class _LazyDriveProxy:
    def __getattr__(self, name):
        return getattr(get_drive_client(), name)


drive_client: ClubDriveClient = _LazyDriveProxy()  # type: ignore[assignment]
