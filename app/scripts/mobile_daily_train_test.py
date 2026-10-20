#!/usr/bin/env python3
"""Offline contract tests for the daily mobile release train.

The self-driving posture (2026-10-14): iOS submits AFTER_APPROVAL with the
phased-release brake (pausable in App Store Connect), Android writes a staged
production rollout at 5% (haltable in Play Console). An approved but
unreleased iOS version blocks the train for a human: Apple refuses to cancel
its COMPLETE review submission.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

_SPEC = importlib.util.spec_from_file_location("mobile_daily_train", Path(__file__).with_name("mobile_daily_train.py"))
train = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = train
_SPEC.loader.exec_module(train)
promote = train.promote

# Rollout hops call the read-only PostHog capture-health check, which fails
# closed offline. Every test runs with it green unless it patches its own;
# CaptureHealthWiringTests and mobile_capture_health_test.py cover it.
_CAPTURE_HEALTH_GREEN = patch.object(train, "capture_health_hold", return_value=None)
_STORE_BUILD_LOOKUP = patch.object(train, "ios_version_build_number", return_value="1")


def setUpModule():
    _CAPTURE_HEALTH_GREEN.start()
    _STORE_BUILD_LOOKUP.start()


def tearDownModule():
    _STORE_BUILD_LOOKUP.stop()
    _CAPTURE_HEALTH_GREEN.stop()

CREDENTIALS = {
    "APP_STORE_CONNECT_ISSUER_ID": "issuer",
    "APP_STORE_CONNECT_KEY_IDENTIFIER": "key",
    "APP_STORE_CONNECT_PRIVATE_KEY": "secret",
}

# A staged release whose observation window closed long ago: the ladder may hop it.
STALE_RECEIPT_NAME = "1.0.554 (gate 2026-10-06-1015)"


def version(id_: str, number: str, state: str) -> dict:
    return {"id": id_, "attributes": {"versionString": number, "appStoreState": state, "appVersionState": state}}


def build(id_: str, number: str, state: str = "VALID", expired: bool = False) -> dict:
    return {"id": id_, "attributes": {"version": number, "processingState": state, "expired": expired}}


class FakeASC:
    """Scripted app-store-connect responses keyed by (sub)command; records every call."""

    def __init__(self, responses: dict[tuple[str, ...], object]):
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> object:
        self.calls.append(args)
        for key, value in self.responses.items():
            if args[: len(key)] == key and all(part in args for part in key):
                if callable(value):
                    return value(args)
                return value
        raise train.TrainError(f"unexpected app-store-connect call: {args}")

    def mutations(self) -> list[tuple[str, ...]]:
        return [c for c in self.calls if c[:2] in (("review-submissions", "cancel"), ("builds", "submit-to-app-store"))]


def live_responses(**overrides: object) -> dict[tuple[str, ...], object]:
    def versions_by_state(args: tuple[str, ...]) -> list:
        state = args[args.index("--state") + 1]
        return {
            "READY_FOR_SALE": [version("live", "1.0.553", "READY_FOR_SALE"), version("old", "1.0.552", "READY_FOR_SALE")],
            **overrides.get("states", {}),
        }.get(state, [])

    def builds_by_version(args: tuple[str, ...]) -> list:
        pre = args[args.index("--pre-release-version") + 1]
        return overrides.get("builds", {"1.0.554": [build("b1334", "1334"), build("b1333", "1333")]}).get(pre, [])

    responses: dict[tuple[str, ...], object] = {
        ("apps", "app-store-versions"): versions_by_state,
        ("apps", "pre-release-versions"): [
            {"id": "p1", "attributes": {"platform": "IOS", "version": "1.0.554"}},
            {"id": "p2", "attributes": {"platform": "IOS", "version": "1.0.553"}},
            {"id": "p3", "attributes": {"platform": "IOS", "version": "1.0.555"}},
        ],
        ("builds", "list"): builds_by_version,
        ("app-store-versions", "localizations"): [
            {"id": "l1", "attributes": {"locale": "en-US"}},
            {"id": "l2", "attributes": {"locale": "fr-FR"}},
        ],
    }
    responses.update(overrides.get("extra", {}))
    return responses


class PlanTests(unittest.TestCase):
    live = "1.0.553"
    candidate = train.IOSCandidate("b1334", "1.0.554", 1334)

    def state(self, **kwargs) -> train.IOSState:
        base = dict(live_version=self.live, in_flight=(), pending=(), candidate=self.candidate, candidate_version_id=None)
        base.update(kwargs)
        return train.IOSState(**base)

    def test_in_flight_submission_holds_everything(self):
        plan = train.plan_ios(self.state(in_flight=(train.IOSVersion("v", "1.0.554", "WAITING_FOR_REVIEW"),)))
        self.assertEqual(plan.action, "hold")
        self.assertIsNone(plan.submit)

    def test_no_newer_build_does_nothing(self):
        self.assertEqual(train.plan_ios(self.state(candidate=None)).action, "nothing")

    def test_pending_with_newest_build_is_left_for_a_human(self):
        pending = train.IOSVersion("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        plan = train.plan_ios(self.state(pending=(pending,), candidate_version_id="pend"))
        self.assertEqual(plan.action, "leave")
        self.assertIsNone(plan.submit)

    def test_pending_with_older_build_blocks_for_a_human(self):
        # Apple 409s a cancel of the approved version's COMPLETE submission and
        # has no developer-reject API, so the train must stop, not replace.
        pending = train.IOSVersion("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        plan = train.plan_ios(self.state(pending=(pending,), candidate_version_id=None))
        self.assertEqual(plan.action, "blocked")
        self.assertIsNone(plan.submit)
        self.assertIn("ACTION REQUIRED", plan.reason)
        self.assertIn("releases 1.0.554 or rejects its binary", plan.reason)

    def test_pending_newer_than_testflight_is_never_offered_for_rejection(self):
        pending = train.IOSVersion("pend", "1.0.560", "PENDING_DEVELOPER_RELEASE")
        with self.assertRaisesRegex(train.TrainError, "never reject it"):
            train.plan_ios(self.state(pending=(pending,)))

    def test_two_pending_versions_need_a_human(self):
        pending = (
            train.IOSVersion("a", "1.0.554", "PENDING_DEVELOPER_RELEASE"),
            train.IOSVersion("b", "1.0.555", "PENDING_DEVELOPER_RELEASE"),
        )
        with self.assertRaises(train.TrainError):
            train.plan_ios(self.state(pending=pending))

    def test_clear_track_submits(self):
        plan = train.plan_ios(self.state())
        self.assertEqual(plan.action, "submit")
        self.assertEqual(plan.submit, self.candidate)


class StateFetchTests(unittest.TestCase):
    def test_candidate_is_highest_version_with_a_processed_build_and_its_highest_build(self):
        asc = FakeASC(live_responses(builds={"1.0.555": [build("x", "1340", "PROCESSING")], "1.0.554": [build("b1334", "1334"), build("b1333", "1333")]}))
        candidate = train.ios_candidate(asc, "1.0.553")
        self.assertEqual(candidate, train.IOSCandidate("b1334", "1.0.554", 1334))
        listed = [c for c in asc.calls if c[:2] == ("builds", "list")]
        self.assertEqual([c[c.index("--pre-release-version") + 1] for c in listed], ["1.0.555", "1.0.554"])
        self.assertTrue(all("--not-expired" in c and "VALID" in c for c in listed))

    def test_versions_are_read_per_state_because_the_unfiltered_listing_hides_them(self):
        asc = FakeASC(live_responses())
        state = train.fetch_ios_state(asc)
        states = {c[c.index("--state") + 1] for c in asc.calls if c[:2] == ("apps", "app-store-versions")}
        self.assertEqual(states, {train.LIVE_STATE, train.PENDING_STATE, *train.IN_FLIGHT_STATES})
        self.assertEqual(state.live_version, "1.0.553")
        self.assertEqual(state.candidate.build_number, 1334)

    def test_missing_live_version_fails_closed(self):
        asc = FakeASC(live_responses(states={"READY_FOR_SALE": []}))
        with self.assertRaisesRegex(train.TrainError, "no live"):
            train.fetch_ios_state(asc)


class RunIOSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.release = Path(self.tmp.name) / "1.0.554.json"
        self.release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["New thing"]}))
        self.notes_patch = patch.object(train, "ensure_release_notes", return_value=self.release)
        self.notes_patch.start()
        self.env = patch.dict(train.os.environ, CREDENTIALS)
        self.env.start()

    def tearDown(self):
        self.notes_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_dry_run_reads_everything_and_mutates_nothing(self):
        asc = FakeASC(live_responses())
        with patch.object(train, "ios_phased_release_should_complete", return_value=(False, "no phased release")), patch.object(
            train, "ios_phased_release_paused", return_value=False
        ), patch.object(promote.subprocess, "run") as run:
            summary = train.run_ios(dry_run=True, release_date="2026-10-06", asc=asc)
        self.assertIn("dry-run:submit 1.0.554 (1334)", summary)
        self.assertEqual(asc.mutations(), [])
        run.assert_not_called()

    def test_hold_never_touches_notes_or_stores(self):
        asc = FakeASC(live_responses(states={"IN_REVIEW": [version("v", "1.0.554", "IN_REVIEW")]}))
        with patch.object(train, "ios_phased_release_should_complete", return_value=(False, "no phased release")), patch.object(
            promote.subprocess, "run"
        ) as run:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        self.assertTrue(summary.startswith("ios=hold"))
        run.assert_not_called()
        self.assertEqual(asc.mutations(), [])

    def test_paused_phased_release_holds_the_train(self):
        asc = FakeASC(live_responses())
        with patch.object(train, "_asc_rest_token", return_value="faketoken"), patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "phased rollout is PAUSED — the operator brake")
        ), patch.object(
            train, "ios_phased_release_paused", return_value=True
        ) as paused, patch.object(promote.subprocess, "run") as run:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        self.assertTrue(summary.startswith("ios=hold"))
        self.assertIn("PAUSED", summary)
        paused.assert_called_once()
        run.assert_not_called()
        self.assertEqual(asc.mutations(), [])

    def test_unpaused_phased_release_still_submits(self):
        asc = FakeASC(
            live_responses(
                extra={
                    ("builds", "app-store-version"): {"id": "new-version", "attributes": {"appStoreState": "WAITING_FOR_REVIEW"}},
                    ("app-store-versions", "get"): {"id": "new-version", "attributes": {"appStoreState": "WAITING_FOR_REVIEW"}},
                }
            )
        )

        def fake_run(command, **kwargs):
            return Mock(returncode=0)

        with patch.object(train, "_asc_rest_token", return_value="faketoken"), patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "no phased release")
        ), patch.object(
            train, "ios_phased_release_paused", return_value=False
        ), patch.object(train, "_attach_phased_release") as attach, patch.object(
            promote.subprocess, "run", side_effect=fake_run
        ), patch.object(train.time, "sleep"), patch.object(
            promote, "require_notes", return_value="- New thing"
        ):
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        self.assertTrue(summary.startswith("ios=submit"))
        self.assertTrue(summary.endswith("(phased rollout attached; day 1 = 1%)"))
        attach.assert_called_once_with("new-version")

    def test_phased_release_lookup_reads_the_rest_resource(self):
        def rest_lookup(url, timeout=60):
            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def read(self):
                    return json.dumps(
                        {"data": {"type": "appStoreVersionPhasedReleases", "id": "pr1", "attributes": {"phasedReleaseState": "PAUSED"}}}
                    ).encode()

            return Response()

        with patch.object(train.urllib.request, "urlopen", side_effect=rest_lookup), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ):
            self.assertTrue(train.ios_phased_release_paused("live-version-id"))

    def test_phased_release_absent_404_is_not_a_pause(self):
        import email.message
        import urllib.error as urlerror

        def rest_lookup(url, timeout=60):
            raise urlerror.HTTPError(url, 404, "Not Found", email.message.Message(), None)

        with patch.object(train.urllib.request, "urlopen", side_effect=rest_lookup), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ):
            self.assertFalse(train.ios_phased_release_paused("live-version-id"))

    def test_phased_release_null_data_is_not_a_pause(self):
        # Apple's live answer for a version released without a phased rollout.
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"data": None, "links": {"self": "https://example"}}).encode()

        with patch.object(train.urllib.request, "urlopen", return_value=Response()), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ):
            self.assertFalse(train.ios_phased_release_paused("live-version-id"))

    def test_phased_release_without_data_still_fails_closed(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"errors": []}).encode()

        with patch.object(train.urllib.request, "urlopen", return_value=Response()), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ):
            with self.assertRaisesRegex(train.TrainError, "invalid resource"):
                train.ios_phased_release_paused("live-version-id")

    def test_phased_release_lookup_failure_fails_closed(self):
        import email.message
        import urllib.error as urlerror

        def rest_lookup(url, timeout=60):
            raise urlerror.HTTPError(url, 500, "Server Error", email.message.Message(), None)

        with patch.object(train.urllib.request, "urlopen", side_effect=rest_lookup), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ):
            with self.assertRaisesRegex(train.TrainError, "phased-release lookup failed"):
                train.ios_phased_release_paused("live-version-id")

    def test_submit_uses_manual_release_and_every_live_locale(self):
        version_states = iter(["PREPARE_FOR_SUBMISSION", "WAITING_FOR_REVIEW"])
        asc = FakeASC(
            live_responses(
                extra={
                    ("builds", "app-store-version"): {"id": "new-version", "attributes": {"appStoreState": "WAITING_FOR_REVIEW"}},
                    ("app-store-versions", "get"): lambda args: {"id": "new-version", "attributes": {"appStoreState": next(version_states)}},
                }
            )
        )
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            path = next(a for a in command if a.startswith("@file:"))[len("@file:") :]
            captured["localizations"] = json.loads(Path(path).read_text())
            return Mock(returncode=0)

        with patch.object(train, "ios_phased_release_should_complete", return_value=(False, "no phased release")), patch.object(
            train, "ios_phased_release_paused", return_value=False
        ), patch.object(train, "_attach_phased_release") as attach, patch.object(
            promote.subprocess, "run", side_effect=fake_run
        ), patch.object(train.time, "sleep"), patch.object(
            promote, "require_notes", return_value="- New thing"
        ):
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        attach.assert_called_once_with("new-version")
        command = captured["command"]
        self.assertEqual(command[:3], ["app-store-connect", "builds", "submit-to-app-store"])
        self.assertEqual(command[command.index("--release-type") + 1], train.RELEASE_TYPE)
        self.assertIn("--phased-release" if train.PHASED_RELEASE else "--no-phased-release", command)
        self.assertNotIn("--cancel-previous-submissions", command)
        self.assertNotIn("--whats-new", command)
        self.assertEqual(command[-1], "b1334")
        self.assertEqual(captured["localizations"], [{"locale": "en-US", "whats_new": "- New thing"}, {"locale": "fr-FR", "whats_new": "- New thing"}])
        self.assertEqual(summary, f"ios=submit 1.0.554 (1334) WAITING_FOR_REVIEW ({train.RELEASE_TYPE}{'/phased' if train.PHASED_RELEASE else ''}) (phased rollout attached; day 1 = 1%)")
        self.assertEqual([c for c in asc.calls if c[:2] == ("review-submissions", "cancel")], [])

    def test_manual_release_type_and_no_phased_flag_stay_available(self):
        # The queue-for-human posture must remain one constant away: MANUAL +
        # --no-phased-release must still be expressible and correctly wired.
        build = promote.IOSBuild("b1", "1.0.554", "1334")
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return Mock(returncode=0)

        with patch.object(promote.subprocess, "run", side_effect=fake_run):
            promote.submit_ios(build, "- n", locales=["en-US"], release_type="MANUAL", phased=False)
        command = captured["command"]
        self.assertEqual(command[command.index("--release-type") + 1], "MANUAL")
        self.assertIn("--no-phased-release", command)
        self.assertNotIn("--phased-release", command)

    def test_phased_requires_after_approval(self):
        build = promote.IOSBuild("b1", "1.0.554", "1334")
        with self.assertRaisesRegex(promote.PromotionError, "AFTER_APPROVAL"):
            promote.submit_ios(build, "- n", locales=["en-US"], release_type="MANUAL", phased=True)
        with self.assertRaisesRegex(promote.PromotionError, "MANUAL or AFTER_APPROVAL"):
            promote.submit_ios(build, "- n", locales=["en-US"], release_type="WHENEVER")

    def test_paused_brake_holds_instead_of_asking_for_a_release(self):
        pending = version("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        asc = FakeASC(
            live_responses(
                states={"PENDING_DEVELOPER_RELEASE": [pending]},
                builds={"1.0.554": [build("b1335", "1335"), build("b1334", "1334")]},
                extra={("builds", "app-store-version"): None},
            )
        )
        with patch.object(promote.subprocess, "run") as run, patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "phased rollout is PAUSED — the operator brake")
        ), patch.object(train, "ios_phased_release_paused", return_value=True):
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        run.assert_not_called()
        self.assertTrue(summary.startswith("ios=hold (live 1.0.553 phased rollout is PAUSED"))

    def test_blocked_pending_version_is_released_with_the_phased_rollout_attached(self):
        # Apple refuses to cancel a COMPLETE review submission (409) but does
        # honor POST appStoreVersionReleaseRequests (verified live 2026-10-17
        # on 1.0.564): the train attaches the phased rollout first so the
        # release starts at 1% with the pause brake available, then releases.
        pending = version("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        asc = FakeASC(
            live_responses(
                states={"PENDING_DEVELOPER_RELEASE": [pending]},
                builds={"1.0.554": [build("b1335", "1335"), build("b1334", "1334")]},
                extra={("builds", "app-store-version"): None},
            )
        )
        with patch.object(promote.subprocess, "run") as run, patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "no phased release")
        ), patch.object(train, "ios_phased_release_paused", return_value=False), patch.object(
            train, "_attach_phased_release"
        ) as attach, patch.object(train, "_release_approved_version") as release:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        run.assert_not_called()
        attach.assert_called_once_with("pend")
        release.assert_called_once_with("pend", "1.0.554")
        self.assertEqual(summary, "ios=blocked: released approved 1.0.554 (phased rollout attached)")
        self.assertEqual([c for c in asc.calls if c[:2] == ("review-submissions", "cancel")], [])

    def _pending_asc(self):
        pending = version("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        return FakeASC(
            live_responses(
                states={"PENDING_DEVELOPER_RELEASE": [pending]},
                builds={"1.0.554": [build("b1335", "1335"), build("b1334", "1334")]},
                extra={("builds", "app-store-version"): None},
            )
        )

    def test_an_already_attached_phased_rollout_still_releases_the_approved_version(self):
        # The train's own submit attaches the phased rollout, so Apple rejects
        # the re-attach as a duplicate; the read-back proves it is there.
        asc = self._pending_asc()
        with patch.object(promote.subprocess, "run"), patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "no phased release")
        ), patch.object(train, "ios_phased_release_paused", return_value=False), patch.object(
            train, "_attach_phased_release", side_effect=train.TrainError("HTTP 409 duplicate")
        ), patch.object(
            train, "ios_phased_release", return_value={"id": "ph1", "attributes": {"phasedReleaseState": "INACTIVE"}}
        ) as read_back, patch.object(train, "_release_approved_version") as release:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        read_back.assert_called_once_with("pend")
        release.assert_called_once_with("pend", "1.0.554")
        self.assertEqual(summary, "ios=blocked: released approved 1.0.554 (phased rollout attached)")

    def test_a_failed_attach_without_a_phased_rollout_never_releases(self):
        asc = self._pending_asc()
        with patch.object(promote.subprocess, "run"), patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "no phased release")
        ), patch.object(train, "ios_phased_release_paused", return_value=False), patch.object(
            train, "_attach_phased_release", side_effect=train.TrainError("HTTP 500")
        ), patch.object(train, "ios_phased_release", return_value=None), patch.object(
            train, "_release_approved_version"
        ) as release:
            with self.assertRaisesRegex(train.TrainError, "not attached to approved 1.0.554"):
                train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        release.assert_not_called()

    def test_a_paused_brake_defers_releasing_the_approved_version(self):
        pending = version("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        asc = FakeASC(
            live_responses(
                states={"PENDING_DEVELOPER_RELEASE": [pending]},
                builds={"1.0.554": [build("b1335", "1335"), build("b1334", "1334")]},
                extra={("builds", "app-store-version"): None},
            )
        )
        with patch.object(promote.subprocess, "run") as run, patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "phased rollout is PAUSED — the operator brake")
        ), patch.object(train, "ios_phased_release_paused", return_value=True), patch.object(
            train, "_attach_phased_release"
        ) as attach, patch.object(train, "_release_approved_version") as release:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        run.assert_not_called()
        attach.assert_not_called()
        release.assert_not_called()
        self.assertTrue(summary.startswith("ios=hold (live 1.0.553 phased rollout is PAUSED"))
        self.assertIn("deferred", summary)

    def test_advance_mode_only_checks_the_phase_window(self):
        asc = FakeASC(live_responses())
        with patch.object(train, "ios_phased_release_should_complete", return_value=(False, "phased rollout is 5.0h old (< 12h observation window)")) as check:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", advance_only=True, asc=asc)
        self.assertEqual(summary, "ios=advance (phased rollout is 5.0h old (< 12h observation window))")
        check.assert_called_once()
        self.assertEqual([c for c in asc.calls if c[:2] == ("builds", "submit-to-app-store")], [])

    def test_advance_mode_jumps_when_the_window_has_passed(self):
        asc = FakeASC(live_responses())
        with patch.object(train, "ios_phased_release_should_complete", return_value=(True, "phased rollout is 12.5h old; releasing to everyone")), patch.object(
            train, "_complete_phased_release"
        ) as complete:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", advance_only=True, asc=asc)
        complete.assert_called_once_with("live")
        self.assertEqual(summary, "ios=advance (released to everyone (jump to 100%))")

    def test_the_phased_jump_never_fires_while_paused(self):
        # The operator pause is the brake: even weeks old, a PAUSED rollout is
        # never "complete" by the decision helper.
        phased = {"attributes": {"phasedReleaseState": "PAUSED", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased):
            should, reason = train.ios_phased_release_should_complete(
                "x", now=datetime(2026, 1, 20, tzinfo=timezone.utc)
            )
        self.assertFalse(should)
        self.assertIn("PAUSED", reason)

    def test_the_phased_jump_fires_after_the_observation_window(self):
        phased = {"attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased):
            should, reason = train.ios_phased_release_should_complete(
                "x", now=datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
            )
        self.assertTrue(should)
        self.assertIn("13.0h", reason)

    def test_the_phased_jump_waits_inside_the_observation_window(self):
        phased = {"attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased):
            should, reason = train.ios_phased_release_should_complete(
                "x", now=datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc)
            )
        self.assertFalse(should)
        self.assertIn("12.0h", reason)

    def test_the_phased_jump_holds_for_any_state_but_active(self):
        # Apple's states are ACTIVE, PAUSED, COMPLETE and INACTIVE; only ACTIVE is
        # a live rollout to advance. A finished (COMPLETE) one must not be touched.
        for state in ("COMPLETE", "INACTIVE", "SOMETHING_NEW"):
            phased = {"attributes": {"phasedReleaseState": state, "startDate": "2026-01-01T00:00:00Z"}}
            with patch.object(train, "ios_phased_release", return_value=phased):
                should, reason = train.ios_phased_release_should_complete(
                    "x", now=datetime(2026, 1, 20, tzinfo=timezone.utc)
                )
            self.assertFalse(should, state)
            self.assertIn(state, reason)

    def _phased_response(self, state):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps(
                    {"data": {"type": "appStoreVersionPhasedReleases", "id": "pr-1", "attributes": {"phasedReleaseState": state}}}
                ).encode()

        return Response()

    def test_the_jump_patches_the_phased_release_resource_to_complete(self):
        phased = {"id": "pr-1", "attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ), patch.object(train.urllib.request, "urlopen", return_value=self._phased_response("COMPLETE")) as urlopen:
            train._complete_phased_release("live")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(request.full_url, "https://api.appstoreconnect.apple.com/v1/appStoreVersionPhasedReleases/pr-1")
        self.assertEqual(
            json.loads(request.data)["data"],
            {"type": "appStoreVersionPhasedReleases", "id": "pr-1", "attributes": {"phasedReleaseState": "COMPLETE"}},
        )

    def test_the_jump_fails_when_the_state_does_not_read_back_complete(self):
        phased = {"id": "pr-1", "attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ), patch.object(train.urllib.request, "urlopen", return_value=self._phased_response("ACTIVE")):
            with self.assertRaises(train.TrainError):
                train._complete_phased_release("live")

    def test_phased_jump_decision_fails_closed_on_lookup_errors(self):
        with patch.object(train, "ios_phased_release", side_effect=train.TrainError("HTTP 500")):
            should, reason = train.ios_phased_release_should_complete("x")
        self.assertFalse(should)
        self.assertIn("HTTP 500", reason)

    def _generate_openssl_ec_pem(self) -> str:
        result = subprocess.run(
            ["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout"],
            capture_output=True,
            check=True,
            timeout=30,
        )
        return result.stdout.decode()

    DER_SIG = b"\x30\x44\x02\x20" + b"\x01" * 32 + b"\x02\x20" + b"\x02" * 32

    def _install_fake_cryptography(self, load_behavior):
        """Install a fake cryptography module tree so the signer's function-local
        imports resolve without the real package (not installed everywhere)."""
        import types

        modules = {}
        for name in (
            "cryptography",
            "cryptography.hazmat",
            "cryptography.hazmat.primitives",
            "cryptography.hazmat.primitives.serialization",
            "cryptography.hazmat.primitives.asymmetric",
            "cryptography.hazmat.primitives.hashes",
        ):
            modules[name] = types.ModuleType(name)
        modules["cryptography.hazmat.primitives.serialization"].load_pem_private_key = load_behavior
        modules["cryptography.hazmat.primitives"].serialization = modules[
            "cryptography.hazmat.primitives.serialization"
        ]
        modules["cryptography.hazmat.primitives"].hashes = modules["cryptography.hazmat.primitives.hashes"]
        modules["cryptography.hazmat.primitives"].asymmetric = modules["cryptography.hazmat.primitives.asymmetric"]
        saved = {name: train.sys.modules.get(name) for name in modules}
        train.sys.modules.update(modules)
        return saved

    def _restore_cryptography(self, saved):
        for name, module in saved.items():
            if module is None:
                train.sys.modules.pop(name, None)
            else:
                train.sys.modules[name] = module

    def test_rest_token_falls_back_to_openssl_when_cryptography_rejects_the_key(self):
        # Some CI OpenSSL builds import fine and then raise at key-load time
        # (unsupported key type / explicit EC parameters) — observed live on the
        # Codemagic train 2026-10-15. The fallback must catch ANY cryptography
        # failure, not only ImportError, or every REST read fails closed.
        pem = self._generate_openssl_ec_pem()
        real_run = subprocess.run

        def reject(_data, password=None):
            raise ValueError("Could not deserialize key data. The data may be in an incorrect format")

        def reject_and_fall_back(command, **kwargs):
            if command[:2] == ["openssl", "ecparam"]:
                return real_run(command, **kwargs)
            self.assertEqual(command[:3], ["openssl", "dgst", "-sha256"])
            self.assertIn("-sign", command)
            return Mock(returncode=0, stdout=self.DER_SIG)

        saved = self._install_fake_cryptography(reject)
        try:
            with patch.dict(train.os.environ, {
                "APP_STORE_CONNECT_ISSUER_ID": "iss",
                "APP_STORE_CONNECT_KEY_IDENTIFIER": "kid",
                "APP_STORE_CONNECT_PRIVATE_KEY": pem,
            }), patch.object(train, "log"), patch.object(train.subprocess, "run", side_effect=reject_and_fall_back):
                token = train._asc_rest_token()
        finally:
            self._restore_cryptography(saved)
        import base64 as b64

        header, _, signature = token.split(".")
        self.assertEqual(json.loads(b64.urlsafe_b64decode(header + "=="))["kid"], "kid")
        self.assertEqual(len(b64.urlsafe_b64decode(signature + "==")), 64)

    def test_rest_token_uses_cryptography_directly_when_key_loads(self):
        pem = self._generate_openssl_ec_pem()
        openssl_calls = []

        def record_non_ecparam(command, **kwargs):
            if command[:2] == ["openssl", "ecparam"]:
                return subprocess.run(command, **kwargs)
            openssl_calls.append(list(command))
            return Mock(returncode=0, stdout=b"")

        fake_key = Mock()
        fake_key.sign = Mock(return_value=self.DER_SIG)

        def load_ok(_data, password=None):
            return fake_key

        modules_fake_ec = Mock()
        modules_fake_hashes = Mock()

        def make_fake_tree():
            import types

            tree = {}
            for name in (
                "cryptography",
                "cryptography.hazmat",
                "cryptography.hazmat.primitives",
                "cryptography.hazmat.primitives.serialization",
                "cryptography.hazmat.primitives.asymmetric",
                "cryptography.hazmat.primitives.hashes",
            ):
                tree[name] = types.ModuleType(name)
            tree["cryptography.hazmat.primitives.serialization"].load_pem_private_key = load_ok
            tree["cryptography.hazmat.primitives"].serialization = tree[
                "cryptography.hazmat.primitives.serialization"
            ]
            tree["cryptography.hazmat.primitives"].hashes = modules_fake_hashes
            tree["cryptography.hazmat.primitives"].asymmetric = tree["cryptography.hazmat.primitives.asymmetric"]
            tree["cryptography.hazmat.primitives.asymmetric"].ec = modules_fake_ec
            tree["cryptography.hazmat.primitives.hashes"].SHA256 = Mock(return_value="sha256")
            tree["cryptography.hazmat.primitives.asymmetric"].ECDSA = Mock(return_value="ecdsa")
            return tree

        tree = make_fake_tree()
        saved = {name: train.sys.modules.get(name) for name in tree}
        train.sys.modules.update(tree)
        try:
            with patch.dict(train.os.environ, {
                "APP_STORE_CONNECT_ISSUER_ID": "iss",
                "APP_STORE_CONNECT_KEY_IDENTIFIER": "kid",
                "APP_STORE_CONNECT_PRIVATE_KEY": pem,
            }), patch.object(train, "log"), patch.object(train.subprocess, "run", side_effect=record_non_ecparam):
                token = train._asc_rest_token()
        finally:
            self._restore_cryptography(saved)
        self.assertEqual(openssl_calls, [])  # cryptography path, no CLI fallback
        fake_key.sign.assert_called_once()
        import base64 as b64

        header, _, signature = token.split(".")
        self.assertEqual(json.loads(b64.urlsafe_b64decode(header + "=="))["alg"], "ES256")
        self.assertEqual(len(b64.urlsafe_b64decode(signature + "==")), 64)

    def test_rest_token_raises_when_both_cryptography_and_openssl_fail(self):
        pem = self._generate_openssl_ec_pem()

        def reject(_data, password=None):
            raise ValueError("Could not deserialize key data")

        def fail_cli(command, **kwargs):
            if command[:2] == ["openssl", "ecparam"]:
                return subprocess.run(command, **kwargs)
            raise subprocess.CalledProcessError(1, "openssl")

        saved = self._install_fake_cryptography(reject)
        try:
            with patch.dict(train.os.environ, {
                "APP_STORE_CONNECT_ISSUER_ID": "iss",
                "APP_STORE_CONNECT_KEY_IDENTIFIER": "kid",
                "APP_STORE_CONNECT_PRIVATE_KEY": pem,
            }), patch.object(train, "log"), patch.object(train.subprocess, "run", side_effect=fail_cli):
                with self.assertRaises(train.TrainError) as ctx:
                    train._asc_rest_token()
        finally:
            self._restore_cryptography(saved)
        self.assertIn("cryptography", str(ctx.exception))
        self.assertIn("openssl", str(ctx.exception))

    def test_missing_credentials_fail_before_any_store_call(self):
        asc = FakeASC({})
        with patch.dict(train.os.environ, {"APP_STORE_CONNECT_PRIVATE_KEY": ""}):
            with self.assertRaisesRegex(train.TrainError, "APP_STORE_CONNECT_PRIVATE_KEY"):
                train.run_ios(dry_run=True, release_date="2026-10-06", asc=asc)
        self.assertEqual(asc.calls, [])


class ReleaseNotesTests(unittest.TestCase):
    def test_no_release_file_and_no_fragments_blocks_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock()
            fake.RELEASES_DIR = Path(tmp)
            fake.unreleased_fragment_paths.return_value = []
            fake.ChangelogError = ValueError
            fake.collect.side_effect = ValueError("no unreleased fragments and no release file")
            with patch.object(train, "spec_from_file_location") as spec, patch.object(train, "module_from_spec", return_value=fake):
                spec.return_value = Mock(loader=Mock())
                with self.assertRaisesRegex(train.TrainError, "no release notes"):
                    train.ensure_release_notes("1.0.554", "2026-10-06", write=False)
                with self.assertRaisesRegex(train.TrainError, "unavailable"):
                    train.ensure_release_notes("1.0.554", "2026-10-06", write=True)

    def test_dry_run_never_writes_release_files(self):
        fake = Mock()
        fake.RELEASES_DIR = Path("/nonexistent")
        fake.unreleased_fragment_paths.return_value = [Path("fragment.json")]
        fake.ChangelogError = ValueError
        with patch.object(train, "spec_from_file_location") as spec, patch.object(train, "module_from_spec", return_value=fake):
            spec.return_value = Mock(loader=Mock())
            train.ensure_release_notes("1.0.554", "2026-10-06", write=False)
        fake.collect.assert_not_called()


class AndroidTests(unittest.TestCase):
    def setUp(self):
        self.production = {
            "track": "production",
            "releases": [{"name": "1.0.552 (1246)", "versionCodes": ["1246"], "status": "completed"}],
        }
        self.internal = {
            "track": "internal",
            "releases": [
                {"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "completed"},
                {"name": "1.0.554 (1339)", "versionCodes": ["1339"], "status": "completed"},
            ],
        }
        self.alpha = {"track": "alpha", "releases": [{"name": "1.0.553", "versionCodes": ["1320"], "status": "completed"}]}

    def test_newest_code_newer_than_live_wins_across_tracks(self):
        candidate = train.pick_play_candidate({"internal": self.internal, "alpha": self.alpha}, self.production)
        self.assertEqual(candidate, train.PlayCandidate("internal", "1.0.554", "1340"))

    def test_live_or_older_versions_and_drafts_are_ignored(self):
        self.production["releases"][0]["name"] = "1.0.554 (1340)"
        self.internal["releases"].append({"name": "1.0.555 (1350)", "versionCodes": ["1350"], "status": "draft"})
        self.assertIsNone(train.pick_play_candidate({"internal": self.internal, "alpha": self.alpha}, self.production))

    def test_staged_rollout_written_from_the_source_track_and_haltable(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release), patch.object(
                promote, "require_notes", return_value="Faster sync"
            ):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, f"android=staged 1.0.554 (1340) @{train.STAGED_ROLLOUT_FRACTION:.0%}")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "inProgress")
        self.assertEqual(body["releases"][0]["userFraction"], train.STAGED_ROLLOUT_FRACTION)
        self.assertEqual(body["releases"][0]["versionCodes"], ["1340"])
        self.assertRegex(body["releases"][0]["name"], r"^1\.0\.554 \(gate \d{4}-\d{2}-\d{2}-\d{4}\)$")
        self.assertEqual(body["releases"][0]["releaseNotes"], [{"language": "en-US", "text": "Faster sync"}])
        client.edits().commit.assert_called_once()

    def test_draft_posture_still_available_when_staged_rollout_disabled(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release), patch.object(
                promote, "require_notes", return_value="Faster sync"
            ), patch.object(train, "STAGED_ROLLOUT_FRACTION", None):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=draft 1.0.554 (1340)")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "draft")
        self.assertNotIn("userFraction", body["releases"][0])
        client.edits().commit.assert_called_once()

    def test_user_fraction_requires_staged_status(self):
        with self.assertRaisesRegex(promote.PromotionError, "inProgress"):
            promote.submit_android(Mock(), "edit", "1.0.554", "1340", "n", status="completed", user_fraction=0.05)
        with self.assertRaisesRegex(promote.PromotionError, "strictly between"):
            promote.submit_android(Mock(), "edit", "1.0.554", "1340", "n", status="inProgress", user_fraction=1.0)

    def test_ladder_promotes_staged_release_one_hop_per_green_day(self):
        client = Mock()
        staged = {"name": STALE_RECEIPT_NAME, "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release), patch.object(
                promote, "require_notes", return_value="Faster sync"
            ):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @10%")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "inProgress")
        self.assertEqual(body["releases"][0]["userFraction"], 0.10)
        client.edits().commit.assert_called_once()

    def test_ladder_completes_at_the_top(self):
        client = Mock()
        staged = {"name": STALE_RECEIPT_NAME, "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.50}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release), patch.object(
                promote, "require_notes", return_value="Faster sync"
            ):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=completed 1.0.554 1340 100%")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "completed")
        self.assertNotIn("userFraction", body["releases"][0])
        client.edits().commit.assert_called_once()

    def test_ladder_leaves_halted_staged_releases_to_a_human(self):
        client = Mock()
        halted = {"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "halted", "userFraction": 0.05}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [halted]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged-halted 1.0.554 1340")
        client.edits().tracks().update.assert_not_called()

    def test_fractionless_inprogress_is_also_the_halted_shape(self):
        client = Mock()
        halted = {"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "inProgress"}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [halted]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged-halted 1.0.554 1340")
        client.edits().tracks().update.assert_not_called()

    def test_ladder_keeps_hopping_while_a_newer_candidate_waits(self):
        client = Mock()
        staged = {"name": STALE_RECEIPT_NAME, "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05}
        newer_internal = {
            "track": "internal",
            "releases": [{"name": "1.0.555 (1350)", "versionCodes": ["1350"], "status": "completed"}],
        }
        tracks = {"internal": newer_internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release) as ensure_notes, patch.object(
                promote, "require_notes", return_value="Faster sync"
            ):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @10%")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["versionCodes"], ["1340"])
        self.assertEqual(body["releases"][0]["userFraction"], 0.10)
        client.edits().commit.assert_called_once()

    def test_ladder_hop_reuses_the_notes_play_already_holds(self):
        client = Mock()
        staged = {
            "name": STALE_RECEIPT_NAME,
            "versionCodes": ["1340"],
            "status": "inProgress",
            "userFraction": 0.05,
            "releaseNotes": [{"language": "en-US", "text": "Shipped text"}],
        }
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes") as ensure_notes:
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @10%")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["releaseNotes"], [{"language": "en-US", "text": "Shipped text"}])
        ensure_notes.assert_not_called()

    def test_disabled_staged_rollout_parks_an_in_flight_rollout(self):
        client = Mock()
        staged = {"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "STAGED_ROLLOUT_FRACTION", None):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @5% parked (staged disabled)")
        client.edits().tracks().update.assert_not_called()

    def test_a_fresh_gate_receipt_holds_position_inside_the_observation_window(self):
        client = Mock()
        receipt = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d-%H%M")
        staged = {"name": f"1.0.554 (gate {receipt})", "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertIn("android=staged 1.0.554 1340 @5%", summary)
        self.assertTrue(summary.endswith("window 4h)"))
        client.edits().tracks().update.assert_not_called()

    def test_a_dry_run_also_holds_position_after_a_gate_receipt(self):
        client = Mock()
        receipt = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d-%H%M")
        staged = {"name": f"1.0.554 (gate {receipt})", "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.25}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            summary = train.run_android(dry_run=True, release_date="2026-10-06")
        self.assertIn("android=staged 1.0.554 1340 @25%", summary)
        self.assertTrue(summary.endswith("window 4h)"))
        client.edits().tracks().update.assert_not_called()

    def test_a_stale_receipt_hops_again(self):
        client = Mock()
        staged = {
            "name": "1.0.554 (gate 2026-10-06-1015)",
            "versionCodes": ["1340"],
            "status": "inProgress",
            "userFraction": 0.05,
            "releaseNotes": [{"language": "en-US", "text": "Shipped text"}],
        }
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes") as ensure_notes:
            summary = train.run_android(dry_run=False, release_date="2026-10-07")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @10%")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertRegex(body["releases"][0]["name"], r"^1\.0\.554 \(gate \d{4}-\d{2}-\d{2}-\d{4}\)$")
        self.assertEqual(body["releases"][0]["userFraction"], 0.10)
        client.edits().commit.assert_called_once()

    def test_a_receipt_free_name_is_stamped_and_held_not_hopped(self):
        # A rollout renamed in Play Console, or one in flight from before
        # receipts existed, has no proof of when it reached its fraction. It
        # gets a receipt at the same fraction and waits out the window.
        for advance_only in (False, True):
            with self.subTest(advance_only=advance_only):
                client = Mock()
                staged = {
                    "name": "1.0.554 (1340)",
                    "versionCodes": ["1340"],
                    "status": "inProgress",
                    "userFraction": 0.05,
                    "releaseNotes": [{"language": "en-US", "text": "Shipped text"}],
                }
                tracks = {
                    "internal": self.internal,
                    "alpha": self.alpha,
                    "production": {"track": "production", "releases": [staged]},
                }
                with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                    promote, "play_track", side_effect=lambda c, e, name: tracks[name]
                ), patch.object(train, "ensure_release_notes") as ensure_notes:
                    summary = train.run_android(dry_run=False, release_date="2026-10-06", advance_only=advance_only)
                self.assertEqual(summary, "android=staged 1.0.554 1340 @5% (no gate receipt; stamped, holding 4h)")
                body = client.edits().tracks().update.call_args.kwargs["body"]
                self.assertEqual(body["releases"][0]["status"], "inProgress")
                self.assertEqual(body["releases"][0]["userFraction"], 0.05)
                self.assertRegex(body["releases"][0]["name"], r"^1\.0\.554 \(gate \d{4}-\d{2}-\d{2}-\d{4}\)$")
                self.assertEqual(body["releases"][0]["releaseNotes"], [{"language": "en-US", "text": "Shipped text"}])
                ensure_notes.assert_not_called()

    def test_the_stamp_holds_the_next_run(self):
        # The stamped name is what Play hands back next time: inside the window it holds.
        client = Mock()
        staged = {"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05,
                  "releaseNotes": [{"language": "en-US", "text": "Shipped text"}]}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            train.run_android(dry_run=False, release_date="2026-10-06")
            staged["name"] = client.edits().tracks().update.call_args.kwargs["body"]["releases"][0]["name"]
            client.reset_mock()
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertTrue(summary.endswith("window 4h)"), summary)
        client.edits().tracks().update.assert_not_called()

    def test_a_receipt_free_dry_run_reports_the_stamp_without_writing(self):
        client = Mock()
        staged = {"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.10,
                  "releaseNotes": [{"language": "en-US", "text": "Shipped text"}]}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            summary = train.run_android(dry_run=True, release_date="2026-10-06")
        self.assertEqual(summary, "android=dry-run:staged-stamp 1.0.554 1340 @10% (no gate receipt; would stamp and hold)")
        client.edits().tracks().update.assert_not_called()

    def test_ladder_hop_retains_every_apk_code(self):
        client = Mock()
        staged = {
            "name": STALE_RECEIPT_NAME,
            "versionCodes": ["1340", "1339"],
            "status": "inProgress",
            "userFraction": 0.05,
            "releaseNotes": [{"language": "en-US", "text": "Shipped text"}],
        }
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes") as ensure_notes:
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @10%")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["versionCodes"], ["1340", "1339"])
        self.assertEqual(body["releases"][0]["userFraction"], 0.10)
        ensure_notes.assert_not_called()

    def test_ladder_dry_run_validates_the_notes_fallback(self):
        client = Mock()
        staged = {"name": STALE_RECEIPT_NAME, "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes", side_effect=train.TrainError("no release notes for 1.0.554")):
            with self.assertRaisesRegex(train.TrainError, "no release notes"):
                train.run_android(dry_run=True, release_date="2026-10-06")
        client.edits().tracks().update.assert_not_called()

    def test_missing_staged_release_file_reports_a_failed_platform_not_a_traceback(self):
        # A staged release with no Play notes and no durable releases/<v>.json:
        # require_notes raises PromotionError, which main() does not catch —
        # the ladder path must convert it so TRAIN SUMMARY reports the failure.
        client = Mock()
        staged = {"name": STALE_RECEIPT_NAME, "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.05}
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes", return_value=Path("/nonexistent/1.0.554.json")):
            with self.assertRaisesRegex(train.TrainError, "no usable What's-New text"):
                train.run_android(dry_run=False, release_date="2026-10-06")
        client.edits().tracks().update.assert_not_called()

    def test_existing_draft_with_the_same_code_is_idempotent(self):
        self.production["releases"].append({"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "draft"})
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "STAGED_ROLLOUT_FRACTION", None):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=leave draft 1.0.554 (1340)")
        client.edits().tracks().update.assert_not_called()

    def test_legacy_draft_converts_into_a_staged_rollout(self):
        self.production["releases"].append({"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "draft"})
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release), patch.object(
                promote, "require_notes", return_value="Faster sync"
            ):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, f"android=staged 1.0.554 (1340) @{train.STAGED_ROLLOUT_FRACTION:.0%}")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "inProgress")
        self.assertEqual(body["releases"][0]["userFraction"], train.STAGED_ROLLOUT_FRACTION)
        client.edits().commit.assert_called_once()

    def test_dry_run_does_not_write_the_track(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes", return_value=Path("unused")):
            summary = train.run_android(dry_run=True, release_date="2026-10-06")
        self.assertEqual(summary, f"android=dry-run:staged 1.0.554 (1340) @{train.STAGED_ROLLOUT_FRACTION:.0%}")
        client.edits().tracks().update.assert_not_called()

    def test_dry_run_reports_a_draft_when_staged_rollouts_are_disabled(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes", return_value=Path("unused")), patch.object(
            train, "STAGED_ROLLOUT_FRACTION", None
        ):
            summary = train.run_android(dry_run=True, release_date="2026-10-06")
        self.assertEqual(summary, "android=dry-run:draft 1.0.554 (1340)")
        client.edits().tracks().update.assert_not_called()

    def test_a_matching_android_pin_still_stages_the_candidate(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / "1.0.554.json"
            release.write_text(json.dumps({"version": "1.0.554", "date": "2026-10-06", "changes": ["Faster sync"]}))
            with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
                promote, "play_track", side_effect=lambda c, e, name: tracks[name]
            ), patch.object(train, "ensure_release_notes", return_value=release), patch.object(
                promote, "require_notes", return_value="Faster sync"
            ), patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": "1.0.554/1340"}):
                summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, f"android=staged 1.0.554 (1340) @{train.STAGED_ROLLOUT_FRACTION:.0%}")
        client.edits().commit.assert_called_once()

    def test_advance_mode_never_stages_a_candidate(self):
        # The watch runs advance-only with no pin; with no rollout in flight and a
        # newer internal build it must not start a production rollout.
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes") as notes, patch.object(promote, "submit_android") as submit:
            summary = train.run_android(dry_run=False, release_date="2026-10-06", advance_only=True)
        self.assertEqual(summary, "android=advance (no staged rollout in flight; candidate 1.0.554 (1340) waits for the gate)")
        submit.assert_not_called()
        notes.assert_not_called()
        client.edits().tracks().update.assert_not_called()
        client.edits().commit.assert_not_called()

    def test_a_drifted_android_pin_fails_closed_before_any_write(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": "1.0.553/1320"}):
            with self.assertRaisesRegex(train.TrainError, "TRAIN_PIN_ANDROID"):
                train.run_android(dry_run=False, release_date="2026-10-06")
        client.edits().tracks().update.assert_not_called()
        client.edits().commit.assert_not_called()

    def test_a_drifted_android_pin_fails_closed_even_in_dry_run(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": "9.9.9/9999"}):
            with self.assertRaisesRegex(train.TrainError, "unaudited"):
                train.run_android(dry_run=True, release_date="2026-10-06")
        client.edits().tracks().update.assert_not_called()

    def test_a_none_pin_over_a_fresh_candidate_fails_closed(self):
        # The gate audited "no Android candidate exists"; a build that appeared
        # in the audit->dispatch gap is unaudited and must not be released.
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": "none"}):
            with self.assertRaisesRegex(train.TrainError, "unaudited"):
                train.run_android(dry_run=False, release_date="2026-10-06")
        client.edits().tracks().update.assert_not_called()

    def test_a_none_pin_with_no_candidate_is_an_audited_no_op(self):
        # Nothing newer than live anywhere: the none verdict matches, android=nothing.
        client = Mock()
        stale = {
            "track": "internal",
            "releases": [{"name": "1.0.552 (1200)", "versionCodes": ["1200"], "status": "completed"}],
        }
        stale_alpha = {"track": "alpha", "releases": [{"name": "1.0.551 (1190)", "versionCodes": ["1190"], "status": "completed"}]}
        tracks = {"internal": stale, "alpha": stale_alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": "none"}):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=nothing (live 1.0.552)")
        client.edits().tracks().update.assert_not_called()

    def test_a_pinned_candidate_that_vanished_fails_closed(self):
        # The gate pinned an audited build the store no longer offers.
        client = Mock()
        stale = {
            "track": "internal",
            "releases": [{"name": "1.0.552 (1200)", "versionCodes": ["1200"], "status": "completed"}],
        }
        stale_alpha = {"track": "alpha", "releases": [{"name": "1.0.551 (1190)", "versionCodes": ["1190"], "status": "completed"}]}
        tracks = {"internal": stale, "alpha": stale_alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": "1.0.554/1340"}):
            with self.assertRaisesRegex(train.TrainError, "no internal/alpha build is newer"):
                train.run_android(dry_run=False, release_date="2026-10-06")
        client.edits().tracks().update.assert_not_called()


class PinTests(unittest.TestCase):
    def test_store_pin_parses_the_gate_identifier(self):
        with patch.dict(train.os.environ, {"TRAIN_PIN_IOS": "1.0.554/1334"}):
            self.assertEqual(train.store_pin("TRAIN_PIN_IOS"), train.StorePin("1.0.554", "1334"))
        with patch.dict(train.os.environ, {"TRAIN_PIN_IOS": " 1.0.554 / 1334 "}):
            self.assertEqual(train.store_pin("TRAIN_PIN_IOS"), train.StorePin("1.0.554", "1334"))
        with patch.dict(train.os.environ, {"TRAIN_PIN_IOS": ""}):
            self.assertIsNone(train.store_pin("TRAIN_PIN_IOS"))

    def test_store_pin_none_encodes_an_audited_no_candidate(self):
        for raw in ("none", "NONE", " none "):
            with patch.dict(train.os.environ, {"TRAIN_PIN_ANDROID": raw}):
                pin = train.store_pin("TRAIN_PIN_ANDROID")
                self.assertTrue(pin.is_none)
                self.assertFalse(pin.matches("1.0.554", "1340"))

    def test_store_pin_malformed_fails_closed(self):
        for bad in ("1.0.554", "1334", "1.0.554/13x4", "v1.0.554/1334", "null", "n/a"):
            with patch.dict(train.os.environ, {"TRAIN_PIN_IOS": bad}):
                with self.assertRaisesRegex(train.TrainError, "X.Y.Z/build or none"):
                    train.store_pin("TRAIN_PIN_IOS")

    def test_a_matching_ios_pin_still_submits(self):
        asc = FakeASC(
            live_responses(
                extra={
                    ("builds", "app-store-version"): {"id": "new-version", "attributes": {"appStoreState": "WAITING_FOR_REVIEW"}},
                    ("app-store-versions", "get"): {"id": "new-version", "attributes": {"appStoreState": "WAITING_FOR_REVIEW"}},
                }
            )
        )

        def fake_run(command, **kwargs):
            return Mock(returncode=0)

        with patch.dict(train.os.environ, CREDENTIALS | {"TRAIN_PIN_IOS": "1.0.554/1334"}), patch.object(
            train, "_asc_rest_token", return_value="faketoken"
        ), patch.object(train, "ios_phased_release_should_complete", return_value=(False, "no phased release")), patch.object(
            train, "ios_phased_release_paused", return_value=False
        ), patch.object(train, "_attach_phased_release"), patch.object(
            promote.subprocess, "run", side_effect=fake_run
        ), patch.object(promote, "require_notes", return_value="- New thing"), patch.object(
            train, "ensure_release_notes"
        ):
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        self.assertTrue(summary.startswith("ios=submit"))

    def test_a_drifted_ios_pin_fails_closed_before_any_mutation(self):
        asc = FakeASC(live_responses())
        with patch.dict(train.os.environ, CREDENTIALS | {"TRAIN_PIN_IOS": "1.0.555/1400"}), patch.object(
            train, "ios_phased_release_should_complete", return_value=(False, "no phased release")
        ), patch.object(train, "ios_phased_release_paused", return_value=False), patch.object(
            promote.subprocess, "run"
        ) as run:
            with self.assertRaisesRegex(train.TrainError, "unaudited"):
                train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        run.assert_not_called()
        self.assertEqual(asc.mutations(), [])


class MainTests(unittest.TestCase):
    def test_summary_line_and_exit_code(self):
        with patch.object(train, "run_ios", return_value="ios=nothing"), patch.object(
            train, "run_android", side_effect=train.TrainError("Play down")
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = train.main(["--platform", "both", "--date", "2026-10-06"])
        self.assertEqual(code, 1)
        self.assertIn("TRAIN SUMMARY: ios=nothing android=FAILED", out.getvalue())
        self.assertIn("FAIL android: Play down", out.getvalue())

    def test_platform_selection(self):
        with patch.object(train, "run_ios", return_value="ios=nothing") as ios, patch.object(train, "run_android") as android:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(train.main(["--platform", "ios", "--date", "2026-10-06"]), 0)
        ios.assert_called_once()
        android.assert_not_called()


class CaptureHealthWiringTests(unittest.TestCase):
    """The two exposure-expanding hops wait on capture health (mobile_capture_health.py)."""

    def test_the_ios_jump_holds_on_capture_health_for_the_exact_store_build(self):
        phased = {"attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased), patch.object(
            train, "ios_version_build_number", return_value="1360"
        ) as lookup, patch.object(train, "capture_health_hold", return_value="more than 2x the previous build") as hold:
            should, reason = train.ios_phased_release_should_complete(
                "live-id", now=datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
            )
        self.assertFalse(should)
        self.assertIn("held on capture health: more than 2x the previous build", reason)
        lookup.assert_called_once_with("live-id")
        hold.assert_called_once_with("ios", build="1360")

    def test_the_ios_jump_inside_its_window_never_queries_capture_health(self):
        phased = {"attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased), patch.object(
            train, "capture_health_hold"
        ) as hold:
            should, _ = train.ios_phased_release_should_complete(
                "x", now=datetime(2026, 1, 1, 5, tzinfo=timezone.utc)
            )
        self.assertFalse(should)
        hold.assert_not_called()

    def test_an_unreadable_store_build_holds_the_jump(self):
        phased = {"attributes": {"phasedReleaseState": "ACTIVE", "startDate": "2026-01-01T00:00:00Z"}}
        with patch.object(train, "ios_phased_release", return_value=phased), patch.object(
            train, "ios_version_build_number", return_value=None
        ), patch.object(train, "capture_health_hold", return_value="no readable build number") as hold:
            should, _ = train.ios_phased_release_should_complete("x", now=datetime(2026, 1, 1, 13, tzinfo=timezone.utc))
        self.assertFalse(should)
        hold.assert_called_once_with("ios", build=None)

    def test_the_store_build_lookup_reads_the_version_build_relationship(self):
        _STORE_BUILD_LOOKUP.stop()
        self.addCleanup(_STORE_BUILD_LOOKUP.start)
        response = io.BytesIO(json.dumps({"data": {"type": "builds", "id": "b", "attributes": {"version": "1417"}}}).encode())
        with patch.object(train, "_asc_rest_token", return_value="jwt"), patch.object(
            train.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            self.assertEqual(train.ios_version_build_number("v-1"), "1417")
        self.assertTrue(urlopen.call_args.args[0].full_url.endswith("/v1/appStoreVersions/v-1/build"))
        with patch.object(train, "_asc_rest_token", side_effect=train.TrainError("no key")), redirect_stdout(io.StringIO()):
            self.assertIsNone(train.ios_version_build_number("v-1"))
        for body in ({"data": {"type": "builds", "id": "b"}}, {"data": {"attributes": "x"}}, {"data": None}, ["x"]):
            response = io.BytesIO(json.dumps(body).encode())
            with patch.object(train, "_asc_rest_token", return_value="jwt"), patch.object(
                train.urllib.request, "urlopen", return_value=response
            ), redirect_stdout(io.StringIO()):
                self.assertIsNone(train.ios_version_build_number("v-1"), body)

    def test_an_android_hop_holds_in_place_on_capture_health(self):
        client = Mock()
        staged = {"name": STALE_RECEIPT_NAME, "versionCodes": ["1340"], "status": "inProgress", "userFraction": 0.10}
        tracks = {
            "internal": {"track": "internal", "releases": []},
            "alpha": {"track": "alpha", "releases": []},
            "production": {"track": "production", "releases": [staged]}}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "capture_health_hold", return_value="capture wedge users above 50/day") as hold:
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=staged 1.0.554 1340 @10% held on capture health (capture wedge users above 50/day)")
        hold.assert_called_once_with("android", build="1340")
        client.edits().tracks().update.assert_not_called()
        client.edits().commit.assert_not_called()

    def test_capture_health_hold_logs_and_returns_the_verdict(self):
        verdict = train.capture_health.Verdict(True, "no PostHog key")
        _CAPTURE_HEALTH_GREEN.stop()
        try:
            with patch.object(train.capture_health, "check_rollout", return_value=verdict), redirect_stdout(io.StringIO()) as out:
                self.assertEqual(train.capture_health_hold("ios", build="1360"), "no PostHog key")
            ok = train.capture_health.Verdict(False, "capture health ok")
            with patch.object(train.capture_health, "check_rollout", return_value=ok), redirect_stdout(io.StringIO()):
                self.assertIsNone(train.capture_health_hold("ios", build="1360"))
        finally:
            _CAPTURE_HEALTH_GREEN.start()
        self.assertIn("ios capture health: no PostHog key", out.getvalue())


class AscKeyNormalizationTest(unittest.TestCase):
    """The REST signer must read the integration key in every shape CI stores it in.

    Live 2026-10-15: on the Codemagic train both cryptography and `openssl dgst`
    rejected the key text the same machine's publishing CLI accepts, so the
    iOS REST surface (phased-release brake reads) failed closed.
    """

    @classmethod
    def setUpClass(cls):
        # Apple's .p8 is PKCS#8 ("BEGIN PRIVATE KEY") on P-256.
        cls.pem = subprocess.run(
            ["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout

    def _signs_with_openssl(self, pem: str) -> bool:
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as key_file:
            key_file.write(pem)
        try:
            result = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", key_file.name], input=b"payload", capture_output=True
            )
            return result.returncode == 0 and len(result.stdout) > 8
        finally:
            Path(key_file.name).unlink()

    def test_every_stored_shape_signs(self):
        import base64

        body = "".join(line for line in self.pem.splitlines() if "-----" not in line)
        shapes = {
            "as-is": self.pem,
            "escaped newlines": self.pem.replace("\n", "\\n"),
            "folded to spaces": self.pem.replace("\n", " "),
            "quoted": '"' + self.pem.replace("\n", "\\n") + '"',
            "bare base64 body": body,
            "base64 of the .p8 file": base64.b64encode(self.pem.encode()).decode(),
            "crlf": self.pem.replace("\n", "\r\n"),
        }
        self.assertTrue(self._signs_with_openssl(self.pem))
        for name, text in shapes.items():
            with self.subTest(shape=name):
                self.assertTrue(self._signs_with_openssl(train._normalize_pem(text)), name)

    def test_codemagic_key_references_resolve_to_a_signing_key(self):
        # Live 2026-10-15: the codemagic_v4 integration's variable was a 72-character
        # single-line reference, not key text.
        with tempfile.NamedTemporaryFile("w", suffix=".p8", delete=False) as key_file:
            key_file.write(self.pem)
        try:
            ref = "@file:" + key_file.name
            self.assertIn("ref=@file", train._pem_shape(ref))
            self.assertTrue(self._signs_with_openssl(train._normalize_pem(train._resolve_key_ref(ref))))
            with unittest.mock.patch.dict(train.os.environ, {"CM_ASC_KEY": ref}):
                resolved = train._resolve_key_ref("@env:CM_ASC_KEY")
            self.assertTrue(self._signs_with_openssl(train._normalize_pem(resolved)))
        finally:
            Path(key_file.name).unlink()
        self.assertEqual(train._resolve_key_ref(self.pem), self.pem)

    def test_unreadable_key_reference_fails_closed(self):
        with self.assertRaises(train.TrainError):
            train._resolve_key_ref("@file:/nonexistent/AuthKey.p8")
        with unittest.mock.patch.dict(train.os.environ, {}, clear=False):
            with self.assertRaises(train.TrainError):
                train._resolve_key_ref("@env:OMI_DEFINITELY_UNSET_KEY")

    def test_garbage_fails_closed_without_echoing_the_key(self):
        with self.assertRaises(train.TrainError) as ctx:
            train._normalize_pem("not a key at all!")
        self.assertIn("len=", str(ctx.exception))
        self.assertNotIn("not a key", str(ctx.exception))

    def test_shape_never_contains_key_material(self):
        shape = train._pem_shape(self.pem)
        body = "".join(line for line in self.pem.splitlines() if "-----" not in line)
        self.assertNotIn(body[:16], shape)
        self.assertIn("armored=True", shape)


if __name__ == "__main__":
    unittest.main()
