#!/usr/bin/env python3
"""Tests for the mobile internal build dispatch decision."""

import importlib.util
import os
import pathlib
import unittest

SPEC = importlib.util.spec_from_file_location(
    "dispatch_mobile_internal_builds",
    pathlib.Path(__file__).with_name("dispatch_mobile_internal_builds.py"),
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

INSTANT = {"mdmohsin7"}


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


def built(created, sha, status="finished"):
    return {"createdAt": created, "commit": sha, "status": status}


class TestNewestBuiltSha(unittest.TestCase):
    def test_picks_the_newest_build_regardless_of_list_order(self):
        builds = [built("2026-08-01T09:00:00Z", "old"), built("2026-08-02T09:00:00Z", "new")]
        self.assertEqual(mod.newest_built_sha(builds), "new")
        self.assertEqual(mod.newest_built_sha(list(reversed(builds))), "new")

    def test_reads_a_nested_commit_object(self):
        self.assertEqual(
            mod.newest_built_sha([{"createdAt": "x", "status": "finished", "commit": {"hash": "abc"}}]), "abc"
        )

    def test_ignores_builds_with_no_commit(self):
        builds = [{"createdAt": "2026-08-03T09:00:00Z", "status": "finished"}, built("2026-08-01T09:00:00Z", "only")]
        self.assertEqual(mod.newest_built_sha(builds), "only")

    def test_no_builds_means_no_baseline(self):
        self.assertIsNone(mod.newest_built_sha([]))

    def test_a_failed_build_does_not_become_the_baseline(self):
        # Otherwise a broken merge sits unbuilt until some later app commit happens along.
        builds = [built("2026-08-01T09:00:00Z", "good"), built("2026-08-02T09:00:00Z", "broken", "failed")]
        self.assertEqual(mod.newest_built_sha(builds), "good")

    def test_cancelled_and_in_progress_builds_do_not_become_the_baseline(self):
        for status in ("canceled", "cancelled", "timeout", "building", "queued", ""):
            with self.subTest(status=status):
                self.assertIsNone(mod.newest_built_sha([built("2026-08-02T09:00:00Z", "x", status)]))

    def test_a_skipped_build_is_a_baseline(self):
        # Codemagic looked and decided there was nothing to build; that commit is settled.
        self.assertEqual(mod.newest_built_sha([built("2026-08-02T09:00:00Z", "x", "skipped")]), "x")

    def test_status_matching_is_case_insensitive(self):
        self.assertEqual(mod.newest_built_sha([built("2026-08-02T09:00:00Z", "x", "Finished")]), "x")


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
        git_env = os.environ.copy()
        git_env.update(
            {
                "GIT_AUTHOR_EMAIL": "mobile-cadence-test@example.com",
                "GIT_AUTHOR_NAME": "mobile-cadence-test",
                "GIT_COMMITTER_EMAIL": "mobile-cadence-test@example.com",
                "GIT_COMMITTER_NAME": "mobile-cadence-test",
            }
        )
        orphan = mod.subprocess.run(
            ["git", "commit-tree", head + "^{tree}", "-m", "orphan"],
            capture_output=True,
            text=True,
            check=True,
            env=git_env,
        ).stdout.strip()
        self.assertFalse(mod.is_ancestor(orphan))
        self.assertEqual(mod.app_commits_since(orphan), ["HEAD"])


if __name__ == "__main__":
    unittest.main()
