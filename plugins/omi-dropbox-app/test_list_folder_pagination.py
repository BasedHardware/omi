"""Hermetic regression tests for Dropbox folder listing pagination.

Standard library only: requests is stubbed before the client is loaded so the
suite runs under plain python3 (the manifest lane).

Covers the list_folder defect: /files/list_folder returns `has_more` with a
`cursor` and Dropbox documents its `limit` as approximate, so a single request
can come back short while more entries remain. The client returned that first
page as the whole folder, so `list_files` reported part of a folder as all of
it, with no sign anything was missing.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_requests = types.ModuleType("requests")
_requests.post = None
_exceptions = types.ModuleType("requests.exceptions")


class _Timeout(Exception):
    pass


class _ConnectionError(Exception):
    pass


_exceptions.Timeout = _Timeout
_exceptions.ConnectionError = _ConnectionError
_requests.exceptions = _exceptions

_tenacity = types.ModuleType("tenacity")
_tenacity.retry = lambda *a, **k: (lambda function: function)
_tenacity.stop_after_attempt = lambda *a, **k: None
_tenacity.wait_exponential = lambda *a, **k: None
_tenacity.retry_if_exception_type = lambda *a, **k: None

sys.modules.setdefault("requests", _requests)
sys.modules.setdefault("requests.exceptions", _exceptions)
sys.modules.setdefault("tenacity", _tenacity)

spec = importlib.util.spec_from_file_location(
    "dropbox_client_under_test", Path(__file__).with_name("dropbox_client.py")
)
dropbox_client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dropbox_client)


class _Response:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def _entry(name):
    return {"name": name, "path_display": f"/{name}", ".tag": "file", "size": 1, "server_modified": "2026-01-01"}


class ListFolderPaginationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.client = dropbox_client.DropboxClient("test-token")

    def respond(self, *pages):
        queue = list(pages)

        def post(url, headers=None, json=None, **kwargs):
            self.calls.append((url, json))
            return queue.pop(0)

        dropbox_client.requests.post = post

    def test_a_short_first_page_still_returns_the_whole_folder(self):
        self.respond(
            _Response({"entries": [_entry("a"), _entry("b")], "has_more": True, "cursor": "c1"}),
            _Response({"entries": [_entry("c")], "has_more": False}),
        )

        results, error = self.client.list_folder("/work", limit=20)

        self.assertIsNone(error)
        self.assertEqual([r["name"] for r in results], ["a", "b", "c"])
        self.assertTrue(self.calls[1][0].endswith("/files/list_folder/continue"))
        self.assertEqual(self.calls[1][1], {"cursor": "c1"})

    def test_the_requested_limit_is_never_exceeded(self):
        self.respond(
            _Response({"entries": [_entry(str(i)) for i in range(2)], "has_more": True, "cursor": "c1"}),
            _Response({"entries": [_entry(str(i)) for i in range(2, 6)], "has_more": True, "cursor": "c2"}),
        )

        results, error = self.client.list_folder("/work", limit=3)

        self.assertIsNone(error)
        self.assertEqual(len(results), 3)
        self.assertEqual(len(self.calls), 2)

    def test_a_complete_first_page_asks_for_nothing_more(self):
        self.respond(_Response({"entries": [_entry("a")], "has_more": False}))

        results, error = self.client.list_folder("/work", limit=20)

        self.assertIsNone(error)
        self.assertEqual([r["name"] for r in results], ["a"])
        self.assertEqual(len(self.calls), 1)

    def test_has_more_without_a_cursor_stops_instead_of_looping(self):
        self.respond(_Response({"entries": [_entry("a")], "has_more": True}))

        results, error = self.client.list_folder("/work", limit=20)

        self.assertIsNone(error)
        self.assertEqual([r["name"] for r in results], ["a"])
        self.assertEqual(len(self.calls), 1)

    def test_a_failed_continuation_is_an_error_not_a_partial_listing(self):
        self.respond(
            _Response({"entries": [_entry("a")], "has_more": True, "cursor": "c1"}),
            _Response({}, status_code=401, text="expired_access_token"),
        )

        results, error = self.client.list_folder("/work", limit=20)

        self.assertIsNone(results)
        self.assertIn("expired_access_token", error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
