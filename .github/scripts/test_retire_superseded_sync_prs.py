#!/usr/bin/env python3
"""Unit tests for retire-superseded-sync-prs.py (#10727).

Guards the Windows release sync-PR cleanup: the current release PR must always
be retained, only same-repo `release/windows-v*` heads may be closed, and the
gh drive must never raise (cleanup is best-effort after the release is tagged).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from retire_superseded_sync_prs import (  # noqa: E402
    LIST_PAGE_SIZE,
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
    def test_list_args_use_exhaustive_api_pagination(self) -> None:
        # Regression: `gh pr list --search head:…` returns zero same-repo results,
        # and `gh pr list --limit 100` truncates when main has >100 open PRs.
        args = list_open_prs_args(repository="BasedHardware/omi", base="main")
        self.assertNotIn("--search", args)
        self.assertFalse(any(a.startswith("head:") for a in args))
        self.assertNotIn("pr", args)  # must not be `gh pr list`
        self.assertEqual(
            args,
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/BasedHardware/omi/pulls?state=open&base=main&per_page={LIST_PAGE_SIZE}",
            ],
        )

    def test_parse_listed_prs_flattens_paginated_pages(self) -> None:
        # Contract for the truncation blocker: a second page of older PRs must
        # be visible to the local prefix filter (not dropped at page 1).
        page1 = [
            {
                "number": i,
                "head": {"ref": f"feat/{i}", "repo": {"full_name": "BasedHardware/omi"}},
                "base": {"repo": {"full_name": "BasedHardware/omi"}},
            }
            for i in range(1, LIST_PAGE_SIZE + 1)
        ]
        page2 = [
            {
                "number": 10419,
                "head": {"ref": "release/windows-v1.0.3", "repo": {"full_name": "BasedHardware/omi"}},
                "base": {"repo": {"full_name": "BasedHardware/omi"}},
            },
            {
                "number": 70000,
                "head": {
                    "ref": "release/windows-v9.9.9",
                    "repo": {"full_name": "someone/omi"},
                },
                "base": {"repo": {"full_name": "BasedHardware/omi"}},
            },
        ]
        prs = parse_listed_prs(json.dumps([page1, page2]))
        self.assertEqual(len(prs), LIST_PAGE_SIZE + 2)
        self.assertEqual(
            prs[-2], SyncPullRequest(number=10419, head_ref="release/windows-v1.0.3", is_cross_repository=False)
        )
        self.assertEqual(
            prs[-1], SyncPullRequest(number=70000, head_ref="release/windows-v9.9.9", is_cross_repository=True)
        )
        selected = select_superseded(prs, current_number=10960, prefix="release/windows-v")
        self.assertEqual([pr.number for pr in selected], [10419])

    def test_parse_listed_prs_treats_missing_head_repo_as_cross(self) -> None:
        payload = json.dumps(
            [
                [
                    {
                        "number": 42,
                        "head": {"ref": "release/windows-v1.0.1", "repo": None},
                        "base": {"repo": {"full_name": "BasedHardware/omi"}},
                    }
                ]
            ]
        )
        prs = parse_listed_prs(payload)
        self.assertEqual(prs, [SyncPullRequest(number=42, head_ref="release/windows-v1.0.1", is_cross_repository=True)])


if __name__ == "__main__":
    unittest.main()
