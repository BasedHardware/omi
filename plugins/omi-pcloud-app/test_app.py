"""
Hermetic unit and integration tests for pCloud Omi plugin FastAPI service (main.py).
Tests OAuth flow, setup webview, user settings, privacy consent gating, and conversation export.
Runs under standard library unittest without third-party server or live network dependencies.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import MagicMock, patch

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import db
import main
from models import ActionItem, Conversation, Structured, TranscriptSegment
from pcloud_client import BackupUploadResult


def _get_body_text(response) -> str:
    """Extracts text content across Starlette Response (.body bytes) and fallback shim (.content/.body)."""
    if hasattr(response, "body") and response.body is not None:
        if isinstance(response.body, bytes):
            return response.body.decode("utf-8", errors="replace")
        return str(response.body)
    if hasattr(response, "content") and response.content is not None:
        if isinstance(response.content, bytes):
            return response.content.decode("utf-8", errors="replace")
        return str(response.content)
    return ""


def _get_redirect_location(response) -> str:
    """Extracts redirect target across Starlette Response (headers['location']) and fallback shim (.url)."""
    if hasattr(response, "headers") and response.headers is not None:
        loc = response.headers.get("location") or response.headers.get("Location")
        if loc:
            return str(loc)
    if hasattr(response, "url") and response.url:
        return str(response.url)
    return ""


class TestPCloudAppHermetic(unittest.TestCase):
    """Hermetic test suite exercising main.py endpoints, webhooks, and privacy gates."""

    def setUp(self):
        # Clear test data directory before each test
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "data")
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir, ignore_errors=True)

        # Clear in-memory audio buffers
        main.audio_buffers.clear()
        main.audio_sample_rates.clear()
        main.audio_buffer_created.clear()

        # Set default test environment variables
        os.environ["PCLOUD_TOKEN_ENCRYPTION_KEY"] = "test-encryption-key-for-hermetic-unit-tests"
        main.PCLOUD_CLIENT_ID = "test_client_id_123"
        main.PCLOUD_CLIENT_SECRET = "test_client_secret_xyz"
        main.PCLOUD_REDIRECT_URI = "https://test.omi.me/auth/pcloud/callback"

    def tearDown(self):
        os.environ.pop("PCLOUD_TOKEN_ENCRYPTION_KEY", None)
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir, ignore_errors=True)

    def test_health_check(self):
        """Health check returns status ok and provider pcloud."""
        res = asyncio.run(main.health_check())
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["provider"], "pcloud")

    def test_setup_page_disconnected(self):
        """Setup page renders Not Connected badge and connect button for unauthenticated users."""
        res = asyncio.run(main.setup_page(uid="user_anon"))
        html_content = _get_body_text(res)
        self.assertIn("pCloud Backup for Omi", html_content)
        self.assertIn("Not Connected", html_content)
        self.assertIn("Connect pCloud Account", html_content)
        self.assertIn("Privacy & Retention Policy", html_content)

    def test_setup_page_connected(self):
        """Setup page renders Connected badge and email for authenticated users."""
        db.store_pcloud_tokens(
            uid="user_authed",
            access_token="valid_access_tok",
            location_id=1,
            userid=9876,
            email="contributor@example.com",
        )
        res = asyncio.run(main.setup_page(uid="user_authed"))
        html_content = _get_body_text(res)
        self.assertIn("Connected as contributor@example.com", html_content)
        self.assertIn("Disconnect pCloud", html_content)

    def test_auth_pcloud_redirect_url(self):
        """OAuth initiate generates secure state and redirects to correct region."""
        # US region (location_id=1)
        res_us = asyncio.run(main.auth_pcloud(uid="user_1", location_id=1))
        loc_us = _get_redirect_location(res_us)
        self.assertTrue(loc_us.startswith("https://my.pcloud.com/oauth2/authorize"))
        self.assertIn("client_id=test_client_id_123", loc_us)
        self.assertIn("state=", loc_us)

        # EU region (location_id=2)
        res_eu = asyncio.run(main.auth_pcloud(uid="user_1", location_id=2))
        loc_eu = _get_redirect_location(res_eu)
        self.assertTrue(loc_eu.startswith("https://e-my.pcloud.com/oauth2/authorize"))

    @patch("requests.post")
    @patch.object(main.PCloudClient, "get_user_info")
    def test_auth_pcloud_callback_success(self, mock_get_user_info, mock_post):
        """OAuth callback exchanges code for token, stores encrypted credentials, and redirects."""
        # Pre-seed CSRF state
        db.store_oauth_state(state="csrf_state_123", uid="user_callback", location_id=1)

        # Mock pCloud token response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": 0,
            "access_token": "secret_access_token_abc",
            "userid": 554433,
            "locationid": 1,
        }
        mock_post.return_value = mock_resp
        mock_get_user_info.return_value = ({"email": "oauth_user@example.com"}, None)

        res = asyncio.run(main.auth_pcloud_callback(code="auth_code_xyz", state="csrf_state_123"))
        loc = _get_redirect_location(res)
        self.assertIn("/setup/pcloud?uid=user_callback&status=connected", loc)

        # Verify token was encrypted and stored in database
        tokens = db.get_pcloud_tokens("user_callback")
        self.assertIsNotNone(tokens)
        self.assertEqual(tokens["access_token"], "secret_access_token_abc")
        self.assertEqual(tokens["email"], "oauth_user@example.com")

        # Verify CSRF state was consumed
        self.assertIsNone(db.get_oauth_state("csrf_state_123"))

    def test_auth_pcloud_callback_invalid_state(self):
        """OAuth callback rejects invalid or expired state with 400 Bad Request."""
        res = asyncio.run(main.auth_pcloud_callback(code="auth_code_xyz", state="invalid_expired_state"))
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid or Expired OAuth State", _get_body_text(res))

    @patch.object(main.PCloudClient, "logout")
    def test_disconnect(self, mock_logout):
        """Disconnect endpoint calls pCloud /logout, erases stored tokens, and redirects."""
        mock_logout.return_value = (True, None)
        db.store_pcloud_tokens("user_disc", "tok_disc", location_id=1)
        self.assertIsNotNone(db.get_pcloud_tokens("user_disc"))

        res = asyncio.run(main.disconnect_pcloud(uid="user_disc"))
        loc = _get_redirect_location(res)
        self.assertIn("status=disconnected", loc)
        self.assertIsNone(db.get_pcloud_tokens("user_disc"))
        mock_logout.assert_called_once()

    def test_fail_fast_encryption_key_missing(self):
        """Encryption functions fail fast with RuntimeError if no encryption key is configured."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                db._get_encryption_key()
            self.assertIn("PCLOUD_TOKEN_ENCRYPTION_KEY or APP_SECRET", str(ctx.exception))

    def test_save_settings(self):
        """Settings endpoint updates user preferences and retention defaults."""
        res = asyncio.run(
            main.save_settings(
                uid="user_settings",
                folder_name="Custom Backups",
                location_id=2,
                save_summary="on",
                save_transcript="on",
                save_audio=None,  # Audio unchecked
            )
        )
        self.assertIn("status=settings_saved", _get_redirect_location(res))

        s = db.get_user_settings("user_settings")
        self.assertEqual(s["folder_name"], "Custom Backups")
        self.assertEqual(s["location_id"], 2)
        self.assertTrue(s["save_summary"])
        self.assertTrue(s["save_transcript"])
        self.assertFalse(s["save_audio"])

    @patch.object(main.PCloudClient, "upload_file")
    @patch.object(main.PCloudClient, "ensure_folder")
    def test_conversation_export_full(self, mock_ensure_folder, mock_upload_file):
        """Conversation webhook exports summary, transcript, and audio when user is connected."""
        uid = "user_export"
        db.store_pcloud_tokens(uid, "tok_valid", location_id=1)
        db.store_user_settings(
            uid,
            {
                "folder_name": "Omi Conversations",
                "save_summary": True,
                "save_transcript": True,
                "save_audio": True,
            },
        )

        # Buffer synthetic audio
        main.audio_buffers[uid] = b"\x00\x01\x02\x03" * 100
        main.audio_sample_rates[uid] = 16000
        main.audio_buffer_created[uid] = datetime.now(timezone.utc)

        mock_ensure_folder.return_value = (501, None)
        mock_upload_file.return_value = (
            BackupUploadResult("f1", "summary.md", "/Omi/conv/summary.md", 250, "now"),
            None,
        )

        conv = Conversation(
            id="conv_101",
            created_at=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 6, 12, 15, tzinfo=timezone.utc),
            structured=Structured(
                title="DeepMind Team Sync",
                overview="Discussion regarding graph-router deployment.",
                emoji="🚀",
                category="work",
                action_items=[ActionItem(description="Review PR #20498", completed=True)],
            ),
            transcript_segments=[
                TranscriptSegment(text="Hello everyone", speaker="Abubakr", is_user=True, start=0.0, end=2.5),
                TranscriptSegment(text="All systems green", speaker="Lead", is_user=False, start=2.6, end=5.0),
            ],
            discarded=False,
        )

        resp = asyncio.run(main.on_conversation_created(conv, uid=uid))
        self.assertIn("summary.md", resp.message)
        self.assertIn("transcript.md", resp.message)
        self.assertIn("audio.wav", resp.message)

        # Verify folder ensure and all 3 uploads occurred
        mock_ensure_folder.assert_called_once()
        self.assertEqual(mock_upload_file.call_count, 3)

    @patch.object(main.PCloudClient, "upload_file")
    @patch.object(main.PCloudClient, "ensure_folder")
    def test_conversation_export_privacy_consent_gating(self, mock_ensure_folder, mock_upload_file):
        """User opting out of private transcript and audio strictly blocks their export."""
        uid = "user_privacy"
        db.store_pcloud_tokens(uid, "tok_valid", location_id=1)
        # Explicitly opt-out of transcript and audio
        db.store_user_settings(
            uid,
            {
                "folder_name": "Omi Conversations",
                "save_summary": True,
                "save_transcript": False,  # No consent for transcript
                "save_audio": False,  # No consent for audio
            },
        )

        # Audio present in buffer
        main.audio_buffers[uid] = b"\x00\x01\x02\x03" * 50

        mock_ensure_folder.return_value = (502, None)
        mock_upload_file.return_value = (
            BackupUploadResult("f2", "summary.md", "/Omi/conv/summary.md", 200, "now"),
            None,
        )

        conv = Conversation(
            id="conv_102",
            structured=Structured(title="Private Medical Consultation", overview="Confidential notes"),
            transcript_segments=[TranscriptSegment(text="Sensitive details", start=0.0, end=1.0)],
            discarded=False,
        )

        resp = asyncio.run(main.on_conversation_created(conv, uid=uid))
        self.assertIn("summary.md", resp.message)
        self.assertNotIn("transcript.md", resp.message)
        self.assertNotIn("audio.wav", resp.message)

        # Exactly 1 upload occurred (summary only)
        self.assertEqual(mock_upload_file.call_count, 1)

    def test_conversation_discarded_skipped(self):
        """Discarded conversations are skipped without creating folders or uploads."""
        uid = "user_discard"
        db.store_pcloud_tokens(uid, "tok_valid", location_id=1)

        conv = Conversation(id="conv_discarded", discarded=True)
        resp = asyncio.run(main.on_conversation_created(conv, uid=uid))
        self.assertEqual(resp.message, "Skipped discarded conversation")

    def test_conversation_account_isolation_unconnected(self):
        """Unconnected accounts fail-closed with clear status message."""
        conv = Conversation(id="conv_anon")
        resp = asyncio.run(main.on_conversation_created(conv, uid="unconnected_uid"))
        self.assertEqual(resp.message, "pCloud account not connected")


if __name__ == "__main__":
    unittest.main()
