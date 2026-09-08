#!/usr/bin/env python3
"""Behavioral tests for the native Codemagic tag-build observer."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).with_name("observe-codemagic-tag-build.py")
SPEC = importlib.util.spec_from_file_location("observe_codemagic_tag_build", SCRIPT)
assert SPEC and SPEC.loader
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)

APP_ID = "66c95e6ec76853c447b8bcbb"
TAG = "v1.2.3+10203-macos"
SHA = "a" * 40


def build(**overrides: object) -> dict[str, object]:
    return {
        "buildId": "build-123",
        "workflowId": observer.CANONICAL_WORKFLOW,
        "tag": TAG,
        "status": "queued",
        **overrides,
    }


class CodemagicTagBuildObserverTests(unittest.TestCase):
    def observe(self, builds: list[dict[str, object]], *, timeout_seconds: int = 0) -> tuple[int, dict[str, object]]:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observation.json"
            result = observer.observe(
                app_id=APP_ID,
                release_tag=TAG,
                candidate_sha=SHA,
                api_token="test-token",
                timeout_seconds=timeout_seconds,
                poll_seconds=1,
                output=output,
                fetch=lambda **_kwargs: builds,
            )
            return result, json.loads(output.read_text(encoding="utf-8"))

    def test_observes_exactly_one_native_tag_build(self) -> None:
        result, evidence = self.observe([build()])

        self.assertEqual(result, 0)
        self.assertEqual(evidence["status"], "observed")
        self.assertEqual(evidence["matching_builds"], [build()])
        self.assertEqual(evidence["candidate_sha"], SHA)

    def test_accepts_api_branch_field_for_the_exact_tag(self) -> None:
        result, evidence = self.observe([build(tag=None, branch=TAG)])

        self.assertEqual(result, 0)
        self.assertEqual(evidence["status"], "observed")

    def test_missing_tag_build_fails_closed_with_durable_evidence(self) -> None:
        result, evidence = self.observe([build(tag="v1.2.2+10202-macos")])

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "missing")
        self.assertEqual(evidence["matching_builds"], [])
        self.assertIn("no Codemagic release build", evidence["error"])

    def test_duplicate_tag_builds_fail_closed(self) -> None:
        result, evidence = self.observe([build(buildId="one"), build(buildId="two")])

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "duplicate")
        self.assertEqual(len(evidence["matching_builds"]), 2)

    def test_wrong_workflow_never_satisfies_the_observation(self) -> None:
        result, evidence = self.observe([build(workflowId="omi-desktop-swift-preview")])

        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "missing")

    def test_missing_token_is_recorded_without_requesting_a_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observation.json"
            fetch = MagicMock()
            result = observer.observe(
                app_id=APP_ID,
                release_tag=TAG,
                candidate_sha=SHA,
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

    def test_fetch_uses_only_a_get_request_with_the_token_header(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.object(observer.urllib.request, "urlopen", return_value=response) as urlopen, patch.object(
            observer.json, "load", return_value={"builds": []}
        ):
            self.assertEqual(observer.fetch_builds(app_id=APP_ID, api_token="test-token"), [])

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn(f"appId={APP_ID}", request.full_url)
        self.assertEqual(request.get_header("X-auth-token"), "test-token")


if __name__ == "__main__":
    unittest.main()
