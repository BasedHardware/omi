#!/usr/bin/env python3
"""Hermetic HTTP coverage for the desktop-backend compatibility verifier."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT = Path(__file__).with_name("verify_desktop_backend_compatibility.py")
GOOD_HEALTH = {
    "status": "healthy",
    "service": "omi-desktop-backend",
    "chat_contract_version": "1",
}


class _HealthFixture:
    def __init__(self, payload: object) -> None:
        response_body = json.dumps(payload).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
                if self.path != "/health":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


class DesktopBackendCompatibilityVerifierTests(unittest.TestCase):
    def run_verifier(self, payload: object) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        with tempfile.TemporaryDirectory() as directory, _HealthFixture(payload) as base_url:
            evidence = Path(directory) / "compatibility.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--base-url",
                    base_url,
                    "--expected-contract-version",
                    "1",
                    "--evidence",
                    str(evidence),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            parsed = json.loads(evidence.read_text(encoding="utf-8")) if evidence.is_file() else None
            return completed, parsed

    def test_exact_compatible_health_response_passes(self) -> None:
        completed, evidence = self.run_verifier(GOOD_HEALTH)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            evidence,
            {
                "chat_contract_version": "1",
                "schema_version": 1,
                "service": "omi-desktop-backend",
                "status": "healthy",
            },
        )

    def test_missing_or_wrong_contract_version_fails(self) -> None:
        for name, payload in (
            ("missing", {key: value for key, value in GOOD_HEALTH.items() if key != "chat_contract_version"}),
            ("wrong", {**GOOD_HEALTH, "chat_contract_version": "2"}),
        ):
            with self.subTest(name=name):
                completed, evidence = self.run_verifier(payload)

                self.assertNotEqual(completed.returncode, 0)
                self.assertIsNone(evidence)
                self.assertIn("chat_contract_version", completed.stderr)
                self.assertIn("expected", completed.stderr)

    def test_diagnostics_do_not_echo_arbitrary_health_values(self) -> None:
        secret = "sensitive response detail with spaces"
        completed, evidence = self.run_verifier({**GOOD_HEALTH, "service": secret})

        self.assertNotEqual(completed.returncode, 0)
        self.assertIsNone(evidence)
        self.assertIn("service", completed.stderr)
        self.assertIn("<redacted", completed.stderr)
        self.assertNotIn(secret, completed.stderr)


if __name__ == "__main__":
    unittest.main()
