from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

_SPEC = importlib.util.spec_from_file_location(
    "omi_hermes_main", Path(__file__).with_name("main.py")
)
assert _SPEC is not None and _SPEC.loader is not None
main = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = main
_SPEC.loader.exec_module(main)


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
            mock.patch.object(
                main.httpx,
                "Client",
                side_effect=AssertionError("synchronous client used"),
            ),
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

    def test_timeout_is_end_to_end_and_stops_in_progress_run(self) -> None:
        settings = main.Settings(
            hermes_api_url="http://hermes.test",
            hermes_api_key="test-key",
            allowed_uids=frozenset({"uid-1"}),
            allowed_app_ids=frozenset({"app-1"}),
            timeout_seconds=0.01,
            instructions="Test instructions",
        )
        client, context = self._async_client()
        stop_response = self._response({})
        client.post = mock.AsyncMock(
            side_effect=[
                self._response({"run_id": "run-2"}),
                stop_response,
            ]
        )

        async def slow_status(*_args: object, **_kwargs: object) -> mock.Mock:
            await asyncio.sleep(0.05)
            return self._response({"status": "running"})

        client.get = mock.AsyncMock(side_effect=slow_status)

        started = time.perf_counter()
        with (
            mock.patch.object(main.httpx, "AsyncClient", return_value=context),
            mock.patch.object(
                main.httpx,
                "Client",
                side_effect=AssertionError("synchronous client used"),
            ),
            self.assertRaises(main.BridgeError) as raised,
        ):
            asyncio.run(
                main.HermesClient(settings).ask(
                    "long task",
                    uid="uid-1",
                    idempotency_key="omi-call-2",
                )
            )
        elapsed = time.perf_counter() - started

        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(raised.exception.code, "hermes_timeout")
        self.assertLess(elapsed, 0.25)
        client.post.assert_awaited_with(
            "http://hermes.test/v1/runs/run-2/stop",
            headers=main.HermesClient(settings).headers,
        )
        stop_response.raise_for_status.assert_called_once_with()

    def test_rejected_approval_stop_is_reported_as_unavailable(self) -> None:
        client, context = self._async_client()
        stop_response = self._response({})
        stop_response.raise_for_status.side_effect = main.httpx.HTTPStatusError(
            "stop rejected",
            request=main.httpx.Request("POST", "http://hermes.test/v1/runs/run-3/stop"),
            response=main.httpx.Response(500),
        )
        client.post = mock.AsyncMock(
            side_effect=[
                self._response({"run_id": "run-3"}),
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
                    idempotency_key="omi-call-3",
                )
            )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.code, "hermes_unavailable")

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


class HermesOmiBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.env = mock.patch.dict(
            os.environ,
            {
                "HERMES_API_KEY": "local-test-key",
                "OMI_ALLOWED_UIDS": "uid-1",
                "OMI_ALLOWED_APP_IDS": "app-1",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_manifest_declares_ask_hermes(self) -> None:
        response = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(response.status_code, 200)
        tool = response.json()["tools"][0]
        self.assertEqual(tool["name"], "ask_hermes")
        self.assertEqual(tool["endpoint"], "/tools/ask_hermes")
        self.assertEqual(tool["parameters"]["required"], ["request"])

    @mock.patch.object(
        main.HermesClient,
        "ask",
        new_callable=mock.AsyncMock,
        return_value="Hermes answer",
    )
    def test_allowed_request_is_forwarded(self, ask: mock.AsyncMock) -> None:
        response = self.client.post(
            "/tools/ask_hermes",
            json={
                "uid": "uid-1",
                "app_id": "app-1",
                "tool_name": "ask_hermes",
                "request": "What changed?",
            },
            headers={"X-Omi-Idempotency-Key": "omi-call-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"result": "Hermes answer"})
        ask.assert_awaited_once_with(
            "What changed?", uid="uid-1", idempotency_key="omi-call-1"
        )

    @mock.patch.object(main.HermesClient, "ask", new_callable=mock.AsyncMock)
    def test_wrong_uid_is_rejected_before_hermes(self, ask: mock.AsyncMock) -> None:
        response = self.client.post(
            "/tools/ask_hermes",
            json={
                "uid": "attacker",
                "app_id": "app-1",
                "tool_name": "ask_hermes",
                "request": "hello",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "uid_not_allowed")
        ask.assert_not_awaited()

    @mock.patch.object(main.HermesClient, "ask", new_callable=mock.AsyncMock)
    def test_missing_allowlist_fails_closed(self, ask: mock.AsyncMock) -> None:
        with mock.patch.dict(
            os.environ, {"OMI_ALLOWED_UIDS": "", "OMI_ALLOWED_APP_IDS": ""}, clear=False
        ):
            response = self.client.post(
                "/tools/ask_hermes",
                json={"uid": "uid-1", "app_id": "app-1", "request": "hello"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "omi_allowlist_not_configured")
        ask.assert_not_awaited()

    @mock.patch.object(
        main.HermesClient,
        "ask",
        new_callable=mock.AsyncMock,
        side_effect=main.BridgeError(409, "approval_required"),
    )
    def test_approval_is_not_granted(self, _ask: mock.AsyncMock) -> None:
        response = self.client.post(
            "/tools/ask_hermes",
            json={
                "uid": "uid-1",
                "app_id": "app-1",
                "tool_name": "ask_hermes",
                "request": "send email",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("requires confirmation", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
