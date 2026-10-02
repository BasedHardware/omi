#!/usr/bin/env python3
"""Tests for the mobile internal build dispatch decision."""

import importlib.util
import pathlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "dispatch_mobile_internal_builds",
    pathlib.Path(__file__).with_name("dispatch_mobile_internal_builds.py"),
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

INSTANT = {"mdmohsin7"}
MOBILE_DISTRIBUTION_SCHEMA = "omi-mobile-distribution/v1"


def decide(event, *, actor="someone", authors=(), pending=False, instant=INSTANT):
    return mod.decide_dispatch(
        event=event,
        actor=actor,
        commit_authors=authors,
        instant_actors=instant,
        has_pending_app_commits=pending,
    )


class TestPushEvent(unittest.TestCase):
    def test_an_allowlisted_pusher_builds_immediately(self):
        should, reason = decide("push", actor="mdmohsin7")
        self.assertTrue(should)
        self.assertEqual(reason, "instant-actor")

    def test_matching_is_case_insensitive(self):
        self.assertTrue(decide("push", actor="MDMohsin7")[0])

    def test_an_allowlisted_commit_author_builds_immediately(self):
        # Someone else merged the change, but it is still their commit.
        self.assertTrue(decide("push", actor="other-dev", authors=["mdmohsin7"])[0])

    def test_everyone_else_waits_for_the_batch(self):
        should, reason = decide("push", actor="other-dev", authors=["other-dev"])
        self.assertFalse(should)
        self.assertIn("batched", reason)

    def test_an_empty_allowlist_batches_everyone(self):
        self.assertFalse(decide("push", actor="mdmohsin7", instant=set())[0])


class TestScheduleEvent(unittest.TestCase):
    def test_builds_when_app_changed_since_the_last_build(self):
        should, reason = decide("schedule", pending=True)
        self.assertTrue(should)
        self.assertIn("app changes", reason)

    def test_skips_when_nothing_changed(self):
        should, reason = decide("schedule", pending=False)
        self.assertFalse(should)
        self.assertIn("no app changes", reason)

    def test_the_allowlist_does_not_apply_to_the_batch(self):
        # The batch is decided by pending work, never by who happens to be the actor.
        self.assertFalse(decide("schedule", actor="mdmohsin7", pending=False)[0])


class TestManualAndUnknown(unittest.TestCase):
    def test_manual_always_dispatches(self):
        should, reason = decide("workflow_dispatch", actor="anyone")
        self.assertTrue(should)
        self.assertEqual(reason, "manual")

    def test_an_unknown_event_never_dispatches(self):
        self.assertFalse(decide("pull_request")[0])


class TestActorParsing(unittest.TestCase):
    def test_parses_and_normalizes_a_comma_list(self):
        self.assertEqual(mod.normalized_actors(" MDMohsin7 , someone "), {"mdmohsin7", "someone"})

    def test_empty_input_is_an_empty_set(self):
        self.assertEqual(mod.normalized_actors(None), set())
        self.assertEqual(mod.normalized_actors(" , "), set())


IOS_SHA = "a" * 40
ANDROID_SHA = "b" * 40


def built(
    created,
    sha=IOS_SHA,
    status="finished",
    *,
    platform="ios",
    outcome="distributed",
    verification="verified",
    evidence=True,
):
    build = {"createdAt": created, "commit": sha, "status": status}
    if evidence:
        build["distribution_evidence"] = {
            "schema": MOBILE_DISTRIBUTION_SCHEMA,
            "platform": platform,
            "source_sha": sha,
            "outcome": outcome,
            "verification": verification,
        }
    return build


