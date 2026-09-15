import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Hermetic module stubs for environments without requests/tenacity
if "requests" not in sys.modules:
    try:
        import requests
    except ImportError:
        requests = types.ModuleType("requests")
        requests.post = lambda *args, **kwargs: None
        requests.get = lambda *args, **kwargs: None
        requests.Response = MagicMock
        exceptions_stub = types.ModuleType("requests.exceptions")
        exceptions_stub.Timeout = type("Timeout", (Exception,), {})
        exceptions_stub.ConnectionError = type("ConnectionError", (Exception,), {})
        requests.exceptions = exceptions_stub
        sys.modules["requests"] = requests
        sys.modules["requests.exceptions"] = exceptions_stub

if not hasattr(sys.modules["requests"], "Response"):
    sys.modules["requests"].Response = MagicMock

if "tenacity" not in sys.modules:
    try:
        import tenacity
    except ImportError:
        tenacity = types.ModuleType("tenacity")

        class _StopAfterAttempt:
            def __init__(self, max_attempts):
                self.max_attempts = max_attempts

        class _RetryIfExceptionType:
            def __init__(self, exc_types):
                self.exc_types = exc_types

        def _stop_after_attempt(max_attempts):
            return _StopAfterAttempt(max_attempts)

        def _wait_exponential(*args, **kwargs):
            return None

        def _retry_if_exception_type(exc_types):
            return _RetryIfExceptionType(exc_types)

        def _retry(*dargs, **dkwargs):
            stop_obj = dkwargs.get("stop")
            max_attempts = stop_obj.max_attempts if isinstance(stop_obj, _StopAfterAttempt) else 3
            retry_obj = dkwargs.get("retry")
            exc_types = retry_obj.exc_types if isinstance(retry_obj, _RetryIfExceptionType) else (Exception,)

            def decorator(f):
                def wrapper(*args, **kwargs):
                    for attempt in range(1, max_attempts + 1):
                        try:
                            return f(*args, **kwargs)
                        except exc_types:
                            if attempt >= max_attempts:
                                raise

                return wrapper

            return decorator

        tenacity.retry = _retry
        tenacity.stop_after_attempt = _stop_after_attempt
        tenacity.wait_exponential = _wait_exponential
        tenacity.retry_if_exception_type = _retry_if_exception_type
        sys.modules["tenacity"] = tenacity

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
                    "server_modified": "2026-09-01T10:00:00Z",
                }
            ],
            "cursor": "c1",
            "has_more": False,
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
            "entries": [{"name": "file1.txt", "path_display": "/file1.txt", ".tag": "file", "size": 10}],
            "cursor": "cursor_page1",
            "has_more": True,
        }

        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "entries": [{"name": "file2.txt", "path_display": "/file2.txt", ".tag": "file", "size": 20}],
            "cursor": "cursor_page2",
            "has_more": False,
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
                {"name": "file2.txt", "path_display": "/file2.txt", ".tag": "file", "size": 20},
            ],
            "cursor": "c1",
            "has_more": True,
        }
        mock_post.return_value = page1

        results, error = self.client.list_folder("", limit=1)
        self.assertIsNone(error)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "file1.txt")
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_list_folder_zero_limit(self, mock_post):
        results, error = self.client.list_folder("/docs", limit=0)
        self.assertIsNone(error)
        self.assertEqual(results, [])
        self.assertEqual(mock_post.call_count, 0)

    @patch("requests.post")
    def test_list_folder_error_handling(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "path not found"
        mock_post.return_value = mock_resp

        results, error = self.client.list_folder("/nonexistent")
        self.assertIsNone(results)
        self.assertIn("List failed", error)

    @patch("requests.post")
    def test_list_folder_continuation_failure(self, mock_post):
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "entries": [{"name": "file1.txt", "path_display": "/file1.txt", ".tag": "file", "size": 10}],
            "cursor": "c_fail",
            "has_more": True,
        }

        page2 = MagicMock()
        page2.status_code = 500
        page2.text = "internal error"

        mock_post.side_effect = [page1, page2]

        results, error = self.client.list_folder("", limit=10)
        self.assertIsNone(results)
        self.assertIn("List continuation failed: internal error", error)

    @patch("requests.post")
    def test_download_file_immediate_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"sample file bytes"
        mock_post.return_value = mock_resp

        data, err = self.client.download_file("/test.txt")
        self.assertIsNone(err)
        self.assertEqual(data, b"sample file bytes")
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_download_file_non_retryable_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "File not found"
        mock_post.return_value = mock_resp

        data, err = self.client.download_file("/missing.txt")
        self.assertIsNone(data)
        self.assertIn("Failed to download file: File not found", err)
        self.assertEqual(mock_post.call_count, 1)

    @patch("time.sleep", return_value=None)
    @patch("requests.post")
    def test_download_file_retries_on_timeout_and_succeeds(self, mock_post, _mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"recovered content"

        side_effects = [sys.modules["requests"].exceptions.Timeout("timed out"), mock_resp]
        mock_post.side_effect = side_effects

        data, err = self.client.download_file("/transient.txt")
        self.assertIsNone(err)
        self.assertEqual(data, b"recovered content")
        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep", return_value=None)
    @patch("requests.post")
    def test_download_file_retries_on_connection_error_and_succeeds(self, mock_post, _mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"recovered from disconnect"

        side_effects = [sys.modules["requests"].exceptions.ConnectionError("connection reset"), mock_resp]
        mock_post.side_effect = side_effects

        data, err = self.client.download_file("/disconnect.txt")
        self.assertIsNone(err)
        self.assertEqual(data, b"recovered from disconnect")
        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep", return_value=None)
    @patch("requests.post")
    def test_download_file_exhausts_retries_and_returns_clean_error(self, mock_post, _mock_sleep):
        timeout_cls = sys.modules["requests"].exceptions.Timeout
        side_effects = [
            timeout_cls("timed out 1"),
            timeout_cls("timed out 2"),
            timeout_cls("timed out 3"),
        ]
        mock_post.side_effect = side_effects

        data, err = self.client.download_file("/failing.txt")
        self.assertIsNone(data)
        self.assertIn("Error downloading file: timed out 3", err)
        self.assertEqual(mock_post.call_count, 3)


if __name__ == "__main__":
    unittest.main()
