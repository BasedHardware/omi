"""Hermetic regression tests for plugins/omi-hermes-agent-app/main.py.

Standard library only: httpx and fastapi are stubbed with minimal mock objects
before importing main so the suite runs cleanly under python3 -S or plain python3
without external site-packages installed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Starlette to be installed.
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message="", *, response=None):
                super().__init__(message)
                self.response = response

        class ConnectError(HTTPError):
            pass

        class TimeoutException(HTTPError):
            pass

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                raise AssertionError("tests must stub client calls; no network allowed")

            async def post(self, *args, **kwargs):
                raise AssertionError("tests must stub client calls; no network allowed")

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.ConnectError = ConnectError
        httpx.TimeoutException = TimeoutException
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str = ""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = {}

            def get(self, path: str, *args, **kwargs):
                def decorator(fn):
                    self.routes[("GET", path)] = fn
                    return fn
                return decorator

            def post(self, path: str, *args, **kwargs):
                def decorator(fn):
                    self.routes[("POST", path)] = fn
                    return fn
                return decorator

        class Request:
            def __init__(self, json_data=None, headers=None):
                self._json_data = json_data
                self.headers = headers or {}

            async def json(self):
                if isinstance(self._json_data, Exception):
                    raise self._json_data
                return self._json_data

        fastapi.HTTPException = HTTPException
        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main


class FakeRequest:
    def __init__(self, json_data=None, headers=None):
        self._json_data = json_data
        self.headers = headers or {}

    async def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class HermesClientAsyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = main.Settings(
            hermes_api_url="http://hermes.test",
            hermes_api_key="test-key",
            allowed_uids=frozenset({"uid-1"}),
            allowed_app_ids=frozenset({"app-1"}),
            timeout_seconds=1.0,
            instructions="Test instructions",
        )

    @staticmethod
    def _response(payload: dict[str, str]) -> mock.Mock:
        response = mock.Mock()
        response.json.return_value = payload
        return response

    def _async_client(self) -> tuple[mock.Mock, mock.Mock]:
        client = mock.Mock()
        context = mock.MagicMock()
        context.__aenter__ = mock.AsyncMock(return_value=client)
        context.__aexit__ = mock.AsyncMock(return_value=None)
        return client, context

    def test_happy_path_ask(self) -> None:
        client, context = self._async_client()
        client.post = mock.AsyncMock(return_value=self._response({"run_id": "run-ok"}))
        client.get = mock.AsyncMock(
            return_value=self._response({"status": "completed", "output": "Hermes answer"})
        )
        with mock.patch.object(main.httpx, "AsyncClient", return_value=context):
            result = asyncio.run(
                main.HermesClient(self.settings).ask(
                    "Hello", uid="uid-1", idempotency_key="key-1"
                )
            )
            self.assertEqual(result, "Hermes answer")

    def test_non_dict_run_creation_payload_raises_invalid_hermes_response(self) -> None:
        client, context = self._async_client()
        for bad_payload in ("not a dict", ["run-1"], 123, None):
            with self.subTest(payload=bad_payload):
                client.post = mock.AsyncMock(return_value=self._response(bad_payload))
                with (
                    mock.patch.object(main.httpx, "AsyncClient", return_value=context),
                    self.assertRaises(main.BridgeError) as raised,
                ):
                    asyncio.run(
                        main.HermesClient(self.settings).ask(
                            "test", uid="uid-1", idempotency_key="key-bad"
                        )
                    )
                self.assertEqual(raised.exception.status_code, 502)
                self.assertEqual(raised.exception.code, "invalid_hermes_response")

    def test_non_dict_status_polling_payload_raises_invalid_hermes_response(self) -> None:
        client, context = self._async_client()
        for bad_status_payload in ("error text", ["pending"], 42, None):
            with self.subTest(payload=bad_status_payload):
                client.post = mock.AsyncMock(return_value=self._response({"run_id": "run-status"}))
                client.get = mock.AsyncMock(return_value=self._response(bad_status_payload))
                with (
                    mock.patch.object(main.httpx, "AsyncClient", return_value=context),
                    self.assertRaises(main.BridgeError) as raised,
                ):
                    asyncio.run(
                        main.HermesClient(self.settings).ask(
                            "test", uid="uid-1", idempotency_key="key-bad-status"
                        )
                    )
                self.assertEqual(raised.exception.status_code, 502)
                self.assertEqual(raised.exception.code, "invalid_hermes_response")

    def test_empty_output_raises_empty_hermes_response(self) -> None:
        client, context = self._async_client()
        client.post = mock.AsyncMock(return_value=self._response({"run_id": "run-empty"}))
        client.get = mock.AsyncMock(return_value=self._response({"status": "completed", "output": "   "}))
        with (
            mock.patch.object(main.httpx, "AsyncClient", return_value=context),
            self.assertRaises(main.BridgeError) as raised,
        ):
            asyncio.run(
                main.HermesClient(self.settings).ask(
                    "test", uid="uid-1", idempotency_key="key-empty"
                )
            )
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.code, "empty_hermes_response")

    def test_failed_or_cancelled_status_raises_error(self) -> None:
        client, context = self._async_client()
        for status in ("failed", "cancelled"):
            with self.subTest(status=status):
                client.post = mock.AsyncMock(return_value=self._response({"run_id": "run-fail"}))
                client.get = mock.AsyncMock(return_value=self._response({"status": status}))
                with (
                    mock.patch.object(main.httpx, "AsyncClient", return_value=context),
                    self.assertRaises(main.BridgeError) as raised,
                ):
                    asyncio.run(
                        main.HermesClient(self.settings).ask(
                            "test", uid="uid-1", idempotency_key="key-fail"
                        )
                    )
                self.assertEqual(raised.exception.status_code, 502)
                self.assertEqual(raised.exception.code, f"hermes_{status}")

    def test_waiting_for_approval_stops_run_and_returns_approval_required(self) -> None:
        client, context = self._async_client()
        stop_response = self._response({})
        client.post = mock.AsyncMock(
            side_effect=[
                self._response({"run_id": "run-1"}),
                stop_response,
            ]
        )
        client.get = mock.AsyncMock(
            return_value=self._response({"status": "waiting_for_approval"})
        )

        with (
            mock.patch.object(main.httpx, "AsyncClient", return_value=context),
            self.assertRaises(main.BridgeError) as raised,
        ):
            asyncio.run(
                main.HermesClient(self.settings).ask(
                    "send email",
                    uid="uid-1",
                    idempotency_key="omi-call-1",
                )
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.code, "approval_required")
        client.post.assert_awaited_with(
            "http://hermes.test/v1/runs/run-1/stop",
            headers=main.HermesClient(self.settings).headers,
        )
        stop_response.raise_for_status.assert_called_once_with()

    def test_cleanup_timeout_is_reported_as_stop_failed(self) -> None:
        settings = main.Settings(
            hermes_api_url="http://hermes.test",
            hermes_api_key="test-key",
            allowed_uids=frozenset({"uid-1"}),
            allowed_app_ids=frozenset({"app-1"}),
            timeout_seconds=0.01,
            instructions="Test instructions",
        )
        client, context = self._async_client()

        async def post(url: str, **_kwargs: object) -> mock.Mock:
            if url.endswith("/v1/runs"):
                return self._response({"run_id": "run-4"})
            await asyncio.sleep(0.05)
            return self._response({})

        async def slow_status(*_args: object, **_kwargs: object) -> mock.Mock:
            await asyncio.sleep(0.05)
            return self._response({"status": "running"})

        client.post = mock.AsyncMock(side_effect=post)
        client.get = mock.AsyncMock(side_effect=slow_status)

        with (
            mock.patch.object(main.httpx, "AsyncClient", return_value=context),
            mock.patch.object(main, "STOP_TIMEOUT_SECONDS", 0.01),
            self.assertRaises(main.BridgeError) as raised,
        ):
            asyncio.run(
                main.HermesClient(settings).ask(
                    "long task",
                    uid="uid-1",
                    idempotency_key="omi-call-4",
                )
            )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.code, "hermes_stop_failed")


class HermesSettingsTests(unittest.TestCase):
    def test_validate_missing_api_key(self) -> None:
        s = main.Settings("http://test", "", frozenset({"u"}), frozenset({"a"}), 10.0, "")
        with self.assertRaises(main.BridgeError) as cm:
            s.validate()
        self.assertEqual(cm.exception.code, "hermes_not_configured")

    def test_validate_missing_allowlists(self) -> None:
        s = main.Settings("http://test", "k", frozenset(), frozenset({"a"}), 10.0, "")
        with self.assertRaises(main.BridgeError) as cm:
            s.validate()
        self.assertEqual(cm.exception.code, "omi_allowlist_not_configured")

    def test_validate_invalid_timeout(self) -> None:
        s = main.Settings("http://test", "k", frozenset({"u"}), frozenset({"a"}), 0.0, "")
        with self.assertRaises(main.BridgeError) as cm:
            s.validate()
        self.assertEqual(cm.exception.code, "invalid_timeout")


class HermesOmiBridgeEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = mock.patch.dict(
            main.os.environ,
            {
                "HERMES_API_KEY": "local-test-key",
                "OMI_ALLOWED_UIDS": "uid-1,uid-2",
                "OMI_ALLOWED_APP_IDS": "app-1",
            },
            clear=False,
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_manifest_declares_ask_hermes(self) -> None:
        manifest = main.tools_manifest()
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 1)
        tool = manifest["tools"][0]
        self.assertEqual(tool["name"], "ask_hermes")
        self.assertEqual(tool["endpoint"], "/tools/ask_hermes")
        self.assertEqual(tool["parameters"]["required"], ["request"])

    def test_root_and_health_endpoints(self) -> None:
        root = main.root()
        self.assertEqual(root["status"], "ready")
        self.assertEqual(root["manifest"], "/.well-known/omi-tools.json")

        health = main.health()
        self.assertEqual(health, {"ok": True})

    def test_allowed_request_is_forwarded(self) -> None:
        req = FakeRequest(
            json_data={
                "uid": "uid-1",
                "app_id": "app-1",
                "tool_name": "ask_hermes",
                "request": "What changed?",
            },
            headers={"X-Omi-Idempotency-Key": "omi-call-1"},
        )
        with mock.patch.object(
            main.HermesClient, "ask", new_callable=mock.AsyncMock, return_value="Hermes answer"
        ) as ask_mock:
            resp = asyncio.run(main.ask_hermes(req))
            self.assertEqual(resp, {"result": "Hermes answer"})
            ask_mock.assert_awaited_once_with(
                "What changed?", uid="uid-1", idempotency_key="omi-call-1"
            )

    def test_wrong_uid_is_rejected_with_403(self) -> None:
        req = FakeRequest(
            json_data={
                "uid": "attacker",
                "app_id": "app-1",
                "tool_name": "ask_hermes",
                "request": "hello",
            }
        )
        with self.assertRaises(main.HTTPException) as cm:
            asyncio.run(main.ask_hermes(req))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(cm.exception.detail, "uid_not_allowed")

    def test_wrong_app_id_is_rejected_with_403(self) -> None:
        req = FakeRequest(
            json_data={
                "uid": "uid-1",
                "app_id": "rogue-app",
                "tool_name": "ask_hermes",
                "request": "hello",
            }
        )
        with self.assertRaises(main.HTTPException) as cm:
            asyncio.run(main.ask_hermes(req))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(cm.exception.detail, "app_not_allowed")

    def test_invalid_json_payload_rejected_with_400(self) -> None:
        for bad in (ValueError("malformed json"), "string", [1, 2], None):
            with self.subTest(bad=bad):
                req = FakeRequest(json_data=bad)
                with self.assertRaises(main.HTTPException) as cm:
                    asyncio.run(main.ask_hermes(req))
                self.assertEqual(cm.exception.status_code, 400)
                self.assertEqual(cm.exception.detail, "invalid_json")

    def test_invalid_tool_name_rejected_with_400(self) -> None:
        req = FakeRequest(
            json_data={
                "uid": "uid-1",
                "app_id": "app-1",
                "tool_name": "other_tool",
                "request": "hello",
            }
        )
        with self.assertRaises(main.HTTPException) as cm:
            asyncio.run(main.ask_hermes(req))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.detail, "invalid_tool_name")

    def test_empty_or_too_long_request_rejected_with_400(self) -> None:
        for bad_req in ("", "   ", "a" * 2001):
            with self.subTest(bad_req=bad_req[:10]):
                req = FakeRequest(
                    json_data={
                        "uid": "uid-1",
                        "app_id": "app-1",
                        "request": bad_req,
                    }
                )
                with self.assertRaises(main.HTTPException) as cm:
                    asyncio.run(main.ask_hermes(req))
                self.assertEqual(cm.exception.status_code, 400)
                self.assertEqual(cm.exception.detail, "invalid_request")

    def test_missing_allowlist_fails_closed(self) -> None:
        with mock.patch.dict(
            main.os.environ, {"OMI_ALLOWED_UIDS": "", "OMI_ALLOWED_APP_IDS": ""}, clear=False
        ):
            req = FakeRequest(
                json_data={"uid": "uid-1", "app_id": "app-1", "request": "hello"}
            )
            with self.assertRaises(main.HTTPException) as cm:
                asyncio.run(main.ask_hermes(req))
            self.assertEqual(cm.exception.status_code, 503)
            self.assertEqual(cm.exception.detail, "omi_allowlist_not_configured")

    def test_approval_required_returns_clean_error(self) -> None:
        req = FakeRequest(
            json_data={
                "uid": "uid-1",
                "app_id": "app-1",
                "request": "send email",
            }
        )
        with mock.patch.object(
            main.HermesClient,
            "ask",
            new_callable=mock.AsyncMock,
            side_effect=main.BridgeError(409, "approval_required"),
        ):
            resp = asyncio.run(main.ask_hermes(req))
            self.assertIn("error", resp)
            self.assertIn("requires confirmation", resp["error"])


if __name__ == "__main__":
    unittest.main()
