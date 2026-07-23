from __future__ import annotations

import importlib.util
import os
import sys
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

    @mock.patch.object(main.HermesClient, "ask", return_value="Hermes answer")
    def test_allowed_request_is_forwarded(self, ask: mock.Mock) -> None:
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
        ask.assert_called_once_with(
            "What changed?", uid="uid-1", idempotency_key="omi-call-1"
        )

    @mock.patch.object(main.HermesClient, "ask")
    def test_wrong_uid_is_rejected_before_hermes(self, ask: mock.Mock) -> None:
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
        ask.assert_not_called()

    @mock.patch.object(main.HermesClient, "ask")
    def test_missing_allowlist_fails_closed(self, ask: mock.Mock) -> None:
        with mock.patch.dict(
            os.environ, {"OMI_ALLOWED_UIDS": "", "OMI_ALLOWED_APP_IDS": ""}, clear=False
        ):
            response = self.client.post(
                "/tools/ask_hermes",
                json={"uid": "uid-1", "app_id": "app-1", "request": "hello"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "omi_allowlist_not_configured")
        ask.assert_not_called()

    @mock.patch.object(
        main.HermesClient, "ask", side_effect=main.BridgeError(409, "approval_required")
    )
    def test_approval_is_not_granted(self, _ask: mock.Mock) -> None:
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
