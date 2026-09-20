import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omi-plugin-sdk" / "src"))

from dropbox_client import DropboxClient
from main import (
    app,
    get_valid_access_token,
    refresh_access_token,
    refresh_access_token_full,
)

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


class TestDropboxTokenRefreshAndTools(unittest.TestCase):
    def test_valid_token_not_expired(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tokens = {
            "access_token": "valid_token",
            "refresh_token": "valid_refresh",
            "expires_at": future,
        }
        with patch("main.get_dropbox_tokens", return_value=tokens), \
             patch("main.refresh_access_token_full") as mock_refresh:
            token = get_valid_access_token("user_123")
            self.assertEqual(token, "valid_token")
            mock_refresh.assert_not_called()

    def test_expired_token_refreshes_and_persists_to_db(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tokens = {
            "access_token": "expired_token",
            "refresh_token": "my_refresh",
            "expires_at": past,
        }
        new_future = (datetime.now(timezone.utc) + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        refresh_result = {
            "access_token": "refreshed_access_token",
            "expires_at": new_future,
            "refresh_token": "new_refresh_token",
        }

        with patch("main.get_dropbox_tokens", return_value=tokens), \
             patch("main.refresh_access_token_full", return_value=refresh_result) as mock_refresh, \
             patch("main.update_dropbox_tokens") as mock_update:
            token = get_valid_access_token("user_123")
            self.assertEqual(token, "refreshed_access_token")
            mock_refresh.assert_called_once_with("my_refresh")
            mock_update.assert_called_once_with(
                "user_123",
                "refreshed_access_token",
                new_future,
                "new_refresh_token",
            )

    def test_refresh_access_token_string_wrapper(self):
        with patch("main.refresh_access_token_full", return_value={"access_token": "tok_123"}):
            self.assertEqual(refresh_access_token("ref"), "tok_123")

        with patch("main.refresh_access_token_full", return_value=None):
            self.assertIsNone(refresh_access_token("ref"))

    def test_search_files_handles_none_metadata_records(self):
        client = DropboxClient("test_token")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "matches": [
                {"metadata": None},  # None metadata bug
                {"metadata": {"metadata": None}},  # Nested None metadata
                "not-a-dict",  # Corrupted match
                {
                    "metadata": {
                        "metadata": {
                            "name": "Report.pdf",
                            "path_display": "/Documents/Report.pdf",
                            ".tag": "file",
                            "size": 2048,
                            "server_modified": "2026-09-20T10:00:00Z",
                        }
                    }
                },
            ]
        }

        with patch("requests.post", return_value=mock_resp):
            results, error = client.search_files("Report")
            self.assertIsNone(error)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["name"], "Report.pdf")
            self.assertEqual(results[0]["path"], "/Documents/Report.pdf")

    @unittest.skipIf(TestClient is None, "fastapi test client not installed")
    def test_chat_tools_reject_non_dict_body(self):
        client = TestClient(app)
        for endpoint in ["/tools/search", "/tools/list", "/tools/read"]:
            res = client.post(endpoint, json=["not", "a", "dict"])
            self.assertEqual(res.status_code, 200)
            self.assertIn("request body must be a JSON object", res.json().get("error", ""))

    @unittest.skipIf(TestClient is None, "fastapi test client not installed")
    def test_chat_tool_search_coerces_and_validates_query(self):
        client = TestClient(app)
        with patch("main.get_valid_access_token", return_value="tok"):
            # Empty / whitespace query
            res = client.post("/tools/search", json={"uid": "u1", "query": "   "})
            self.assertIn("Please provide a search query", res.json().get("error", ""))

            # Numeric query coerced to string
            with patch.object(DropboxClient, "search_files", return_value=([], None)) as mock_search:
                res = client.post("/tools/search", json={"uid": "u1", "query": 2026})
                mock_search.assert_called_once_with("2026", max_results=10)


if __name__ == "__main__":
    unittest.main()
