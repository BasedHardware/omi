#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).with_name("desktop_backend_candidate_probe.py")
SPEC = importlib.util.spec_from_file_location("desktop_backend_candidate_probe", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)

SHA = "7fd2aac1f5e1d6c12a8c7b641e6fb532e2324e6c"


def sse_event(payload: object) -> bytes:
    return f"data: {json.dumps(payload)}\n".encode()


class CandidateProbeTests(unittest.TestCase):
    def test_compatibility_requires_live_service_contract(self) -> None:
        summary = PROBE.validate_compatibility(
            {
                "status": "healthy",
                "service": "omi-desktop-backend",
                "chat_contract_version": "1",
            },
            expected_contract_version="1",
        )
        self.assertEqual(summary["chat_contract_version"], "1")

        with self.assertRaises(PROBE.ProbeError):
            PROBE.validate_compatibility(
                {
                    "status": "healthy",
                    "service": "omi-desktop-backend",
                    "chat_contract_version": "2",
                },
                expected_contract_version="1",
            )

    def test_health_requires_backend_identity_and_contract(self) -> None:
        summary = PROBE.validate_health(
            {
                "status": "healthy",
                "service": "omi-desktop-backend",
                "backend_release_sha": SHA,
                "backend_release_channel": "development",
                "chat_contract_version": "1",
                "release_tag": "legacy-value-is-not-the-backend-vector",
            },
            expected_sha=SHA,
            expected_channel="development",
            expected_contract_version="1",
        )
        self.assertEqual(summary["backend_release_sha"], SHA)

    def test_health_rejects_stale_or_unversioned_candidate(self) -> None:
        for mutation in (
            {"backend_release_sha": "0" * 40},
            {"chat_contract_version": None},
        ):
            payload = {
                "status": "healthy",
                "service": "omi-desktop-backend",
                "backend_release_sha": SHA,
                "backend_release_channel": "production",
                "chat_contract_version": "1",
                **mutation,
            }
            with self.assertRaises(PROBE.ProbeError):
                PROBE.validate_health(
                    payload,
                    expected_sha=SHA,
                    expected_channel="production",
                    expected_contract_version="1",
                )

    def test_readiness_requires_redis(self) -> None:
        self.assertEqual(
            PROBE.validate_readiness({"status": "ready", "redis": {"status": "ready"}}),
            {"status": "ready", "redis": "ready"},
        )
        with self.assertRaises(PROBE.ProbeError):
            PROBE.validate_readiness(
                {"status": "not_ready", "redis": {"status": "unavailable"}}
            )

    def test_health_only_evidence_excludes_chat_claims(self) -> None:
        original = PROBE._request_json
        try:
            PROBE._request_json = lambda _url: {
                "status": "healthy",
                "service": "omi-desktop-backend",
                "backend_release_sha": SHA,
                "backend_release_channel": "production",
                "chat_contract_version": "1",
            }
            evidence = PROBE.probe_health_only(
                base_url="https://candidate.example",
                expected_sha=SHA,
                expected_channel="production",
                expected_contract_version="1",
            )
        finally:
            PROBE._request_json = original
        self.assertEqual(evidence["status"], "passed")
        self.assertNotIn("chat", evidence)

    def test_compatibility_only_does_not_require_release_identity(self) -> None:
        original = PROBE._request_json
        try:
            PROBE._request_json = lambda _url: {
                "status": "healthy",
                "service": "omi-desktop-backend",
                "chat_contract_version": "1",
            }
            evidence = PROBE.probe_compatibility_only(
                base_url="https://production.example",
                expected_contract_version="1",
            )
        finally:
            PROBE._request_json = original
        self.assertEqual(evidence["desktop_backend"]["chat_contract_version"], "1")
        self.assertNotIn("backend_release_sha", evidence["desktop_backend"])

    def test_sse_parser_requires_text_and_terminal_marker(self) -> None:
        answer, done, searches, _, saw_usage = PROBE.parse_sse(
            [
                sse_event({"choices": [{"delta": {"content": "hello"}}]}),
                sse_event({"choices": [], "usage": {"web_search_requests": 1}}),
                b"data: [DONE]\n",
            ],
            stage="chat",
        )
        self.assertEqual(answer, "hello")
        self.assertTrue(done)
        self.assertEqual(searches, 1)
        self.assertTrue(saw_usage)

        with self.assertRaisesRegex(PROBE.ProbeError, "without \\[DONE\\]"):
            PROBE.parse_sse(
                [sse_event({"choices": [{"delta": {"content": "partial"}}]})],
                stage="chat",
            )

    def test_sse_parser_rejects_upstream_errors_without_echoing_payload(self) -> None:
        with self.assertRaisesRegex(PROBE.ProbeError, "invalid_request_error"):
            PROBE.parse_sse(
                [
                    sse_event(
                        {
                            "error": {
                                "type": "invalid_request_error",
                                "message": "sensitive upstream detail",
                            }
                        }
                    )
                ],
                stage="public_web_turn",
            )

    def test_sse_parser_rejects_invalid_web_search_usage(self) -> None:
        with self.assertRaisesRegex(PROBE.ProbeError, "invalid web search usage"):
            PROBE.parse_sse(
                [
                    sse_event({"choices": [{"delta": {"content": "answer"}}]}),
                    sse_event({"choices": [], "usage": {"web_search_requests": -1}}),
                    b"data: [DONE]\n",
                ],
                stage="public_web_turn",
            )

    def test_token_file_must_be_regular_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("abc.def.ghi", encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(PROBE._valid_token(path), "abc.def.ghi")
            path.chmod(0o644)
            with self.assertRaisesRegex(PROBE.ProbeError, "mode-0600"):
                PROBE._valid_token(path)

    def test_full_cli_forwards_candidate_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "token"
            token.write_text("abc.def.ghi", encoding="utf-8")
            token.chmod(0o600)
            evidence = root / "evidence.json"
            argv = [
                str(SCRIPT),
                "--base-url=https://candidate.example",
                f"--bearer-token-file={token}",
                f"--expected-release-sha={SHA}",
                "--expected-release-channel=production",
                "--expected-contract-version=1",
                "--expected-revision=desktop-backend-abc",
                f"--expected-image-digest=sha256:{'a' * 64}",
                "--candidate-tag=desktop-prod-candidate",
                "--workflow-run-id=123",
                f"--evidence-path={evidence}",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                PROBE,
                "probe_candidate",
                return_value={"status": "passed"},
            ) as candidate:
                self.assertEqual(PROBE.main(), 0)
            self.assertEqual(candidate.call_args.kwargs["expected_revision"], "desktop-backend-abc")
            self.assertEqual(candidate.call_args.kwargs["workflow_run_id"], "123")

    def test_health_only_cli_does_not_forward_candidate_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "health.json"
            argv = [
                str(SCRIPT),
                "--health-only",
                "--base-url=https://serving.example",
                f"--expected-release-sha={SHA}",
                "--expected-release-channel=development",
                "--expected-contract-version=1",
                f"--evidence-path={evidence}",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                PROBE,
                "probe_health_only",
                return_value={"status": "passed"},
            ) as health:
                self.assertEqual(PROBE.main(), 0)
            self.assertEqual(
                set(health.call_args.kwargs),
                {"base_url", "expected_sha", "expected_channel", "expected_contract_version"},
            )

    def test_candidate_requires_web_then_plain_follow_up(self) -> None:
        health = {
            "status": "healthy",
            "service": "omi-desktop-backend",
            "backend_release_sha": SHA,
            "backend_release_channel": "production",
            "chat_contract_version": "1",
        }
        readiness = {"status": "ready", "redis": {"status": "ready"}}
        chat_results = [
            PROBE.ChatResult("web answer", 1.2, 0.2, True, 1),
            PROBE.ChatResult("plain answer", 0.8, 0.1, True, 0),
        ]
        with mock.patch.object(PROBE, "_request_json", side_effect=[health, readiness]), mock.patch.object(
            PROBE, "_require_firestore_read", return_value={"status": "passed"}
        ), mock.patch.object(PROBE, "_chat_request", side_effect=chat_results) as chat:
            evidence = PROBE.probe_candidate(
                base_url="https://candidate.example",
                token="token",
                expected_sha=SHA,
                expected_channel="production",
                expected_contract_version="1",
                expected_revision="desktop-backend-abc",
                expected_image_digest=f"sha256:{'a' * 64}",
                candidate_tag="desktop-prod-candidate",
                workflow_run_id="123",
            )
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(evidence["chat"]["public_web_turn_web_search_requests"], 1)
        self.assertEqual(evidence["target"]["revision"], "desktop-backend-abc")

    def test_candidate_rejects_model_only_web_answer(self) -> None:
        health = {
            "status": "healthy",
            "service": "omi-desktop-backend",
            "backend_release_sha": SHA,
            "backend_release_channel": "development",
            "chat_contract_version": "1",
        }
        readiness = {"status": "ready", "redis": {"status": "ready"}}
        with mock.patch.object(PROBE, "_request_json", side_effect=[health, readiness]), mock.patch.object(
            PROBE, "_require_firestore_read", return_value={"status": "passed"}
        ), mock.patch.object(
            PROBE,
            "_chat_request",
            return_value=PROBE.ChatResult("hallucinated answer", 0.5, 0.1, True, 0),
        ):
            with self.assertRaisesRegex(PROBE.ProbeError, "did not report a web search"):
                PROBE.probe_candidate(
                    base_url="https://candidate.example",
                    token="token",
                    expected_sha=SHA,
                    expected_channel="development",
                    expected_contract_version="1",
                    expected_revision="desktop-backend-def",
                    expected_image_digest=f"sha256:{'b' * 64}",
                    candidate_tag="desktop-dev-candidate",
                    workflow_run_id="456",
                )


if __name__ == "__main__":
    unittest.main()
