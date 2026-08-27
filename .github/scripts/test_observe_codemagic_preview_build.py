#!/usr/bin/env python3
"""Behavioral tests for the Codemagic preview-build observer."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).with_name("observe-codemagic-preview-build.py")
WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "desktop_publish_preview.yml"
SPEC = importlib.util.spec_from_file_location("observe_codemagic_preview_build", SCRIPT)
assert SPEC and SPEC.loader
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)

APP_ID = "66c95e6ec76853c447b8bcbb"
BUILD_ID = "build-preview-123"
SLUG = "v5"
SHA = "a" * 40


def build(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "buildId": BUILD_ID,
        "workflowId": observer.CANONICAL_WORKFLOW,
        "status": "building",
        "environment": {
            "variables": {
                "PREVIEW_SLUG": SLUG,
                "PREVIEW_SOURCE_SHA": SHA,
            }
        },
    }
    payload.update(overrides)
    return payload


class CodemagicPreviewBuildObserverTests(unittest.TestCase):
    def observe(
        self,
        builds: list[dict[str, object]],
        *,
        timeout_seconds: int = 0,
        poll_seconds: int = 1,
    ) -> tuple[int, dict[str, object]]:
        cursor = {"index": 0}

        def fetch(**_kwargs: object) -> dict[str, object]:
            index = min(cursor["index"], len(builds) - 1)
            cursor["index"] += 1
            return builds[index]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observation.json"
            result = observer.observe(
                app_id=APP_ID,
                build_id=BUILD_ID,
                preview_slug=SLUG,
                source_sha=SHA,
                api_token="test-token",
                timeout_seconds=timeout_seconds,
                poll_seconds=poll_seconds,
                output=output,
                fetch=fetch,
            )
            return result, json.loads(output.read_text(encoding="utf-8"))

    def test_finished_preview_build_passes(self) -> None:
        result, evidence = self.observe([build(status="finished")])

        self.assertEqual(result, 0)
        self.assertEqual(evidence["status"], "finished")
        self.assertEqual(evidence["codemagic_status"], "finished")
        self.assertEqual(evidence["preview_slug"], SLUG)
        self.assertEqual(evidence["source_sha"], SHA)

    def test_failed_preview_build_fails_closed(self) -> None:
        result, evidence = self.observe([build(status="failed")])

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "failed")
        self.assertIn("terminal status 'failed'", evidence["error"])

    def test_canceled_preview_build_fails_closed(self) -> None:
        result, evidence = self.observe([build(status="canceled")])

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "failed")

    def test_wrong_workflow_fails_closed(self) -> None:
        result, evidence = self.observe([build(workflowId="omi-desktop-swift-release", status="finished")])

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "identity_mismatch")
        self.assertIn("omi-desktop-swift-release", evidence["error"])

    def test_slug_mismatch_fails_closed(self) -> None:
        result, evidence = self.observe(
            [
                build(
                    status="finished",
                    environment={"variables": {"PREVIEW_SLUG": "other", "PREVIEW_SOURCE_SHA": SHA}},
                )
            ]
        )

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "identity_mismatch")
        self.assertIn("PREVIEW_SLUG", evidence["error"])

    def test_in_progress_build_times_out_with_evidence(self) -> None:
        result, evidence = self.observe([build(status="building")], timeout_seconds=0)

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "timeout")
        self.assertIn("terminal status", evidence["error"])

    def test_missing_token_is_recorded_without_requesting_a_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observation.json"
            fetch = MagicMock()
            result = observer.observe(
                app_id=APP_ID,
                build_id=BUILD_ID,
                preview_slug=SLUG,
                source_sha=SHA,
                api_token="",
                timeout_seconds=0,
                poll_seconds=1,
                output=output,
                fetch=fetch,
            )
            evidence = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "unobservable")
        fetch.assert_not_called()

    def test_fetch_uses_get_for_the_exact_build_id(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.object(observer.urllib.request, "urlopen", return_value=response) as urlopen, patch.object(
            observer.json, "load", return_value={"build": build(status="queued")}
        ):
            self.assertEqual(
                observer.fetch_build(build_id=BUILD_ID, api_token="test-token")["status"],
                "queued",
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.endswith(f"/builds/{BUILD_ID}"))
        self.assertEqual(request.get_header("X-auth-token"), "test-token")

    def test_dispatcher_wires_observer_and_evidence_retention(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("observe-codemagic-preview-build.py", text)
        self.assertIn("Observe Codemagic preview build to a terminal status", text)
        self.assertIn("Retain Codemagic preview build observation evidence", text)
        self.assertIn("codemagic-preview-build-observation-", text)
        self.assertIn('[[ "$build_id" =~ ^[A-Za-z0-9_-]+$ ]]', text)
        self.assertIn('echo "build_id=$build_id" >> "$GITHUB_OUTPUT"', text)
        self.assertIn("CODEMAGIC_BUILD_ID:", text)
        self.assertIn('--build-id "$CODEMAGIC_BUILD_ID"', text)
        self.assertNotIn('--build-id "${{ steps.dispatch.outputs.build_id }}"', text)


if __name__ == "__main__":
    unittest.main()
