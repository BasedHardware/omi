"""
Production client implementation for pCloud REST API.
Supports multi-region routing (US & EU data centers) and implements
the CloudBackupProvider Protocol.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
import requests

try:
    from .pcloud_provider_contract import BackupUploadResult, CloudBackupProvider
except ImportError:
    from pcloud_provider_contract import BackupUploadResult, CloudBackupProvider


class PCloudClient(CloudBackupProvider):
    """Client for pCloud REST API supporting US and EU data centers."""

    provider_id: str = "pcloud"
    API_BASE_US: str = "https://api.pcloud.com"
    API_BASE_EU: str = "https://eapi.pcloud.com"

    def __init__(self, access_token: str, location_id: int = 1):
        self.access_token = access_token.strip()
        self.location_id = location_id
        self.base_url = (
            self.API_BASE_EU if self.location_id == 2 else self.API_BASE_US
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
        }

    @staticmethod
    def sanitize_path(name: str) -> str:
        """Sanitizes directory or file name for cloud filesystem safety."""
        # Strip invalid characters: < > : " / \ | ? * and control chars
        invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        sanitized = re.sub(invalid_chars, "", name)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        if not sanitized:
            return "Untitled"
        return sanitized[:120]

    def get_user_info(self) -> Tuple[Optional[dict], Optional[str]]:
        """Retrieves user profile information and quota status from pCloud."""
        try:
            resp = requests.get(
                f"{self.base_url}/userinfo",
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("result") == 0:
                    return data, None
                return None, f"pCloud error: {data.get('error', 'Unknown')}"
            return None, f"HTTP error {resp.status_code}: {resp.text}"
        except Exception as ex:
            return None, f"Network exception: {str(ex)}"

    def ensure_folder(
        self, folder_path: str
    ) -> Tuple[Optional[int], Optional[str]]:
        """Ensures a folder hierarchy exists via pCloud /createfolderifnotexists.

        Returns (folder_id, error_message).
        """
        clean_path = f"/{folder_path.strip('/')}"
        try:
            resp = requests.post(
                f"{self.base_url}/createfolderifnotexists",
                headers=self._headers(),
                params={"path": clean_path},
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("result") == 0:
                    meta = data.get("metadata", {})
                    folder_id = meta.get("folderid")
                    return folder_id, None
                return None, f"pCloud createfolder error: {data.get('error')}"
            return None, f"HTTP error {resp.status_code}: {resp.text}"
        except Exception as ex:
            return None, f"Network exception creating folder: {str(ex)}"

    def upload_file(
        self,
        folder_ref: str | int,
        filename: str,
        content: bytes,
        overwrite: bool = False,
    ) -> Tuple[Optional[BackupUploadResult], Optional[str]]:
        """Uploads file content to the specified folder with conflict handling."""
        clean_filename = self.sanitize_path(filename)
        params: dict[str, str | int] = {
            "nopartial": 1,
            "renameifexists": 0 if overwrite else 1,
        }
        if isinstance(folder_ref, int) or (
            isinstance(folder_ref, str) and folder_ref.isdigit()
        ):
            params["folderid"] = int(folder_ref)
        else:
            params["path"] = f"/{str(folder_ref).strip('/')}"

        files = {"file": (clean_filename, content)}
        try:
            resp = requests.post(
                f"{self.base_url}/uploadfile",
                headers=self._headers(),
                params=params,
                files=files,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("result") == 0:
                    raw_meta = data.get("metadata", [])
                    meta = (
                        raw_meta[0] if isinstance(raw_meta, list) else raw_meta
                    )
                    file_id = str(meta.get("fileid", ""))
                    actual_name = meta.get("name", clean_filename)
                    size_bytes = meta.get("size", len(content))
                    modified = str(meta.get("modified", ""))
                    return (
                        BackupUploadResult(
                            file_id=file_id,
                            filename=actual_name,
                            path=f"/{actual_name}",
                            size_bytes=size_bytes,
                            modified_time=modified,
                        ),
                        None,
                    )
                return None, f"pCloud upload error: {data.get('error')}"
            return None, f"HTTP error {resp.status_code}: {resp.text}"
        except Exception as ex:
            return None, f"Network exception uploading file: {str(ex)}"
