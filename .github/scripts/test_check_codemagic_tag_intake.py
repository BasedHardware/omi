#!/usr/bin/env python3
"""Behavioral tests for bounded native Codemagic tag-intake evidence."""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import Mock

SCRIPT = Path(__file__).with_name("check-codemagic-tag-intake.py")
SPEC = importlib.util.spec_from_file_location("check_codemagic_tag_intake", SCRIPT)
assert SPEC and SPEC.loader
intake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(intake)

ROOT = Path(__file__).resolve().parents[2]
APP_ID = "66c95e6ec76853c447b8bcbb"
WORKFLOW_ID = "omi-desktop-swift-release"
TAG = "v1.2.3+10203-macos"
SOURCE_SHA = "a" * 40


def build(*, tag: str = TAG, workflow_id: str = WORKFLOW_ID, source_sha: str | None = SOURCE_SHA):
    record = {
        "_id": "build-1",
        "tag": tag,
        "workflowId": workflow_id,
        "status": "queued",
        "createdAt": "2026-07-26T20:08:49Z",
    }
    if source_sha is not None:
        record["commit"] = {"hash": source_sha}
    return record


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class CodemagicTagIntakeTests(unittest.TestCase):
    def test_exact_tag_workflow_and_source_confirm_intake(self) -> None:
        decision = intake.classify_builds(
            [build()],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "intake_confirmed")
        self.assertEqual(decision["exact_tag_build_count"], 1)
        self.assertEqual(decision["exact_workflow_build_count"], 1)

    def test_exact_immutable_tag_is_enough_when_api_omits_commit_sha(self) -> None:
        decision = intake.classify_builds(
            [build(source_sha=None)],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "intake_confirmed")
        self.assertIn("immutable tag remains the source identity", decision["message"])

    def test_wrong_workflow_is_distinct_from_missing_native_intake(self) -> None:
        decision = intake.classify_builds(
            [build(workflow_id="macos-prod-legacy-no-publish")],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "workflow_selector_mismatch")
        self.assertIn("macos-prod-legacy-no-publish", decision["observed_workflows"])

    def test_wrong_reported_source_fails_identity(self) -> None:
        decision = intake.classify_builds(
            [build(source_sha="b" * 40)],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "source_identity_mismatch")
        self.assertIn("b" * 40, decision["message"])

    def test_duplicate_native_builds_fail_exactly_once_contract(self) -> None:
        duplicate = build()
        duplicate["_id"] = "build-2"
        decision = intake.classify_builds(
            [build(), duplicate],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "duplicate_native_intake")
        self.assertEqual(decision["exact_workflow_build_count"], 2)

    def test_poll_is_bounded_and_stops_when_intake_appears(self) -> None:
        responses = iter([[], [], [build()]])
        clock = FakeClock()

        result = intake.poll_for_intake(
            fetch=lambda: next(responses),
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
            timeout_seconds=600,
            poll_seconds=15,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertEqual(result["decision"]["status"], "intake_confirmed")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(clock.sleeps, [15.0, 15.0])

    def test_api_failure_is_not_misreported_as_missing_intake(self) -> None:
        result = intake.poll_for_intake(
            fetch=lambda: (_ for _ in ()).throw(
                intake.ProviderApiError("Codemagic builds query returned HTTP 401", retryable=False)
            ),
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
            timeout_seconds=600,
            poll_seconds=15,
        )

        self.assertEqual(result["decision"]["status"], "provider_api_unavailable")
        self.assertEqual(result["attempts"], 1)
        self.assertIn("cannot be distinguished", result["decision"]["message"])

    def test_provider_query_is_read_only_and_exact_tag_scoped(self) -> None:
        opener = Mock(return_value=FakeResponse({"builds": [build()]}))

        builds = intake.fetch_builds(
            app_id=APP_ID,
            release_tag=TAG,
            api_token="secret",
            opener=opener,
        )

        self.assertEqual(builds, [build()])
        request = opener.call_args.args[0]
        self.assertEqual(request.method, "GET")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(query["appId"], [APP_ID])
        self.assertEqual(query["tag"], [TAG])

    def test_checked_in_workflow_binds_assertion_to_native_contract(self) -> None:
        workflow = (ROOT / ".github/workflows/desktop_auto_release.yml").read_text(encoding="utf-8")
        codemagic = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")

        for fragment in (
            "Assert native Codemagic tag intake",
            "CODEMAGIC_API_TOKEN: ${{ secrets.CODEMAGIC_API_TOKEN }}",
            "check-codemagic-tag-intake.py",
            '--workflow-id "omi-desktop-swift-release"',
            "--timeout-seconds 600",
            "Retain native Codemagic tag intake evidence",
        ):
            self.assertIn(fragment, workflow)
        self.assertIn(
            '        - pattern: "v*-macos"\n          include: true',
            codemagic.split("  omi-desktop-swift-release:", 1)[1],
        )
        self.assertNotIn(intake.BUILDS_API, workflow)


if __name__ == "__main__":
    unittest.main()
