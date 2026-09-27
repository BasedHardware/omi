"""Hermetic unit tests for Dropbox token refresh persistence, metadata safety, and input coercion.

Runs under standard library unittest without third-party dependencies (FastAPI/TestClient not required).
"""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda f: f

    post = get


class DummyResponse:
    def __init__(self, *args, **kwargs):
        pass


class EndpointResponseStub:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


class ResponseStandIn:
    """Minimal requests.Response stand-in used when requests is not installed."""

    status_code = 0
    text = ""

    def __init__(self, *args, **kwargs):
        pass

    def json(self):
        return {}

    def raise_for_status(self):
        return None


def identity_retry(*args, **kwargs):
    """Stand-in for tenacity.retry's decorating form when tenacity is absent."""

    def decorate(func):
        return func

    return decorate


def make_module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


# Framework stubs for hermetic execution without fastapi/requests/tenacity installed
stubs = {
    "requests": make_module(
        "requests",
        RequestException=OSError,
        post=lambda *a, **kw: None,
        get=lambda *a, **kw: None,
        Response=ResponseStandIn,
        # dropbox_client evaluates requests.exceptions.* at decoration time
        exceptions=make_module(
            "requests.exceptions",
            RequestException=OSError,
            Timeout=OSError,
            ConnectionError=OSError,
        ),
    ),
    "tenacity": make_module(
        "tenacity",
        retry=identity_retry,
        stop_after_attempt=lambda *a, **kw: None,
        wait_exponential=lambda *a, **kw: None,
        retry_if_exception_type=lambda *a, **kw: None,
    ),
    "dotenv": make_module("dotenv", load_dotenv=lambda *a, **kw: None),
    "fastapi": make_module(
        "fastapi",
        FastAPI=Framework,
        Request=object,
        Query=lambda default=None, **kw: default,
        HTTPException=Exception,
    ),
    "fastapi.responses": make_module(
        "fastapi.responses",
        HTMLResponse=DummyResponse,
        RedirectResponse=DummyResponse,
        JSONResponse=DummyResponse,
    ),
    "db": make_module(
        "db",
        store_dropbox_tokens=Mock(),
        get_dropbox_tokens=Mock(),
        update_dropbox_tokens=Mock(),
        delete_dropbox_tokens=Mock(),
        store_oauth_state=Mock(),
        get_oauth_state=Mock(),
        delete_oauth_state=Mock(),
        get_user_settings=Mock(),
        store_user_settings=Mock(),
    ),
    "models": make_module("models", Conversation=dict, EndpointResponse=EndpointResponseStub),
}

# Only inject stubs if modules are not already installed
active_stubs = {k: v for k, v in stubs.items() if k not in sys.modules}

spec = importlib.util.spec_from_file_location(
    "dropbox_main", Path(__file__).with_name("main.py")
)
dropbox_main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, active_stubs):
    spec.loader.exec_module(dropbox_main)
    # dropbox_client imports requests/tenacity itself, so it must load inside the
    # stubbed window too when those packages are absent.
    import dropbox_client  # noqa: E402
    from dropbox_client import DropboxClient  # noqa: E402


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class TestDropboxTokenRefreshAndTools(unittest.TestCase):
    def test_valid_token_not_expired(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tokens = {
            "access_token": "valid_token",
            "refresh_token": "valid_refresh",
            "expires_at": future,
        }
        with patch.object(dropbox_main, "get_dropbox_tokens", return_value=tokens), \
             patch.object(dropbox_main, "refresh_access_token_full") as mock_refresh:
            token = dropbox_main.get_valid_access_token("user_123")
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

        with patch.object(dropbox_main, "get_dropbox_tokens", return_value=tokens), \
             patch.object(dropbox_main, "refresh_access_token_full", return_value=refresh_result) as mock_refresh, \
             patch.object(dropbox_main, "update_dropbox_tokens") as mock_update:
            token = dropbox_main.get_valid_access_token("user_123")
            self.assertEqual(token, "refreshed_access_token")
            mock_refresh.assert_called_once_with("my_refresh")
            mock_update.assert_called_once_with(
                "user_123",
                "refreshed_access_token",
                new_future,
                "new_refresh_token",
            )

    def test_refresh_access_token_string_wrapper(self):
        with patch.object(dropbox_main, "refresh_access_token_full", return_value={"access_token": "tok_123"}):
            self.assertEqual(dropbox_main.refresh_access_token("ref"), "tok_123")

        with patch.object(dropbox_main, "refresh_access_token_full", return_value=None):
            self.assertIsNone(dropbox_main.refresh_access_token("ref"))

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

        with patch.object(dropbox_client.requests, "post", return_value=mock_resp):
            results, error = client.search_files("Report")
            self.assertIsNone(error)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["name"], "Report.pdf")
            self.assertEqual(results[0]["path"], "/Documents/Report.pdf")

    def test_chat_tools_reject_non_dict_body(self):
        tools = [dropbox_main.tool_search_dropbox, dropbox_main.tool_list_dropbox, dropbox_main.tool_read_dropbox_file]
        for tool in tools:
            res = asyncio.run(tool(FakeRequest(["not", "a", "dict"])))
            self.assertIn("error", res)
            self.assertIn("request body must be a JSON object", res["error"])

    def test_chat_tool_search_coerces_and_validates_query(self):
        with patch.object(dropbox_main, "get_valid_access_token", return_value="tok"):
            # Empty / whitespace query
            res = asyncio.run(dropbox_main.tool_search_dropbox(FakeRequest({"uid": "u1", "query": "   "})))
            self.assertIn("error", res)
            self.assertIn("Please provide a search query", res["error"])

            # Numeric query coerced to string
            with patch.object(DropboxClient, "search_files", return_value=([], None)) as mock_search:
                res = asyncio.run(dropbox_main.tool_search_dropbox(FakeRequest({"uid": "u1", "query": 2026})))
                mock_search.assert_called_once_with("2026", max_results=10)


if __name__ == "__main__":
    unittest.main()
