#!/usr/bin/env python3
"""Behavioral tests for bounded native Codemagic intake and one fallback fence."""

from __future__ import annotations

import importlib.util
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


def build(
    *,
    build_id: str = "build-1",
    tag: str = TAG,
    workflow_id: str = WORKFLOW_ID,
    source_sha: str | None = SOURCE_SHA,
    file_workflow_id: bool = False,
) -> dict[str, object]:
    record: dict[str, object] = {
        "_id": build_id,
        "tag": tag,
        "status": "initializing",
        "createdAt": "2026-07-26T20:08:49Z",
    }
    record["fileWorkflowId" if file_workflow_id else "workflowId"] = workflow_id
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
    def test_file_workflow_id_from_real_build_api_is_canonical(self) -> None:
        decision = intake.classify_builds(
            [build(file_workflow_id=True)],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "canonical_build_observed")
        self.assertEqual(decision["exact_tag_build_count"], 1)
        self.assertEqual(decision["exact_workflow_build_count"], 1)

    def test_exact_immutable_tag_is_enough_when_api_omits_commit_sha(self) -> None:
        decision = intake.classify_builds(
            [build(source_sha=None)],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "canonical_build_observed")
        self.assertIn("immutable tag remains the source identity", decision["message"])

    def test_wrong_workflow_blocks_fallback_instead_of_ignoring_same_tag_build(self) -> None:
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

    def test_duplicate_same_tag_builds_reject_fallback(self) -> None:
        decision = intake.classify_builds(
            [build(), build(build_id="build-2")],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "duplicate_same_tag_build")
        self.assertEqual(decision["exact_workflow_build_count"], 2)

    def test_mixed_workflow_same_tag_builds_also_reject_fallback(self) -> None:
        decision = intake.classify_builds(
            [build(), build(build_id="other-build", workflow_id="other-workflow")],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(decision["status"], "duplicate_same_tag_build")
        self.assertEqual(decision["exact_tag_build_count"], 2)

    def test_native_wait_consumes_full_budget_before_absence_proof(self) -> None:
        clock = FakeClock()
        result = intake.poll_for_intake(
            fetch=lambda: [],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
            timeout_seconds=600,
            poll_seconds=15,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertEqual(result["decision"]["status"], "native_intake_absent")
        self.assertEqual(result["elapsed_seconds"], 600.0)
        self.assertEqual(len(clock.sleeps), 40)
        self.assertEqual(clock.sleeps[-1], 15.0)

    def test_native_wait_stops_once_any_same_tag_state_is_observed(self) -> None:
        clock = FakeClock()
        result = intake.poll_for_intake(
            fetch=lambda: [build(workflow_id="wrong-workflow")],
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
            timeout_seconds=600,
            poll_seconds=15,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertEqual(result["decision"]["status"], "workflow_selector_mismatch")
        self.assertEqual(clock.sleeps, [])

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

    def test_fallback_posts_once_after_final_all_state_absence_fence(self) -> None:
        reads = iter([[], [build(build_id="fallback-1")]])
        dispatch = Mock(return_value="fallback-1")
        fetch_one = Mock(return_value=build(build_id="fallback-1", file_workflow_id=True))

        result = intake.dispatch_fallback_after_absence(
            fetch=lambda: next(reads),
            dispatch=dispatch,
            fetch_one=fetch_one,
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(result["outcome"], "fallback_dispatched_and_verified")
        self.assertEqual(result["dispatch_count"], 1)
        dispatch.assert_called_once_with()
        fetch_one.assert_called_once_with("fallback-1")
        self.assertEqual(result["final_query"]["exact_tag_build_count"], 1)

    def test_fallback_waits_for_post_dispatch_visibility_without_a_second_post(self) -> None:
        clock = FakeClock()
        reads = iter([[], [], [build(build_id="fallback-1")]])
        dispatch = Mock(return_value="fallback-1")
        fetch_one = Mock(return_value=build(build_id="fallback-1", file_workflow_id=True))

        result = intake.dispatch_fallback_after_absence(
            fetch=lambda: next(reads),
            dispatch=dispatch,
            fetch_one=fetch_one,
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
            visibility_timeout_seconds=120,
            visibility_poll_seconds=5,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertEqual(result["outcome"], "fallback_dispatched_and_verified")
        self.assertEqual(result["dispatch_count"], 1)
        dispatch.assert_called_once_with()
        self.assertEqual(clock.sleeps, [5.0])
        visibility = result["post_dispatch_visibility"]
        self.assertEqual(visibility["attempts"], 2)
        self.assertEqual(visibility["decision"]["status"], "canonical_build_observed")

    def test_active_canonical_build_in_final_fence_prevents_post(self) -> None:
        dispatch = Mock(return_value="never")
        result = intake.dispatch_fallback_after_absence(
            fetch=lambda: [build(build_id="native-active")],
            dispatch=dispatch,
            fetch_one=Mock(),
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(result["outcome"], "canonical_build_observed_before_fallback")
        self.assertEqual(result["dispatch_count"], 0)
        dispatch.assert_not_called()

    def test_ambiguous_post_is_not_retried_when_final_query_has_one_canonical_build(self) -> None:
        dispatch = Mock(side_effect=intake.ProviderApiError("transport closed"))
        result = intake.dispatch_fallback_after_absence(
            fetch=Mock(side_effect=[[], [build(build_id="fallback-1")]]),
            dispatch=dispatch,
            fetch_one=Mock(),
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(result["outcome"], "fallback_dispatch_ambiguous_but_canonical_build_observed")
        self.assertEqual(result["dispatch_count"], 1)
        dispatch.assert_called_once_with()

    def test_final_query_rejects_duplicate_build_even_after_a_successful_post(self) -> None:
        result = intake.dispatch_fallback_after_absence(
            fetch=Mock(side_effect=[[], [build(build_id="fallback-1"), build(build_id="duplicate-2")]]),
            dispatch=Mock(return_value="fallback-1"),
            fetch_one=Mock(),
            release_tag=TAG,
            workflow_id=WORKFLOW_ID,
            source_sha=SOURCE_SHA,
        )

        self.assertEqual(result["outcome"], "fallback_final_query_rejected")
        self.assertEqual(result["final_query"]["status"], "duplicate_same_tag_build")

    def test_provider_calls_follow_all_same_tag_pages_then_post_tag_bound_payload(self) -> None:
        opener = Mock(
            side_effect=[
                FakeResponse({"builds": [build(build_id="page-1")], "nextPageUrl": "/builds?cursor=next"}),
                FakeResponse({"builds": [build(build_id="page-2")]}),
                FakeResponse({"buildId": "fallback-1"}),
            ]
        )
        builds = intake.fetch_builds(app_id=APP_ID, release_tag=TAG, api_token="secret", opener=opener)
        returned = intake.request_fallback_build(
            app_id=APP_ID,
            workflow_id=WORKFLOW_ID,
            release_tag=TAG,
            api_token="secret",
            opener=opener,
        )

        self.assertEqual(builds, [build(build_id="page-1"), build(build_id="page-2")])
        self.assertEqual(returned, "fallback-1")
        get_request, page_request, post_request = [call.args[0] for call in opener.call_args_list]
        self.assertEqual(get_request.method, "GET")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(get_request.full_url).query)
        self.assertEqual(query["appId"], [APP_ID])
        self.assertEqual(query["tag"], [TAG])
        self.assertEqual(page_request.method, "GET")
        self.assertEqual(urllib.parse.urlparse(page_request.full_url).path, "/builds")
        self.assertEqual(post_request.method, "POST")
        self.assertEqual(json.loads(post_request.data.decode()), {"appId": APP_ID, "workflowId": WORKFLOW_ID, "tag": TAG})

    def test_checked_in_workflow_keeps_native_wait_then_enables_only_fenced_fallback(self) -> None:
        workflow = (ROOT / ".github/workflows/desktop_auto_release.yml").read_text(encoding="utf-8")
        codemagic = (ROOT / "codemagic.yaml").read_text(encoding="utf-8")

        for fragment in (
            "Verify native Codemagic tag intake or dispatch fenced fallback",
            "CODEMAGIC_API_TOKEN: ${{ secrets.CODEMAGIC_API_TOKEN }}",
            "check-codemagic-tag-intake.py",
            '--workflow-id "omi-desktop-swift-release"',
            "--timeout-seconds 600",
            "--dispatch-fallback-on-absence",
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
