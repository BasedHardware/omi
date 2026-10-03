"""
Protocol contract for extensible cloud backup providers in Omi.
Enables pluggable destinations (pCloud, Dropbox, S3, WebDAV).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple, runtime_checkable


@dataclass(frozen=True)
class BackupUploadResult:
    """Unified result metadata returned by cloud backup providers."""

    file_id: str
    filename: str
    path: str
    size_bytes: int
    modified_time: str


@runtime_checkable
class CloudBackupProvider(Protocol):
    """Formal protocol for cloud backup destinations."""

    provider_id: str

    def ensure_folder(
        self, folder_path: str
    ) -> Tuple[Optional[str | int], Optional[str]]:
        """Ensures the destination folder hierarchy exists.

        Returns (folder_identifier, error_message).
        """
        ...

    def upload_file(
        self,
        folder_ref: str | int,
        filename: str,
        content: bytes,
        overwrite: bool = True,
    ) -> Tuple[Optional[BackupUploadResult], Optional[str]]:
        """Uploads binary file content to the destination folder.

        Returns (BackupUploadResult, error_message).
        """
        ...

    def sanitize_path(self, name: str) -> str:
        """Normalizes and strips invalid path characters."""
        ...