class TestNewestBuiltSha(unittest.TestCase):
    def test_picks_the_newest_build_regardless_of_list_order(self):
        builds = [built("2026-08-01T09:00:00Z", IOS_SHA), built("2026-08-02T09:00:00Z", "c" * 40)]
        self.assertEqual(mod.newest_built_sha(builds), "c" * 40)
        self.assertEqual(mod.newest_built_sha(list(reversed(builds))), "c" * 40)

    def test_reads_a_nested_commit_object(self):
        self.assertEqual(
            mod.newest_built_sha(
                [
                    {
                        "createdAt": "x",
                        "status": "finished",
                        "commit": {"hash": "d" * 40},
                        "distribution_evidence": {
                            "schema": MOBILE_DISTRIBUTION_SCHEMA,
                            "platform": "ios",
                            "source_sha": "d" * 40,
                            "outcome": "distributed",
                            "verification": "verified",
                        },
                    }
                ]
            ), "d" * 40
        )

    def test_ignores_provider_label_before_valid_source_sha(self):
        sha = "d" * 40
        build = {
            "createdAt": "x",
            "status": "finished",
            "commit": "main",
            "commitHash": sha,
            "distribution_evidence": {
                "schema": MOBILE_DISTRIBUTION_SCHEMA,
                "platform": "ios",
                "source_sha": sha,
                "outcome": "distributed",
                "verification": "verified",
            },
        }
        self.assertEqual(mod.build_sha(build), sha)

    def test_ignores_builds_with_no_commit(self):
        builds = [{"createdAt": "2026-08-03T09:00:00Z", "status": "finished"}, built("2026-08-01T09:00:00Z", "e" * 40)]
        self.assertEqual(mod.newest_built_sha(builds), "e" * 40)

    def test_no_builds_means_no_baseline(self):
        self.assertIsNone(mod.newest_built_sha([]))

    def test_a_failed_build_does_not_become_the_baseline(self):
        # Otherwise a broken merge sits unbuilt until some later app commit happens along.
        builds = [built("2026-08-01T09:00:00Z", "f" * 40), built("2026-08-02T09:00:00Z", "1" * 40, "failed")]
        self.assertEqual(mod.newest_built_sha(builds), "f" * 40)

    def test_a_finished_build_with_a_failed_store_task_does_not_become_the_baseline(self):
        builds = [
            built("2026-08-01T09:00:00Z", "f" * 40),
            built(
                "2026-08-02T09:00:00Z",
                "1" * 40,
                outcome="failed",
                verification="unknown",
            ),
        ]
        self.assertEqual(mod.newest_built_sha(builds), "f" * 40)

    def test_cancelled_and_in_progress_builds_do_not_become_the_baseline(self):
        for status in ("canceled", "cancelled", "timeout", "building", "queued", ""):
            with self.subTest(status=status):
                self.assertIsNone(mod.newest_built_sha([built("2026-08-02T09:00:00Z", "2" * 40, status)]))

    def test_a_skipped_build_is_a_baseline(self):
        # Codemagic looked and decided there was nothing to build; that commit is settled.
        self.assertEqual(
            mod.newest_built_sha(
                [built("2026-08-02T09:00:00Z", "3" * 40, "skipped", outcome="no-op", verification="not_applicable")]
            ),
            "3" * 40,
        )

    def test_status_matching_is_case_insensitive(self):
        self.assertEqual(mod.newest_built_sha([built("2026-08-02T09:00:00Z", "4" * 40, "Finished")]), "4" * 40)

    def test_missing_distribution_evidence_does_not_become_a_baseline(self):
        self.assertIsNone(mod.newest_built_sha([built("x", "5" * 40, evidence=False)]))

    def test_malformed_distribution_evidence_does_not_become_a_baseline(self):
        build = built("x", "5" * 40)
        build["distribution_evidence"]["unexpected"] = "unknown"
        self.assertIsNone(mod.newest_built_sha([build]))

    def test_ios_and_android_baselines_are_independent(self):
        builds = [built("x", ANDROID_SHA, platform="android")]
        self.assertIsNone(mod.newest_built_sha(builds, platform="ios"))
        self.assertEqual(mod.newest_built_sha(builds, platform="android"), ANDROID_SHA)

    def test_mismatched_distribution_source_does_not_become_a_baseline(self):
        build = built("x", "6" * 40)
        build["distribution_evidence"]["source_sha"] = "7" * 40
        self.assertIsNone(mod.newest_built_sha([build]))

    def test_last_built_sha_adapts_codemagic_build_detail(self):
        build_id = "build-1"
        detail = {
            "build": {
                "status": "finished",
                "commit": {"hash": IOS_SHA},
                "buildActions": [{"type": "publishing", "status": "success"}],
            }
        }
        with patch.object(mod, "_api_get", side_effect=[{"builds": [{"_id": build_id}]}, detail]):
            self.assertEqual(mod.last_built_sha("app", "android-internal-auto", "token", platform="android"), IOS_SHA)

    def test_last_built_sha_does_not_adapt_failed_ios_store_task(self):
        detail = {
            "build": {
                "status": "finished",
                "commit": {"hash": IOS_SHA},
                "buildActions": [{"type": "publishing", "status": "success"}],
                "appStoreConnectTasks": [{"status": "failed"}],
            }
        }
        with patch.object(mod, "_api_get", side_effect=[{"builds": [{"_id": "build-1"}]}, detail]):
            self.assertIsNone(mod.last_built_sha("app", "ios-internal-auto", "token", platform="ios"))

    def test_malformed_ios_store_task_does_not_block_android_baseline(self):
        detail = {
            "build": {
                "status": "finished",
                "commit": {"hash": ANDROID_SHA},
                "buildActions": [{"type": "publishing", "status": "success"}],
                "appStoreConnectTasks": [None],
            }
        }
        with patch.object(
            mod,
            "_api_get",
            side_effect=[
                {"builds": [{"_id": "ios-build"}]},
                detail,
                {"builds": [{"_id": "android-build"}]},
                detail,
            ],
        ):
            self.assertIsNone(mod.last_built_sha("app", "ios-internal-auto", "token", platform="ios"))
            self.assertEqual(
                mod.last_built_sha("app", "android-internal-auto", "token", platform="android"),
                ANDROID_SHA,
            )


