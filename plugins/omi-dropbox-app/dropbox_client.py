"""
Dropbox API client wrapper.
"""
import json
import re
from typing import Optional, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class DropboxClient:
    """Client for Dropbox API operations."""

    API_BASE = "https://api.dropboxapi.com/2"
    CONTENT_BASE = "https://content.dropboxapi.com/2"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _headers(self, content_type: str = "application/json") -> dict:
        """Get standard headers for API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }

    @staticmethod
    def sanitize_path(name: str) -> str:
        """
        Sanitize a string to be safe for Dropbox paths.
        Removes/replaces characters that are invalid in Dropbox paths.
        """
        # Characters not allowed in Dropbox: < > : " / \ | ? *
        invalid_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(invalid_chars, "", name)
        # Replace multiple spaces with single space
        sanitized = re.sub(r"\s+", " ", sanitized)
        # Trim to reasonable length
        sanitized = sanitized[:100].strip()
        # Ensure it's not empty
        if not sanitized:
            sanitized = "Untitled"
        return sanitized

    def get_account(self) -> Tuple[Optional[dict], Optional[str]]:
        """
        Get current user's account info.
        Returns (account_info, error_message).
        """
        try:
            response = requests.post(
                f"{self.API_BASE}/users/get_current_account",
                headers=self._headers(),
            )

            if response.status_code == 200:
                return response.json(), None
            else:
                return None, f"Failed to get account: {response.text}"

        except Exception as e:
            return None, f"Error getting account: {str(e)}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    )
    def create_folder(self, path: str) -> Tuple[Optional[dict], Optional[str]]:
        """
        Create a folder at the given path.
        Returns (folder_metadata, error_message).
        If folder already exists, returns success.
        """
        try:
            response = requests.post(
                f"{self.API_BASE}/files/create_folder_v2",
                headers=self._headers(),
                json={"path": path, "autorename": False},
            )

            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 409:
                # Folder already exists - this is fine
                error_data = response.json()
                if "path" in str(error_data) and "conflict" in str(error_data):
                    return {"path": path, "already_exists": True}, None
                return None, f"Conflict: {response.text}"
            else:
                return None, f"Failed to create folder: {response.text}"

        except Exception as e:
            return None, f"Error creating folder: {str(e)}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    )
    def upload_file(
        self,
        path: str,
        content: bytes,
        mode: str = "overwrite",
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        Upload a file to Dropbox.
        For files < 150MB.
        Returns (file_metadata, error_message).
        """
        try:
            # Dropbox-API-Arg header requires JSON
            api_arg = json.dumps({
                "path": path,
                "mode": mode,
                "autorename": True,
                "mute": False,
            })

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": api_arg,
            }

            response = requests.post(
                f"{self.CONTENT_BASE}/files/upload",
                headers=headers,
                data=content,
            )

            if response.status_code == 200:
                return response.json(), None
            else:
                return None, f"Failed to upload file: {response.text}"

        except Exception as e:
            return None, f"Error uploading file: {str(e)}"

    def folder_exists(self, path: str) -> bool:
        """Check if a folder exists at the given path."""
        try:
            response = requests.post(
                f"{self.API_BASE}/files/get_metadata",
                headers=self._headers(),
                json={"path": path},
            )
            if response.status_code == 200:
                metadata = response.json()
                return metadata.get(".tag") == "folder"
            return False
        except Exception:
            return False

    def ensure_folder_exists(self, path: str) -> Tuple[bool, Optional[str]]:
        """
        Ensure a folder exists, creating it if necessary.
        Returns (success, error_message).
        """
        if self.folder_exists(path):
            return True, None

        result, error = self.create_folder(path)
        if error and "already_exists" not in str(result):
            return False, error
        return True, None

    def search_files(
        self,
        query: str,
        path: str = "",
        max_results: int = 10,
    ) -> Tuple[Optional[list], Optional[str]]:
        """
        Search for files in Dropbox.
        Returns (results_list, error_message).
        """
        try:
            payload = {
                "query": query,
                "options": {
                    "max_results": max_results,
                    "file_status": "active",
                },
            }

            if path:
                payload["options"]["path"] = path

            response = requests.post(
                f"{self.API_BASE}/files/search_v2",
                headers=self._headers(),
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                matches = data.get("matches", [])
                results = []
                for match in matches:
                    metadata = match.get("metadata", {}).get("metadata", {})
                    results.append({
                        "name": metadata.get("name", "Unknown"),
                        "path": metadata.get("path_display", ""),
                        "type": metadata.get(".tag", "file"),
                        "size": metadata.get("size", 0),
                        "modified": metadata.get("server_modified", ""),
                    })
                return results, None
            else:
                return None, f"Search failed: {response.text}"

        except Exception as e:
            return None, f"Error searching: {str(e)}"

    def list_folder(
        self,
        path: str = "",
        limit: int = 20,
    ) -> Tuple[Optional[list], Optional[str]]:
        """
        List files in a folder.
        Returns (files_list, error_message).
        """
        try:
            response = requests.post(
                f"{self.API_BASE}/files/list_folder",
                headers=self._headers(),
                json={
                    "path": path if path else "",
                    "limit": limit,
                    "recursive": False,
                },
            )

            if response.status_code == 200:
                data = response.json()
                entries = data.get("entries", [])
                results = []
                for entry in entries:
                    results.append({
                        "name": entry.get("name", "Unknown"),
                        "path": entry.get("path_display", ""),
                        "type": entry.get(".tag", "file"),
                        "size": entry.get("size", 0),
                        "modified": entry.get("server_modified", ""),
                    })
                return results, None
            else:
                return None, f"List failed: {response.text}"

        except Exception as e:
            return None, f"Error listing: {str(e)}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    )
    def download_file(self, path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download a file from Dropbox.
        Returns (file_bytes, error_message).
        """
        try:
            api_arg = json.dumps({"path": path})

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Dropbox-API-Arg": api_arg,
            }

            response = requests.post(
                f"{self.CONTENT_BASE}/files/download",
                headers=headers,
            )

            if response.status_code == 200:
                return response.content, None
            else:
                return None, f"Failed to download file: {response.text}"

        except Exception as e:
            return None, f"Error downloading file: {str(e)}"
