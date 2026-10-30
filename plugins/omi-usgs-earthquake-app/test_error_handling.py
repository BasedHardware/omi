"""
Tests ensuring error messages, HTTP request exceptions, and unhandled errors
in the USGS earthquake app do not leak internal URLs, private IPs, credentials,
or raw stack traces to the API response callers.
"""

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from test_main import (
    DummyFastAPI,
    DummyRequest,
    DummyState,
    install_dependency_stubs,
)

install_dependency_stubs()
import main  # noqa: E402

SENSITIVE_HOST = "192.168.1.42"
SENSITIVE_TOKEN = "sec_token_999888777"
SENSITIVE_DETAIL = (
    f"ConnectionRefusedError: failed to connect to http://{SENSITIVE_HOST}:8080/fdsnws?auth={SENSITIVE_TOKEN}"
)


class TestUSGSErrorHandlingAndLeakPrevention(unittest.TestCase):
    def setUp(self):
        main.app.state = DummyState()

    def test_usgs_get_http_status_error_does_not_leak_sensitive_details(self):
        """HTTPStatusError should log status, return generic failure without internal URL/token."""
        import httpx

        req = object()
        resp = types.SimpleNamespace(status_code=502)
        exc = getattr(httpx, "HTTPStatusError", Exception)(SENSITIVE_DETAIL, request=req, response=resp)

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(side_effect=exc)
        mock_client.aclose = AsyncMock()
        main.app.state.http_client = mock_client

        result = asyncio.run(main._usgs_get({"format": "geojson"}))
        self.assertIn("error", result)
        self.assertNotIn(SENSITIVE_HOST, result["error"])
        self.assertNotIn(SENSITIVE_TOKEN, result["error"])
        self.assertIn("USGS request failed", result["error"])
        self.assertIn("502", result["error"])

    def test_usgs_get_network_error_does_not_leak_sensitive_details(self):
        """Network/transport HTTPError should not leak raw connection details or internal IPs."""
        import httpx

        exc = getattr(httpx, "HTTPError", Exception)(SENSITIVE_DETAIL)

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(side_effect=exc)
        mock_client.aclose = AsyncMock()
        main.app.state.http_client = mock_client

        result = asyncio.run(main._usgs_get({"format": "geojson"}))
        self.assertIn("error", result)
        self.assertNotIn(SENSITIVE_HOST, result["error"])
        self.assertNotIn(SENSITIVE_TOKEN, result["error"])
        self.assertEqual(result["error"], "USGS request failed due to a network error.")

    def test_usgs_get_unexpected_exception_does_not_leak_details(self):
        """Unexpected internal exceptions in _usgs_get are masked safely."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.get = AsyncMock(side_effect=RuntimeError(SENSITIVE_DETAIL))
        mock_client.aclose = AsyncMock()
        main.app.state.http_client = mock_client

        result = asyncio.run(main._usgs_get({"format": "geojson"}))
        self.assertIn("error", result)
        self.assertNotIn(SENSITIVE_HOST, result["error"])
        self.assertNotIn(SENSITIVE_TOKEN, result["error"])
        self.assertEqual(result["error"], "USGS request failed due to an internal error.")

    def test_tool_recent_earthquakes_catches_unhandled_exception(self):
        """tool_recent_earthquakes handles unexpected errors cleanly without crashing."""
        req = DummyRequest(payload={"hours": 12})
        with patch.object(main, "_list_earthquakes", side_effect=RuntimeError(SENSITIVE_DETAIL)):
            res = asyncio.run(main.tool_recent_earthquakes(req))

        self.assertFalse(res.success)
        self.assertNotIn(SENSITIVE_HOST, res.message)
        self.assertNotIn(SENSITIVE_TOKEN, res.message)
        self.assertEqual(res.message, "An unexpected error occurred while fetching recent earthquakes.")
        self.assertEqual(res.data.get("error"), "internal error")

    def test_tool_nearby_earthquakes_catches_unhandled_exception(self):
        """tool_nearby_earthquakes handles unexpected errors cleanly without crashing."""
        req = DummyRequest(payload={"latitude": 37.77, "longitude": -122.42})
        with patch.object(main, "_list_earthquakes", side_effect=RuntimeError(SENSITIVE_DETAIL)):
            res = asyncio.run(main.tool_nearby_earthquakes(req))

        self.assertFalse(res.success)
        self.assertNotIn(SENSITIVE_HOST, res.message)
        self.assertNotIn(SENSITIVE_TOKEN, res.message)
        self.assertEqual(res.message, "An unexpected error occurred while searching nearby earthquakes.")
        self.assertEqual(res.data.get("error"), "internal error")

    def test_tool_earthquake_details_catches_unhandled_exception(self):
        """tool_earthquake_details handles unexpected errors cleanly without crashing."""
        req = DummyRequest(payload={"event_id": "us7000abcd"})
        with patch.object(main, "_usgs_get", side_effect=RuntimeError(SENSITIVE_DETAIL)):
            res = asyncio.run(main.tool_earthquake_details(req))

        self.assertFalse(res.success)
        self.assertNotIn(SENSITIVE_HOST, res.message)
        self.assertNotIn(SENSITIVE_TOKEN, res.message)
        self.assertEqual(res.message, "An unexpected error occurred while retrieving earthquake details.")
        self.assertEqual(res.data.get("error"), "internal error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
