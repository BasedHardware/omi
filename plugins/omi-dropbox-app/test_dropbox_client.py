"""
Tests for dropbox_client.py — Dropbox API client wrapper.

Run directly (``python3 test_dropbox_client.py``) or via pytest/unittest.
All network access is mocked, so the suite is hermetic.
"""
import time
import unittest
from unittest.mock import MagicMock, patch

import requests

from dropbox_client import DropboxClient


def _resp(status: int, json_body: dict = None, text: str = ""):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.json.return_value = json_body if json_body is not None else {}
    return m


class TestDownloadFile(unittest.TestCase):
    def test_download_file_immediate_success(self):
        client = DropboxClient("fake_token")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"sample file bytes"

        with patch("requests.post", return_value=mock_resp) as mock_post:
            data, err = client.download_file("/test.txt")
            self.assertIsNone(err)
            self.assertEqual(data, b"sample file bytes")
            self.assertEqual(mock_post.call_count, 1)

    def test_download_file_non_retryable_http_error(self):
        client = DropboxClient("fake_token")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "File not found"

        with patch("requests.post", return_value=mock_resp) as mock_post:
            data, err = client.download_file("/missing.txt")
            self.assertIsNone(data)
            self.assertIn("Failed to download file: File not found", err)
            self.assertEqual(mock_post.call_count, 1)

    def test_download_file_retries_on_timeout_and_succeeds(self):
        client = DropboxClient("fake_token")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"recovered content"

        side_effects = [requests.exceptions.Timeout("timed out"), mock_resp]

        with patch("requests.post", side_effect=side_effects) as mock_post, \
                patch("time.sleep", return_value=None):
            data, err = client.download_file("/transient.txt")
            self.assertIsNone(err)
            self.assertEqual(data, b"recovered content")
            self.assertEqual(mock_post.call_count, 2)

    def test_download_file_retries_on_connection_error_and_succeeds(self):
        client = DropboxClient("fake_token")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"recovered from disconnect"

        side_effects = [requests.exceptions.ConnectionError("connection reset"), mock_resp]

        with patch("requests.post", side_effect=side_effects) as mock_post, \
                patch("time.sleep", return_value=None):
            data, err = client.download_file("/disconnect.txt")
            self.assertIsNone(err)
            self.assertEqual(data, b"recovered from disconnect")
            self.assertEqual(mock_post.call_count, 2)

    def test_download_file_exhausts_retries_and_returns_clean_error(self):
        client = DropboxClient("fake_token")
        side_effects = [
            requests.exceptions.Timeout("timed out 1"),
            requests.exceptions.Timeout("timed out 2"),
            requests.exceptions.Timeout("timed out 3"),
        ]

        with patch("requests.post", side_effect=side_effects) as mock_post, \
                patch("time.sleep", return_value=None):
            data, err = client.download_file("/failing.txt")
            self.assertIsNone(data)
            self.assertIn("Error downloading file: timed out 3", err)
            self.assertEqual(mock_post.call_count, 3)


