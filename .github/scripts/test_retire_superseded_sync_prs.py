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

from retire_superseded_sync_prs import SyncPullRequest, select_superseded  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