class TestPendingCommits(unittest.TestCase):
    def test_no_known_baseline_counts_as_pending(self):
        # First ever build, or a pruned SHA: never silently stop building.
        self.assertEqual(mod.app_commits_since(None), ["HEAD"])

    def test_an_unknown_sha_counts_as_pending(self):
        self.assertEqual(mod.app_commits_since("0" * 40), ["HEAD"])

    def test_a_non_ancestor_baseline_counts_as_pending(self):
        # A rewound or rewritten main leaves the baseline off this history: the range would read
        # empty and skip a batch that is genuinely pending.
        head = mod.subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        self.assertTrue(mod.is_ancestor(head))
        # An unresolvable SHA is sufficient to exercise the same fail-open-to-pending branch;
        # creating an orphan commit would mutate the shared worktree's object database.
        orphan = "f" * 40
        self.assertFalse(mod.is_ancestor(orphan))
        self.assertEqual(mod.app_commits_since(orphan), ["HEAD"])


class TestSourceIdentity(unittest.TestCase):
    def test_exact_checkout_source_is_accepted(self):
        sha = "8" * 40
        self.assertTrue(mod.source_identity_matches(sha, sha))

    def test_branch_movement_or_checkout_mismatch_is_rejected(self):
        self.assertFalse(mod.source_identity_matches("9" * 40, "a" * 40))

    def test_dispatch_carries_the_source_pin_to_the_provider(self):
        with patch.object(mod, "_api_post", return_value={"buildId": "build-123"}) as post:
            self.assertEqual(
                mod.dispatch("app", "ios-internal-auto", "secret", "main", "b" * 40),
                "build-123",
            )
        payload = post.call_args.args[2]
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(payload["environment"]["variables"]["OMI_RELEASE_SOURCE_SHA"], "b" * 40)
        self.assertEqual(payload["environment"]["variables"]["OMI_RELEASE_PLATFORM"], "ios")
        self.assertNotIn("secret", repr(payload))

    def test_checkout_movement_is_rejected_before_downstream_dispatch(self):
        with patch.dict(mod.os.environ, {"CODEMAGIC_API_TOKEN": "secret"}), patch.object(
            mod.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="b" * 40 + "\n"),
        ), patch.object(mod, "dispatch") as dispatch:
            with self.assertRaisesRegex(mod.DispatchError, "does not match the checked-out commit"):
                mod.main(
                    [
                        "--event",
                        "workflow_dispatch",
                        "--app-id",
                        "app",
                        "--source-sha",
                        "a" * 40,
                    ]
                )
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