class TestListFolder(unittest.TestCase):
    """Regression + behavior tests for cursor pagination in list_folder()."""

    LIST_URL = "https://api.dropboxapi.com/2/files/list_folder"
    CONT_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"

    def _router(self, list_specs, cont_specs):
        list_idx = {"i": 0}
        cont_idx = {"i": 0}

        def side_effect(url, *args, **kwargs):
            if url.endswith("/files/list_folder/continue"):
                specs = cont_specs
                idx = cont_idx["i"]
                cont_idx["i"] += 1
            elif url.endswith("/files/list_folder"):
                specs = list_specs
                idx = list_idx["i"]
                list_idx["i"] += 1
            else:
                return _resp(200, {})
            idx = min(idx, len(specs) - 1)
            spec = specs[idx]
            return _resp(spec["status"], spec.get("json", {}), spec.get("text", ""))

        return side_effect

    def test_list_folder_single_page(self):
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [{"status": 200, "json": {
                "entries": [
                    {"name": "a.txt", "path_display": "/a.txt", ".tag": "file", "size": 1, "server_modified": "t1"},
                    {"name": "b.txt", "path_display": "/b.txt", ".tag": "file", "size": 2, "server_modified": "t2"},
                ],
                "has_more": False,
            }}],
            [],
        )
        with patch("requests.post", side_effect=side_effect) as mock_post:
            data, err = client.list_folder("/")
            self.assertIsNone(err)
            self.assertEqual([e["name"] for e in data], ["a.txt", "b.txt"])
            # Only the initial page was fetched.
            self.assertEqual(mock_post.call_count, 1)

    def test_list_folder_multi_page_continuation(self):
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [{"status": 200, "json": {
                "entries": [{"name": "a", "path_display": "/a", ".tag": "file", "size": 1, "server_modified": "t"}],
                "has_more": True, "cursor": "c1",
            }}],
            [{"status": 200, "json": {
                "entries": [{"name": "b", "path_display": "/b", ".tag": "file", "size": 2, "server_modified": "t"}],
                "has_more": False, "cursor": None,
            }}],
        )
        with patch("requests.post", side_effect=side_effect) as mock_post:
            data, err = client.list_folder("/")
            self.assertIsNone(err)
            self.assertEqual([e["name"] for e in data], ["a", "b"])
            # Initial page + one continuation page.
            self.assertEqual(mock_post.call_count, 2)

    def test_list_folder_respects_limit_across_pages(self):
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [{"status": 200, "json": {
                "entries": [
                    {"name": "a", "path_display": "/a", ".tag": "file", "size": 1, "server_modified": "t"},
                    {"name": "b", "path_display": "/b", ".tag": "file", "size": 1, "server_modified": "t"},
                    {"name": "c", "path_display": "/c", ".tag": "file", "size": 1, "server_modified": "t"},
                ],
                "has_more": True, "cursor": "c1",
            }}],
            [{"status": 200, "json": {
                "entries": [
                    {"name": "d", "path_display": "/d", ".tag": "file", "size": 1, "server_modified": "t"},
                    {"name": "e", "path_display": "/e", ".tag": "file", "size": 1, "server_modified": "t"},
                ],
                "has_more": False, "cursor": None,
            }}],
        )
        with patch("requests.post", side_effect=side_effect):
            data, err = client.list_folder("/", limit=3)
            self.assertIsNone(err)
            self.assertEqual(len(data), 3)
            self.assertEqual([e["name"] for e in data], ["a", "b", "c"])

    def test_list_folder_surfaces_continuation_error(self):
        """A failing continuation page must be reported, not silently dropped."""
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [{"status": 200, "json": {
                "entries": [{"name": "a", "path_display": "/a", ".tag": "file", "size": 1, "server_modified": "t"}],
                "has_more": True, "cursor": "c1",
            }}],
            [{"status": 500, "json": {}, "text": "internal error"}],
        )
        with patch("requests.post", side_effect=side_effect):
            data, err = client.list_folder("/")
            # Partial results are preserved, but the error is surfaced.
            self.assertIsNotNone(err)
            self.assertIn("List pagination failed", err)
            self.assertEqual([e["name"] for e in data], ["a"])

    def test_list_folder_recovers_from_cursor_reset(self):
        """HTTP 409 reset on the cursor restarts the listing once."""
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [
                {"status": 200, "json": {
                    "entries": [{"name": "a", "path_display": "/a", ".tag": "file", "size": 1, "server_modified": "t"}],
                    "has_more": True, "cursor": "stale",
                }},
                # Restart response after the 409
                {"status": 200, "json": {
                    "entries": [
                        {"name": "x", "path_display": "/x", ".tag": "file", "size": 1, "server_modified": "t"},
                        {"name": "y", "path_display": "/y", ".tag": "file", "size": 1, "server_modified": "t"},
                    ],
                    "has_more": False, "cursor": None,
                }},
            ],
            [{"status": 409, "json": {"error_summary": "reset/..."}, "text": "reset"}],
        )
        with patch("requests.post", side_effect=side_effect) as mock_post:
            data, err = client.list_folder("/")
            self.assertIsNone(err)
            self.assertEqual([e["name"] for e in data], ["x", "y"])
            # Initial + continuation(409) + restart = 3 POSTs.
            self.assertEqual(mock_post.call_count, 3)

    def test_list_folder_initial_error(self):
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [{"status": 500, "json": {}, "text": "auth failed"}],
            [],
        )
        with patch("requests.post", side_effect=side_effect):
            data, err = client.list_folder("/")
            self.assertIsNone(data)
            self.assertIn("List failed: auth failed", err)

    def test_list_folder_handles_missing_fields(self):
        client = DropboxClient("fake_token")
        side_effect = self._router(
            [{"status": 200, "json": {
                "entries": [{"name": "a", "path_display": "/a"}],  # no .tag/size/modified
                "has_more": False,
            }}],
            [],
        )
        with patch("requests.post", side_effect=side_effect):
            data, err = client.list_folder("/")
            self.assertIsNone(err)
            self.assertEqual(data[0]["type"], "file")
            self.assertEqual(data[0]["size"], 0)
            self.assertEqual(data[0]["modified"], "")


if __name__ == "__main__":
    unittest.main()
