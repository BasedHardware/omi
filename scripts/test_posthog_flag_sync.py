#!/usr/bin/env python3
"""Hermetic tests for scripts/posthog_flag_sync.py — HTTP layer stubbed."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
import urllib.request
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import posthog_flag_sync as sync  # noqa: E402

ENV = {
    "POSTHOG_PERSONAL_API_KEY": "token-1",
    "POSTHOG_HOST": "https://us.posthog.com",
    "POSTHOG_PROJECT_ID": "302298",
}


def flag(key: str, role: str = "enable", row: str = "expected", **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "key": key,
        "aliases": [],
        "kind": "posthog",
        "lifecycle": "rollout",
        "surfaces": ["backend"],
        "summary": "Fixture gate",
        "fail": "closed",
        "owner": "unowned",
        "created": "2026-08-01",
        "review_by": "2026-10-15",
        "decision": "pending",
        "posthog": {"row": row, "role": role},
    }
    entry.update(overrides)
    if entry["kind"] != "posthog":
        entry.pop("posthog", None)
    return entry


def registry(flags: list[dict[str, object]], retired: list[dict[str, object]] | None = None) -> dict[str, list[dict[str, object]]]:
    return {"flags": flags, "ignore": [], "retired": retired or []}


def retired(key: str) -> dict[str, object]:
    return {"key": key, "kind": "posthog", "retired": "2026-09-24", "reason": "x", "posthog": {"row": "delete"}}


def armed_kill(key: str) -> dict[str, object]:
    return {
        "key": key,
        "active": True,
        "filters": {"groups": [{"properties": [], "rollout_percentage": 0}]},
    }


class ListFeatureFlagsTest(unittest.TestCase):
    def test_paginates_by_offset_and_never_follows_next_url(self) -> None:
        requested: list[str] = []
        pages = [
            {"results": [{"key": "a"}, {"key": "b"}], "next": "https://attacker.example/next"},
            {"results": [{"key": "c"}], "next": None},
        ]

        def transport(request: urllib.request.Request) -> dict[str, object]:
            requested.append(request.full_url)
            self.assertEqual(request.headers["Authorization"], "Bearer token-1")
            return pages[len(requested) - 1]

        rows = sync.list_feature_flags("https://us.posthog.com/", "302298", "token-1", transport=transport)

        self.assertEqual([row["key"] for row in rows], ["a", "b", "c"])
        self.assertEqual(len(requested), 2)
        self.assertEqual(
            requested[0],
            "https://us.posthog.com/api/projects/302298/feature_flags/?limit=100&offset=0",
        )
        self.assertEqual(
            requested[1],
            "https://us.posthog.com/api/projects/302298/feature_flags/?limit=100&offset=2",
        )
        self.assertNotIn("attacker.example", requested[1])

    def test_single_page_when_next_is_null(self) -> None:
        def transport(request: urllib.request.Request) -> dict[str, object]:
            return {"results": [{"key": "a"}], "next": None}

        rows = sync.list_feature_flags("https://us.posthog.com", "1", "t", transport=transport)
        self.assertEqual(len(rows), 1)

    def test_empty_results_with_nonnull_next_fails_instead_of_looping(self) -> None:
        calls: list[str] = []

        def transport(request: urllib.request.Request) -> dict[str, object]:
            calls.append(request.full_url)
            return {"results": [], "next": "https://api.example/more"}

        with self.assertRaises(sync.SyncError):
            sync.list_feature_flags("https://us.posthog.com", "1", "t", transport=transport)
        self.assertEqual(len(calls), 1)

    def test_invalid_host_and_project_rejected_before_any_http(self) -> None:
        called = False

        def transport(request: urllib.request.Request) -> dict[str, object]:
            nonlocal called
            called = True
            return {"results": [], "next": None}

        for host in (
            "http://us.posthog.com",
            "https://user:secret@us.posthog.com",
            "https://us.posthog.com/some/path",
            "us.posthog.com",
            "https://us.posthog.com/?x=1",
        ):
            with self.subTest(host=host), self.assertRaises(sync.SyncError):
                sync.list_feature_flags(host, "302298", "t", transport=transport)
        for project in ("abc", "", "302298a"):
            with self.subTest(project=project), self.assertRaises(sync.SyncError):
                sync.list_feature_flags("https://us.posthog.com", project, "t", transport=transport)
            with self.subTest(project=project, post=True), self.assertRaises(sync.SyncError):
                sync.create_kill_row("https://us.posthog.com", project, "t", "k", transport=transport)
        self.assertFalse(called)


class ArmedKillShapeTest(unittest.TestCase):
    def test_armed_kill_requires_active_single_zero_percent_group(self) -> None:
        self.assertTrue(sync.is_armed_kill(armed_kill("k")))
        self.assertFalse(sync.is_armed_kill({**armed_kill("k"), "active": False}))
        nonzero = armed_kill("k")
        nonzero["filters"]["groups"][0]["rollout_percentage"] = 50
        self.assertFalse(sync.is_armed_kill(nonzero))
        propped = armed_kill("k")
        propped["filters"]["groups"][0]["properties"] = [{"key": "x"}]
        self.assertFalse(sync.is_armed_kill(propped))

    def test_malformed_group_data_returns_false_not_raises(self) -> None:
        malformed = [
            {"key": "k", "active": True, "filters": "nope"},
            {"key": "k", "active": True, "filters": {"groups": "nope"}},
            {"key": "k", "active": True, "filters": {"groups": {"0": {}}}},
            {"key": "k", "active": True, "filters": {"groups": [42]}},
            {"key": "k", "active": True, "filters": {"groups": [None]}},
            {
                "key": "k",
                "active": True,
                "filters": {
                    "groups": [
                        {"properties": [], "rollout_percentage": 0},
                        {"properties": [], "rollout_percentage": 0},
                    ]
                },
            },
            {"key": "k", "active": True},
        ]
        for row in malformed:
            with self.subTest(row=row):
                self.assertFalse(sync.is_armed_kill(row))


class DiffRowsTest(unittest.TestCase):
    def test_classifies_expected_missing_unregistered_kill_and_retired(self) -> None:
        reg = registry(
            [
                flag("missing-enable", role="enable", row="expected"),
                flag("armed-kill", role="kill", row="expected"),
                flag("broken-kill", role="kill", row="expected"),
                flag("must-be-absent", role="enable", row="absent"),
                flag("kill-decision", role="kill", row="expected", decision="kill"),
                flag("env-only", kind="env"),
            ],
            retired=[retired("old-row")],
        )
        rows = [
            armed_kill("armed-kill"),
            {"key": "broken-kill", "active": False, "filters": {"groups": []}},
            armed_kill("must-be-absent"),
            armed_kill("kill-decision"),
            armed_kill("old-row"),
            armed_kill("stray-row"),
        ]
        diff = sync.diff_rows(reg, rows)
        self.assertEqual(diff.expected_missing, ["missing-enable"])
        self.assertEqual(diff.unexpected_present, ["must-be-absent"])
        self.assertEqual(diff.malformed_kills, ["broken-kill"])
        self.assertEqual(diff.unarmed_or_unknown, ["broken-kill"])
        self.assertEqual(diff.present_decision_kill, ["kill-decision"])
        self.assertEqual(diff.retired_present, ["old-row"])
        self.assertEqual(diff.present_unregistered, ["stray-row"])

    def test_missing_kill_is_unarmed_or_unknown_as_well_as_expected_missing(self) -> None:
        reg = registry([flag("gone-kill", role="kill", row="expected")])
        diff = sync.diff_rows(reg, [])
        self.assertEqual(diff.expected_missing, ["gone-kill"])
        self.assertEqual(diff.unarmed_or_unknown, ["gone-kill"])
        self.assertEqual(diff.malformed_kills, [])


class MissingKillsTest(unittest.TestCase):
    def test_only_expected_kill_rows_are_creatable(self) -> None:
        reg = registry(
            [
                flag("need-kill", role="kill", row="expected"),
                flag("already-kill", role="kill", row="expected"),
                flag("need-enable", role="enable", row="expected"),
                flag("want-absent", role="kill", row="absent"),
            ]
        )
        rows = [armed_kill("already-kill")]
        self.assertEqual(sync.missing_kill_keys(reg, rows), ["need-kill"])


class ApplyTest(unittest.TestCase):
    def test_apply_prints_all_writes_before_any_post_and_posts_only_missing_kills(self) -> None:
        reg = registry(
            [
                flag("need-kill-a", role="kill", row="expected"),
                flag("need-kill-b", role="kill", row="expected"),
                flag("already-kill", role="kill", row="expected"),
                flag("need-enable", role="enable", row="expected"),
            ]
        )
        stdout = io.StringIO()
        posts: list[tuple[str, dict[str, object]]] = []

        def fake_transport(request: urllib.request.Request) -> dict[str, object]:
            if request.data is not None:
                body = json.loads(request.data)
                if not posts:
                    captured = stdout.getvalue()
                    planned = captured.split("planned writes:")[-1]
                    self.assertIn("POST https://us.posthog.com/api/projects/302298/feature_flags/", planned)
                    self.assertIn("need-kill-a", planned)
                    self.assertIn("need-kill-b", planned)
                posts.append((request.full_url, body))
                return {"key": body["key"]}
            return {"results": [armed_kill("already-kill")], "next": None}

        argv = ["posthog_flag_sync.py", "--apply-missing-kills"]
        with (
            mock.patch.object(sync, "_default_transport", side_effect=fake_transport),
            mock.patch.dict(os.environ, ENV, clear=False),
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(sync, "_parse_yaml_subset", return_value=reg),
            contextlib.redirect_stdout(stdout),
        ):
            code = sync.main()

        self.assertEqual(code, 0)
        self.assertEqual(len(posts), 2)
        for url, body in posts:
            self.assertEqual(url, "https://us.posthog.com/api/projects/302298/feature_flags/")
            self.assertEqual(
                body,
                {
                    "key": body["key"],
                    "name": body["key"],
                    "active": True,
                    "filters": {"groups": [{"properties": [], "rollout_percentage": 0}]},
                },
            )
        self.assertEqual({body["key"] for _, body in posts}, {"need-kill-a", "need-kill-b"})

    def test_default_mode_is_read_only(self) -> None:
        reg = registry([flag("need-kill", role="kill", row="expected")])

        def fake_transport(request: urllib.request.Request) -> dict[str, object]:
            self.assertIsNone(request.data)
            return {"results": [], "next": None}

        stdout = io.StringIO()
        with (
            mock.patch.object(sync, "_default_transport", side_effect=fake_transport),
            mock.patch.dict(os.environ, ENV, clear=False),
            mock.patch.object(sys, "argv", ["posthog_flag_sync.py"]),
            mock.patch.object(sync, "_parse_yaml_subset", return_value=reg),
            contextlib.redirect_stdout(stdout),
        ):
            code = sync.main()

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("expected but missing: need-kill", output)
        self.assertIn("kill rows unarmed or unknown", output)
        self.assertIn("need-kill", output.split("kill rows unarmed or unknown")[1].splitlines()[0])
        self.assertNotIn("planned writes:", output)


if __name__ == "__main__":
    unittest.main()
