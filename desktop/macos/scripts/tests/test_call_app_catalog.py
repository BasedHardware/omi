#!/usr/bin/env python3
"""Tests for desktop/macos/scripts/call-app-catalog/score.py (stdlib unittest)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCORE = Path(__file__).resolve().parents[1] / "call-app-catalog" / "score.py"
spec = importlib.util.spec_from_file_location("call_app_catalog_score", SCORE)
score = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = score
spec.loader.exec_module(score)

NATIVE = {"us.zoom.xos", "com.hnc.discord", "com.hnc.discordptb", "com.tdesktop.telegram"}
BROWSERS = ["com.google.chrome", "com.apple.safari"]


def catalog(listed=("us.zoom.xos",)):
    return {
        "schema_version": 1,
        "thresholds": {
            "window_days": 14,
            "min_users": 10,
            "min_call_like_sessions": 30,
            "min_classified_releases": 30,
            "max_mute_like_ratio_to_add": 0.02,
            "min_mute_like_ratio_to_remove": 0.1,
            "candidate_min_users": 5,
            "candidate_min_call_like_sessions": 20,
        },
        "release_ends_call": [{"bundle_id": b, "added": "2026-09-26", "source": "probe", "evidence": "x"} for b in listed],
    }


def row(bundle, users=12, calls=40, call_end=40, mute_like=0, device_switch=0):
    return {"bundle_id": bundle, "users": users, "call_like_sessions": calls,
            "releases_call_end": call_end, "releases_mute_like": mute_like,
            "releases_device_switch": device_switch}


def board(*rows, listed=("us.zoom.xos",)):
    data = {"window_days": 14, "fetched_at": "2026-10-05T02:00:00+00:00", "total_users": 90, "rows": list(rows)}
    return score.score(data, catalog(listed), NATIVE, BROWSERS)


def verdicts(b):
    return {a["bundle_id"]: a["verdict"] for a in b["apps"]}


class ScoringTests(unittest.TestCase):
    def test_native_app_with_clean_releases_is_proposed(self):
        b = board(row("com.tdesktop.telegram", call_end=60, mute_like=1))
        self.assertEqual(b["add"], ["com.tdesktop.telegram"])

    def test_mute_like_releases_block_an_addition(self):
        b = board(row("com.tdesktop.telegram", call_end=50, mute_like=5))
        self.assertEqual(verdicts(b)["com.tdesktop.telegram"], "not_eligible")
        self.assertEqual(b["add"], [])

    def test_too_few_users_or_calls_waits(self):
        self.assertEqual(verdicts(board(row("com.tdesktop.telegram", users=9)))["com.tdesktop.telegram"], "waiting")
        self.assertEqual(verdicts(board(row("com.tdesktop.telegram", calls=29)))["com.tdesktop.telegram"], "waiting")
        self.assertEqual(
            verdicts(board(row("com.tdesktop.telegram", call_end=20, mute_like=0)))["com.tdesktop.telegram"], "waiting")

    def test_device_switches_do_not_count_against_an_app(self):
        b = board(row("com.tdesktop.telegram", call_end=40, mute_like=0, device_switch=30))
        self.assertEqual(b["add"], ["com.tdesktop.telegram"])

    def test_helper_rows_resolve_to_their_app(self):
        b = board(row("com.hnc.discord.helper.renderer"))
        self.assertEqual(b["add"], ["com.hnc.discord"])
        self.assertEqual(score.resolve_native("com.hnc.discordptb.helper", NATIVE), "com.hnc.discordptb")
        self.assertIsNone(score.resolve_native("com.hnc.discordian", NATIVE))

    def test_listed_app_that_turns_mute_like_is_proposed_for_removal(self):
        b = board(row("us.zoom.xos", call_end=40, mute_like=10))
        self.assertEqual(b["remove"], ["us.zoom.xos"])

    def test_listed_app_stays_when_confirmed_or_quiet(self):
        self.assertEqual(verdicts(board(row("us.zoom.xos")))["us.zoom.xos"], "confirmed")
        self.assertEqual(verdicts(board())["us.zoom.xos"], "listed")

    def test_unknown_call_like_app_is_a_candidate_never_an_addition(self):
        b = board(row("com.example.around", users=6, calls=25))
        self.assertEqual(verdicts(b)["com.example.around"], "candidate")
        self.assertEqual(b["add"], [])

    def test_browsers_and_omi_are_ignored(self):
        b = board(row("com.google.chrome.helper"), row("com.omi.computer-macos.beta"))
        self.assertEqual(set(verdicts(b).values()) - {"listed"}, {"ignored"})
        self.assertEqual(b["add"], [])

    def test_report_names_every_proposal(self):
        b = board(row("com.tdesktop.telegram"), row("us.zoom.xos", mute_like=10))
        text = score.report(b, catalog())
        self.assertIn("PROPOSE ADD com.tdesktop.telegram", text)
        self.assertIn("PROPOSE REMOVE us.zoom.xos", text)
        self.assertNotIn("No catalog change proposed.", text)


class SwiftBlockTests(unittest.TestCase):
    def test_generated_block_round_trips(self):
        source = "enum X {\n" + score.generated_block(["us.zoom.xos", "com.tdesktop.telegram"]) + "\n}\n"
        self.assertEqual(score.swift_block_ids(source), ["com.tdesktop.telegram", "us.zoom.xos"])

    def test_checked_in_catalog_matches_the_swift_policy(self):
        swift = sorted(score.swift_block_ids(score.SWIFT_POLICY.read_text()))
        self.assertEqual(swift, sorted(score.catalog_ids(score.load_catalog())))

    def test_swift_catalogs_parse(self):
        native = score.native_call_ids()
        self.assertIn("us.zoom.xos", native)
        self.assertIn("com.hnc.discord", native)
        self.assertIn("com.tdesktop.telegram", native)
        self.assertIn("com.google.chrome", score.browser_prefixes())


class ApplyTests(unittest.TestCase):
    def test_apply_updates_catalog_swift_changelog_and_pr_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            originals = (score.CATALOG, score.SWIFT_POLICY, score.CHANGELOG_DIR)
            try:
                score.CATALOG = tmp / "catalog.json"
                score.CATALOG.write_text(json.dumps(catalog()))
                score.SWIFT_POLICY = tmp / "Policy.swift"
                score.SWIFT_POLICY.write_text("enum P {\n" + score.generated_block(["us.zoom.xos"]) + "\n}\n")
                score.CHANGELOG_DIR = tmp
                b = board(row("com.tdesktop.telegram"))
                changed = score.apply(b, score.load_catalog(score.CATALOG), "2026-10-05", tmp / "body.md")
                self.assertEqual(len(changed), 3)
                self.assertEqual(
                    score.swift_block_ids(score.SWIFT_POLICY.read_text()), ["com.tdesktop.telegram", "us.zoom.xos"])
                entry = [e for e in json.loads(score.CATALOG.read_text())["release_ends_call"]
                         if e["bundle_id"] == "com.tdesktop.telegram"][0]
                self.assertEqual(entry["source"], "telemetry")
                self.assertIn("12 users", entry["evidence"])
                self.assertIn("com.tdesktop.telegram", (tmp / "20261005-call-app-catalog.json").read_text())
                body = (tmp / "body.md").read_text()
                self.assertIn("## Product invariants affected", body)
                self.assertIn("`com.tdesktop.telegram` | add", body)
            finally:
                score.CATALOG, score.SWIFT_POLICY, score.CHANGELOG_DIR = originals

    def test_apply_without_proposals_changes_nothing(self):
        self.assertEqual(score.apply(board(row("us.zoom.xos")), catalog(), "2026-10-05", Path("/nonexistent")), [])


if __name__ == "__main__":
    unittest.main()
