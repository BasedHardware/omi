#!/usr/bin/env python3
"""Offline contract tests for the daily mobile release train."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

_SPEC = importlib.util.spec_from_file_location("mobile_daily_train", Path(__file__).with_name("mobile_daily_train.py"))
train = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = train
_SPEC.loader.exec_module(train)
promote = train.promote

CREDENTIALS = {
    "APP_STORE_CONNECT_ISSUER_ID": "issuer",
    "APP_STORE_CONNECT_KEY_IDENTIFIER": "key",
    "APP_STORE_CONNECT_PRIVATE_KEY": "secret",
}


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
        self.assertIsNone(plan.reject)

    def test_no_newer_build_does_nothing(self):
        self.assertEqual(train.plan_ios(self.state(candidate=None)).action, "nothing")

    def test_pending_with_newest_build_is_left_for_a_human(self):
        pending = train.IOSVersion("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        plan = train.plan_ios(self.state(pending=(pending,), candidate_version_id="pend"))
        self.assertEqual(plan.action, "leave")
        self.assertIsNone(plan.reject)

    def test_pending_with_older_build_is_replaced(self):
        pending = train.IOSVersion("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        plan = train.plan_ios(self.state(pending=(pending,), candidate_version_id=None))
        self.assertEqual(plan.action, "replace")
        self.assertEqual(plan.reject, pending)
        self.assertEqual(plan.submit, self.candidate)

    def test_pending_newer_than_testflight_is_never_rejected(self):
        pending = train.IOSVersion("pend", "1.0.560", "PENDING_DEVELOPER_RELEASE")
        with self.assertRaisesRegex(train.TrainError, "refusing to reject"):
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
        with patch.object(promote.subprocess, "run") as run:
            summary = train.run_ios(dry_run=True, release_date="2026-10-06", asc=asc)
        self.assertIn("dry-run:submit 1.0.554 (1334)", summary)
        self.assertEqual(asc.mutations(), [])
        run.assert_not_called()

    def test_hold_never_touches_notes_or_stores(self):
        asc = FakeASC(live_responses(states={"IN_REVIEW": [version("v", "1.0.554", "IN_REVIEW")]}))
        with patch.object(promote.subprocess, "run") as run:
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        self.assertTrue(summary.startswith("ios=hold"))
        run.assert_not_called()
        self.assertEqual(asc.mutations(), [])

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

        with patch.object(promote.subprocess, "run", side_effect=fake_run), patch.object(train.time, "sleep"), patch.object(
            promote, "require_notes", return_value="- New thing"
        ):
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=asc)
        command = captured["command"]
        self.assertEqual(command[:3], ["app-store-connect", "builds", "submit-to-app-store"])
        self.assertEqual(command[command.index("--release-type") + 1], "MANUAL")
        self.assertIn("--no-phased-release", command)
        self.assertNotIn("--cancel-previous-submissions", command)
        self.assertNotIn("--whats-new", command)
        self.assertEqual(command[-1], "b1334")
        self.assertEqual(captured["localizations"], [{"locale": "en-US", "whats_new": "- New thing"}, {"locale": "fr-FR", "whats_new": "- New thing"}])
        self.assertEqual(summary, "ios=submit 1.0.554 (1334) WAITING_FOR_REVIEW")
        self.assertEqual([c for c in asc.calls if c[:2] == ("review-submissions", "cancel")], [])

    def test_replace_cancels_the_completed_submission_before_submitting(self):
        pending = version("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE")
        get_states = iter(["PENDING_DEVELOPER_RELEASE", "DEVELOPER_REJECTED", "WAITING_FOR_REVIEW"])
        order = []

        def build_version(args):
            # Candidate build 1335 was never submitted (the pending version carries 1334);
            # after the submission it is attached to the new App Store version.
            return {"id": "v-new", "attributes": {}} if "submit" in order else None

        asc = FakeASC(
            live_responses(
                states={"PENDING_DEVELOPER_RELEASE": [pending]},
                builds={"1.0.554": [build("b1335", "1335"), build("b1334", "1334")]},
                extra={
                    ("builds", "app-store-version"): build_version,
                    ("apps", "list-review-submissions"): [
                        {"id": "rs-old", "attributes": {"state": "COMPLETE", "submittedDate": "2026-09-01T00:00:00Z"}},
                        {"id": "rs-new", "attributes": {"state": "COMPLETE", "submittedDate": "2026-10-01T00:00:00Z"}},
                    ],
                    ("review-submissions", "items"): lambda args: [
                        {"id": "i", "attributes": {"state": "ACCEPTED"}, "relationships": {"appStoreVersion": {"data": {"id": "pend" if args[-1] == "rs-new" else "older"}}}}
                    ],
                    ("review-submissions", "cancel"): {"id": "rs-new", "attributes": {"state": "CANCELING"}},
                    ("app-store-versions", "get"): lambda args: {"id": args[-1], "attributes": {"appStoreState": next(get_states)}},
                }
            )
        )

        def fake_run(command, **kwargs):
            order.append("submit")
            return Mock(returncode=0)

        original_call = asc.__call__

        def recording_call(*args):
            if args[:2] == ("review-submissions", "cancel"):
                order.append("cancel")
            return original_call(*args)

        with patch.object(promote.subprocess, "run", side_effect=fake_run), patch.object(train.time, "sleep"):
            summary = train.run_ios(dry_run=False, release_date="2026-10-06", asc=recording_call)
        self.assertEqual(order, ["cancel", "submit"])
        self.assertIn(("review-submissions", "cancel", "rs-new"), asc.calls)
        self.assertNotIn(("review-submissions", "cancel", "rs-old"), asc.calls)
        self.assertTrue(summary.startswith("ios=replace 1.0.554 (1335)"))

    def test_rejection_that_does_not_reach_developer_rejected_fails_loudly(self):
        asc = FakeASC(
            {
                ("apps", "list-review-submissions"): [{"id": "rs", "attributes": {"state": "COMPLETE", "submittedDate": "x"}}],
                ("review-submissions", "items"): [{"id": "i", "attributes": {}, "relationships": {"appStoreVersion": {"data": {"id": "pend"}}}}],
                ("review-submissions", "cancel"): {"id": "rs", "attributes": {}},
                ("app-store-versions", "get"): {"id": "pend", "attributes": {"appStoreState": "PENDING_DEVELOPER_RELEASE"}},
            }
        )
        with patch.object(train, "STATE_POLL_ATTEMPTS", 2), patch.object(train.time, "sleep"):
            with self.assertRaisesRegex(train.TrainError, "did not reach DEVELOPER_REJECTED"):
                train.reject_pending_ios(asc, train.IOSVersion("pend", "1.0.554", "PENDING_DEVELOPER_RELEASE"))

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

    def test_draft_is_written_from_the_source_track_and_never_completed(self):
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
        self.assertEqual(summary, "android=draft 1.0.554 (1340)")
        body = client.edits().tracks().update.call_args.kwargs["body"]
        self.assertEqual(body["releases"][0]["status"], "draft")
        self.assertEqual(body["releases"][0]["versionCodes"], ["1340"])
        self.assertEqual(body["releases"][0]["name"], "1.0.554")
        self.assertEqual(body["releases"][0]["releaseNotes"], [{"language": "en-US", "text": "Faster sync"}])
        client.edits().commit.assert_called_once()

    def test_existing_draft_with_the_same_code_is_idempotent(self):
        self.production["releases"].append({"name": "1.0.554 (1340)", "versionCodes": ["1340"], "status": "draft"})
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ):
            summary = train.run_android(dry_run=False, release_date="2026-10-06")
        self.assertEqual(summary, "android=leave draft 1.0.554 (1340)")
        client.edits().tracks().update.assert_not_called()

    def test_dry_run_does_not_write_the_track(self):
        client = Mock()
        tracks = {"internal": self.internal, "alpha": self.alpha, "production": self.production}
        with patch.object(promote, "play_edit", return_value=(client, "edit")), patch.object(
            promote, "play_track", side_effect=lambda c, e, name: tracks[name]
        ), patch.object(train, "ensure_release_notes", return_value=Path("unused")):
            summary = train.run_android(dry_run=True, release_date="2026-10-06")
        self.assertEqual(summary, "android=dry-run:draft 1.0.554 (1340)")
        client.edits().tracks().update.assert_not_called()


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


if __name__ == "__main__":
    unittest.main()
