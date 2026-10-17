"""
Hermetic unit test suite for pCloud client and extensible provider contract.
Verifies multi-region routing, protocol conformance, path sanitization,
folder management, outgoing request headers, and idempotent upload semantics.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

try:
    from .models import PCloudUserSettings
    from .pcloud_client import PCloudClient
    from .provider_contract import BackupUploadResult, CloudBackupProvider
except (ImportError, ValueError):
    from models import PCloudUserSettings
    from pcloud_client import PCloudClient
    from provider_contract import (
        BackupUploadResult,
        CloudBackupProvider,
    )


class TestPCloudClientAndProvider(unittest.TestCase):
    """Hermetic unit tests exercising PCloudClient and contract conformance."""

    def test_protocol_conformance(self):
        """PCloudClient satisfies runtime CloudBackupProvider protocol."""
        client = PCloudClient("test_token", location_id=1)
        self.assertIsInstance(client, CloudBackupProvider)
        self.assertEqual(client.provider_id, "pcloud")

    def test_multi_region_base_urls(self):
        """Location ID correctly selects US vs EU endpoints."""
        us_client = PCloudClient("token", location_id=1)
        self.assertEqual(us_client.base_url, "https://api.pcloud.com")

        eu_client = PCloudClient("token", location_id=2)
        self.assertEqual(eu_client.base_url, "https://eapi.pcloud.com")

        with self.assertRaises(ValueError):
            PCloudClient("token", location_id=3)

        with self.assertRaises(ValueError):
            PCloudClient("token", location_id=0)

    def test_sanitize_path(self):
        """Sanitizer cleans invalid characters and preserves valid text."""
        self.assertEqual(
            PCloudClient.sanitize_path('Meeting: "Q3 Strategy" / Review?'),
            "Meeting Q3 Strategy Review",
        )
        self.assertEqual(PCloudClient.sanitize_path("   "), "Untitled")
        self.assertEqual(PCloudClient.sanitize_path("."), "Untitled")
        self.assertEqual(PCloudClient.sanitize_path(".."), "Untitled")
        self.assertEqual(PCloudClient.sanitize_path("Normal_Folder_123"), "Normal_Folder_123")
        long_name = "a" * 200
        self.assertEqual(len(PCloudClient.sanitize_path(long_name)), 120)

    @patch("requests.get")
    def test_get_user_info_success_and_outgoing_call(self, mock_get):
        """User info returns parsed data and asserts outgoing request shape."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 0,
            "email": "user@example.com",
            "quota": 10737418240,
            "usedquota": 1048576,
        }
        mock_get.return_value = mock_resp

        client = PCloudClient("tok123", location_id=1)
        info, err = client.get_user_info()
        self.assertIsNone(err)
        self.assertIsNotNone(info)
        self.assertEqual(info["email"], "user@example.com")
        mock_get.assert_called_once_with(
            "https://api.pcloud.com/userinfo",
            headers={"Authorization": "Bearer tok123"},
            timeout=15,
        )

    @patch("requests.get")
    def test_get_user_info_error(self, mock_get):
        """Non-zero result in userinfo returns descriptive error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 2000,
            "error": "Log in required",
        }
        mock_get.return_value = mock_resp

        client = PCloudClient("tok123")
        info, err = client.get_user_info()
        self.assertIsNone(info)
        self.assertIn("Log in required", err)

    @patch("requests.get")
    def test_logout_success(self, mock_get):
        """Logout endpoint calls /logout with Bearer token and returns success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": 0, "auth_deleted": True}
        mock_get.return_value = mock_resp

        client = PCloudClient("tok123", location_id=1)
        ok, err = client.logout()
        self.assertTrue(ok)
        self.assertIsNone(err)
        mock_get.assert_called_once_with(
            "https://api.pcloud.com/logout",
            headers={"Authorization": "Bearer tok123"},
            timeout=10,
        )

    @patch("requests.get")
    def test_logout_error(self, mock_get):
        """Logout endpoint handles error response gracefully."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_get.return_value = mock_resp

        client = PCloudClient("tok123", location_id=2)
        ok, err = client.logout()
        self.assertFalse(ok)
        self.assertIn("HTTP error 400", err)
        mock_get.assert_called_once_with(
            "https://eapi.pcloud.com/logout",
            headers={"Authorization": "Bearer tok123"},
            timeout=10,
        )

    @patch("requests.post")
    def test_ensure_folder_success_and_sanitization(self, mock_post):
        """Ensure folder sanitizes components and creates sequential paths."""
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {
            "result": 0,
            "metadata": {"folderid": 482010, "name": "Omi Conversations"},
        }
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {
            "result": 0,
            "metadata": {"folderid": 482019, "name": "2026"},
        }
        mock_post.side_effect = [mock_resp1, mock_resp2]

        client = PCloudClient("tok123", location_id=2)
        folder_id, err = client.ensure_folder("/Omi: Conversations / 2026? /")
        self.assertIsNone(err)
        self.assertEqual(folder_id, 482019)
        self.assertEqual(mock_post.call_count, 2)
        called_paths = [call[1]["params"]["path"] for call in mock_post.call_args_list]
        self.assertEqual(called_paths, ["/Omi Conversations", "/Omi Conversations/2026"])

    @patch("requests.post")
    def test_ensure_folder_nested_creates_parents_in_order(self, mock_post):
        """ensure_folder sequentially creates intermediate parents to prevent pCloud error 2002."""
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {"result": 0, "metadata": {"folderid": 101}}

        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"result": 0, "metadata": {"folderid": 102}}

        mock_resp3 = MagicMock()
        mock_resp3.status_code = 200
        mock_resp3.json.return_value = {"result": 0, "metadata": {"folderid": 103}}

        mock_post.side_effect = [mock_resp1, mock_resp2, mock_resp3]

        client = PCloudClient("tok123")
        folder_id, err = client.ensure_folder("/omi/backups/transcripts")
        self.assertIsNone(err)
        self.assertEqual(folder_id, 103)
        self.assertEqual(mock_post.call_count, 3)
        called_paths = [call[1]["params"]["path"] for call in mock_post.call_args_list]
        self.assertEqual(called_paths, ["/omi", "/omi/backups", "/omi/backups/transcripts"])

    def test_ensure_folder_rejects_relative_components(self):
        """Relative path traversal components ('.' and '..') are rejected."""
        client = PCloudClient("tok123")
        folder_id, err = client.ensure_folder("/Omi/../Sensitive")
        self.assertIsNone(folder_id)
        self.assertIn("Invalid folder path component '..'", err)

        folder_id2, err2 = client.ensure_folder("/./")
        self.assertIsNone(folder_id2)
        self.assertIn("Invalid folder path component '.'", err2)

    @patch("requests.post")
    def test_upload_file_path_traversal_rejected(self, mock_post):
        """upload_file rejects . and .. traversal components and performs no upload."""
        client = PCloudClient("tok123")
        res, err = client.upload_file(
            folder_ref="/omi/../secret",
            filename="audio.wav",
            content=b"test",
        )
        self.assertIsNone(res)
        self.assertIn("relative traversal is not permitted", err)
        mock_post.assert_not_called()

        res2, err2 = client.upload_file(
            folder_ref="/omi/backups",
            filename="../secret.wav",
            content=b"test",
        )
        self.assertIsNone(res2)
        self.assertIn("relative traversal is not permitted", err2)
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_upload_file_default_overwrite_idempotency(self, mock_post):
        """Upload file defaults to overwrite=True (renameifexists=0) for retries."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 0,
            "metadata": [
                {
                    "fileid": 9821345,
                    "name": "transcript.md",
                    "size": 1500,
                    "modified": "Sun, 04 Oct 2026 00:00:00 +0000",
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = PCloudClient("tok123", location_id=1)
        res, err = client.upload_file(
            folder_ref=482019,
            filename="transcript.md",
            content=b"# Conversation transcript",
        )
        self.assertIsNone(err)
        self.assertIsInstance(res, BackupUploadResult)
        self.assertEqual(res.file_id, "9821345")
        self.assertEqual(res.filename, "transcript.md")
        self.assertEqual(res.size_bytes, 1500)
        self.assertEqual(res.path, "folderid:482019/transcript.md")

        # Verify outgoing params enforce renameifexists=0 (overwrite on retry)
        mock_post.assert_called_once_with(
            "https://api.pcloud.com/uploadfile",
            headers={"Authorization": "Bearer tok123"},
            params={
                "nopartial": 1,
                "renameifexists": 0,
                "folderid": 482019,
            },
            files={"file": ("transcript.md", b"# Conversation transcript")},
            timeout=30,
        )

    @patch("requests.post")
    def test_upload_file_path_string_sanitized(self, mock_post):
        """Upload file with string path sanitizes path components."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 0,
            "metadata": [
                {
                    "fileid": 1122334,
                    "name": "audio.wav",
                    "size": 4096,
                    "modified": "Sun, 04 Oct 2026 00:00:00 +0000",
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = PCloudClient("tok123", location_id=1)
        res, err = client.upload_file(
            folder_ref="/Omi: Backups / 2026? /",
            filename="audio.wav",
            content=b"RIFF...",
        )
        self.assertIsNone(err)
        self.assertEqual(res.path, "/Omi Backups/2026/audio.wav")
        mock_post.assert_called_once_with(
            "https://api.pcloud.com/uploadfile",
            headers={"Authorization": "Bearer tok123"},
            params={
                "nopartial": 1,
                "renameifexists": 0,
                "path": "/Omi Backups/2026",
            },
            files={"file": ("audio.wav", b"RIFF...")},
            timeout=30,
        )

    @patch("requests.post")
    def test_upload_file_network_exception(self, mock_post):
        """Network exception during upload returns safe error string."""
        mock_post.side_effect = Exception("Connection reset by peer")

        client = PCloudClient("tok123")
        res, err = client.upload_file(
            folder_ref=123,
            filename="audio.wav",
            content=b"RIFF...",
        )
        self.assertIsNone(res)
        self.assertIn("Connection reset by peer", err)

    def test_user_settings_validation_and_defaults(self):
        """PCloudUserSettings model enforces Literal[1, 2] validation."""
        settings = PCloudUserSettings()
        self.assertEqual(settings.folder_name, "Omi Conversations")
        self.assertTrue(settings.save_summary)
        self.assertTrue(settings.save_transcript)
        self.assertTrue(settings.save_audio)
        self.assertEqual(settings.location_id, 1)

        # Valid EU setting
        eu_settings = PCloudUserSettings(location_id=2)
        self.assertEqual(eu_settings.location_id, 2)

        # Invalid location_id rejected by Pydantic validation
        with self.assertRaises(ValidationError):
            PCloudUserSettings(location_id=3)

        with self.assertRaises(ValidationError):
            PCloudUserSettings(location_id=0)


if __name__ == "__main__":
    unittest.main()
