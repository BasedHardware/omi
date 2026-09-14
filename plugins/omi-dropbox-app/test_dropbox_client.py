import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Hermetic module stubs for environments without requests/tenacity
if "tenacity" not in sys.modules:
    tenacity_stub = types.ModuleType("tenacity")
    def identity_decorator(*args, **kwargs):
        def decorator(f):
            return f
        return decorator
    tenacity_stub.retry = identity_decorator
    tenacity_stub.stop_after_attempt = lambda *args, **kwargs: None
    tenacity_stub.wait_exponential = lambda *args, **kwargs: None
    tenacity_stub.retry_if_exception_type = lambda *args, **kwargs: None
    sys.modules["tenacity"] = tenacity_stub

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.post = lambda *args, **kwargs: None
    requests_stub.get = lambda *args, **kwargs: None
    exceptions_stub = types.ModuleType("requests.exceptions")
    exceptions_stub.Timeout = Exception
    exceptions_stub.ConnectionError = Exception
    requests_stub.exceptions = exceptions_stub
    sys.modules["requests"] = requests_stub
    sys.modules["requests.exceptions"] = exceptions_stub

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dropbox_client
from dropbox_client import DropboxClient


class TestDropboxClient(unittest.TestCase):
    def setUp(self):
        self.client = DropboxClient("test-token")

    def test_sanitize_path(self):
        self.assertEqual(DropboxClient.sanitize_path("file:name?.txt"), "filename.txt")
        self.assertEqual(DropboxClient.sanitize_path(""), "Untitled")
        self.assertEqual(DropboxClient.sanitize_path("hello   world"), "hello world")

    @patch("requests.post")
    def test_list_folder_single_page(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "entries": [
                {
                    "name": "doc.pdf",
                    "path_display": "/docs/doc.pdf",
                    ".tag": "file",
                    "size": 1024,
                    "server_modified": "2026-09-01T10:00:00Z"
                }
            ],
            "cursor": "c1",
            "has_more": False
        }
        mock_post.return_value = mock_resp

        results, error = self.client.list_folder("/docs", limit=10)
        self.assertIsNone(error)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "doc.pdf")
        self.assertEqual(results[0]["size"], 1024)

    @patch("requests.post")
    def test_list_folder_multi_page_cursor_continuation(self, mock_post):
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "entries": [
                {"name": "file1.txt", "path_display": "/file1.txt", ".tag": "file", "size": 10}
            ],
            "cursor": "cursor_page1",
            "has_more": True
        }

        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "entries": [
                {"name": "file2.txt", "path_display": "/file2.txt", ".tag": "file", "size": 20}
            ],
            "cursor": "cursor_page2",
            "has_more": False
        }

        mock_post.side_effect = [page1, page2]

        results, error = self.client.list_folder("", limit=10)
        self.assertIsNone(error)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "file1.txt")
        self.assertEqual(results[1]["name"], "file2.txt")
        self.assertEqual(mock_post.call_count, 2)

    @patch("requests.post")
    def test_list_folder_respects_limit(self, mock_post):
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "entries": [
                {"name": "file1.txt", "path_display": "/file1.txt", ".tag": "file", "size": 10},
                {"name": "file2.txt", "path_display": "/file2.txt", ".tag": "file", "size": 20}
            ],
            "cursor": "c1",
            "has_more": True
        }
        mock_post.return_value = page1

        results, error = self.client.list_folder("", limit=1)
        self.assertIsNone(error)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "file1.txt")
        # Should not have called continue since len(results) >= limit
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_list_folder_error_handling(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "path not found"
        mock_post.return_value = mock_resp

        results, error = self.client.list_folder("/nonexistent")
        self.assertIsNone(results)
        self.assertIn("List failed", error)


if __name__ == "__main__":
    unittest.main()
