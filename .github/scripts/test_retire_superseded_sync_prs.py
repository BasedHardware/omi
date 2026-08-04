#!/usr/bin/env python3
"""Unit tests for retire-superseded-sync-prs.py (#10727).

Guards the Windows release sync-PR cleanup: the current release PR must always
be retained, only same-repo `release/windows-v*` heads may be closed, and the
gh drive must never raise (cleanup is best-effort after the release is tagged).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from retire_superseded_sync_prs import (  # noqa: E402
    SyncPullRequest,
    list_open_prs_args,
    parse_listed_prs,
    select_superseded,
)


class SelectSupersededTests(unittest.TestCase):
    def test_current_pr_is_retained(self) -> None:
        prs = [
            SyncPullRequest(number=10419, head_ref="release/windows-v1.0.3"),
            SyncPullRequest(number=10960, head_ref="release/windows-v1.0.30"),
        ]
        selected = select_superseded(prs, current_number=10960, prefix="release/windows-v")
        self.assertEqual([pr.number for pr in selected], [10419])

    def test_unrelated_heads_are_never_selected(self) -> None:
        prs = [
            SyncPullRequest(number=99999, head_ref="unrelated/feature"),
            SyncPullRequest(number=88888, head_ref="release/windows-v1.0.3"),
        ]
        selected = select_superseded(prs, current_number=10960, prefix="release/windows-v")
        self.assertEqual([pr.number for pr in selected], [88888])

    def test_empty_and_single_pr_cases(self) -> None:
        self.assertEqual(select_superseded([], current_number=1, prefix="release/windows-v"), [])
        only = [SyncPullRequest(number=1, head_ref="release/windows-v1.0.1")]
        self.assertEqual(select_superseded(only, current_number=1, prefix="release/windows-v"), [])

    def test_prefix_must_be_head_prefix_not_contains(self) -> None:
        # A head named "my-release/windows-v-something" must not match.
        prs = [SyncPullRequest(number=42, head_ref="my-release/windows-v-something")]
        self.assertEqual(select_superseded(prs, current_number=1, prefix="release/windows-v"), [])

    def test_fork_prs_are_never_closed(self) -> None:
        # A fork-origin PR that happens to use a release/windows-v* branch name
        # must not be retired by this release job (it only manages same-repo
        # sync PRs), even though its head matches the prefix.
        prs = [
            SyncPullRequest(number=10419, head_ref="release/windows-v1.0.3"),
            SyncPullRequest(number=70000, head_ref="release/windows-v1.0.7", is_cross_repository=True),
            SyncPullRequest(number=10960, head_ref="release/windows-v1.0.30"),
        ]
        selected = select_superseded(prs, current_number=10960, prefix="release/windows-v")
        self.assertEqual([pr.number for pr in selected], [10419])


class ListOpenPrsQueryTests(unittest.TestCase):
    def test_list_args_do_not_use_head_search_qualifier(self) -> None:
        # Regression for the review blocker: `gh pr list --search head:release/windows-v`
        # returns zero same-repo results, so listing must be open + local prefix filter.
        args = list_open_prs_args(base="main")
        self.assertNotIn("--search", args)
        self.assertFalse(any(a.startswith("head:") for a in args))
        self.assertEqual(
            args,
            [
                "pr",
                "list",
                "--base",
                "main",
                "--state",
                "open",
                "--json",
                "number,headRefName,isCrossRepository",
                "--limit",
                "100",
            ],
        )

    def test_parse_listed_prs_keeps_cross_repo_flag(self) -> None:
        payload = (
            '[{"number":1,"headRefName":"release/windows-v1.0.1","isCrossRepository":false},'
            '{"number":2,"headRefName":"release/windows-v9.9.9","isCrossRepository":true}]'
        )
        prs = parse_listed_prs(payload)
        self.assertEqual(
            prs,
            [
                SyncPullRequest(number=1, head_ref="release/windows-v1.0.1", is_cross_repository=False),
                SyncPullRequest(number=2, head_ref="release/windows-v9.9.9", is_cross_repository=True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
