"""
Hermetic unit test suite for pCloud client and extensible provider contract.
Verifies multi-region routing, protocol conformance, path sanitization,
folder management, and idempotent file upload semantics.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pcloud_client import PCloudClient
from pcloud_models import PCloudUserSettings
from pcloud_provider_contract import BackupUploadResult, CloudBackupProvider


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

    def test_sanitize_path(self):
        """Sanitizer cleans invalid characters and preserves valid text."""
        self.assertEqual(
            PCloudClient.sanitize_path('Meeting: "Q3 Strategy" / Review?'),
            "Meeting Q3 Strategy Review",
        )
        self.assertEqual(PCloudClient.sanitize_path("   "), "Untitled")
        self.assertEqual(
            PCloudClient.sanitize_path("Normal_Folder_123"), "Normal_Folder_123"
        )
        long_name = "a" * 200
        self.assertEqual(len(PCloudClient.sanitize_path(long_name)), 120)

    @patch("requests.get")
    def test_get_user_info_success(self, mock_get):
        """User info returns parsed data on success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 0,
            "email": "user@example.com",
            "quota": 10737418240,
            "usedquota": 1048576,
        }
        mock_get.return_value = mock_resp

        client = PCloudClient("tok123")
        info, err = client.get_user_info()
        self.assertIsNone(err)
        self.assertIsNotNone(info)
        self.assertEqual(info["email"], "user@example.com")

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

    @patch("requests.post")
    def test_ensure_folder_success(self, mock_post):
        """Ensure folder returns folderid when successful."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 0,
            "metadata": {"folderid": 482019, "name": "Omi Conversations"},
        }
        mock_post.return_value = mock_resp

        client = PCloudClient("tok123")
        folder_id, err = client.ensure_folder("/Omi Conversations")
        self.assertIsNone(err)
        self.assertEqual(folder_id, 482019)

    @patch("requests.post")
    def test_ensure_folder_failure(self, mock_post):
        """Ensure folder returns error when pCloud rejects path."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 2004,
            "error": "Access denied",
        }
        mock_post.return_value = mock_resp

        client = PCloudClient("tok123")
        folder_id, err = client.ensure_folder("/Restricted")
        self.assertIsNone(folder_id)
        self.assertIn("Access denied", err)

    @patch("requests.post")
    def test_upload_file_success(self, mock_post):
        """File upload returns BackupUploadResult with metadata."""
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

        client = PCloudClient("tok123")
        res, err = client.upload_file(
            folder_ref=482019,
            filename="transcript.md",
            content=b"# Conversation transcript content",
        )
        self.assertIsNone(err)
        self.assertIsInstance(res, BackupUploadResult)
        self.assertEqual(res.file_id, "9821345")
        self.assertEqual(res.filename, "transcript.md")
        self.assertEqual(res.size_bytes, 1500)

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

    def test_user_settings_defaults(self):
        """PCloudUserSettings model enforces defaults and validation."""
        settings = PCloudUserSettings()
        self.assertEqual(settings.folder_name, "Omi Conversations")
        self.assertTrue(settings.save_summary)
        self.assertTrue(settings.save_transcript)
        self.assertTrue(settings.save_audio)
        self.assertEqual(settings.location_id, 1)


if __name__ == "__main__":
    unittest.main()
