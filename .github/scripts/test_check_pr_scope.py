#!/usr/bin/env python3
"""Unit tests for check_pr_scope.py classification, counting, and advisory tiers."""

from __future__ import annotations

import unittest

from check_pr_scope import (
    REVIEW_COLLAPSE_LINES,
    WARN_LINES,
    count_production_lines,
    evaluate,
    is_production_source,
)


class ClassificationTests(unittest.TestCase):
    def test_production_paths(self) -> None:
        for path in (
            'backend/utils/sync/pipeline.py',
            'app/lib/services/wals/wal.dart',
            'desktop/macos/Backend-Rust/src/routes/proxy.rs',
            'desktop/macos/Desktop/Sources/Chat/ChatToolExecutor.swift',
            '.github/workflows/gcp_backend.yml',
            'backend/testharness.py',  # 'testharness' must not match test excludes
            'desktop/macos/scripts/test-tool-surfaces.sh',  # hyphenated prod script
        ):
            self.assertTrue(is_production_source(path), path)

    def test_excluded_test_trees_all_platform_conventions(self) -> None:
        for path in (
            'backend/tests/unit/test_sync_v2.py',
            'backend/testing/e2e/test_crud.py',
            'app/test/widget_test.dart',
            'app/integration_test/onboarding_test.dart',
            'desktop/macos/Desktop/Tests/GoogleSessionTests.swift',  # capital-T Swift tree
            'desktop/macos/Desktop/Sources/FooTests.swift',
            'web/frontend/src/__tests__/App.test.tsx',
            'desktop/windows/src/session.test.ts',
        ):
            self.assertFalse(is_production_source(path), path)

    def test_excluded_docs_l10n_generated_locks(self) -> None:
        for path in (
            'docs/doc/developer/guide.mdx',
            'AGENTS.md',
            'app/lib/l10n/app_fr.arb',
            'backend/pylock.toml',
            'app/pubspec.lock',
            'web/package-lock.json',
            'app/lib/gen/assets.g.dart',
            '.cursor/plans/x.plan.md',
            'desktop/macos/changelog/unreleased/fix.json',
            'backend/openapi.json',
        ):
            self.assertFalse(is_production_source(path), path)


class CountingTests(unittest.TestCase):
    def test_counts_production_only_and_skips_binary(self) -> None:
        numstat = (
            '10\t5\tbackend/utils/a.py\0'
            '3\t0\tbackend/tests/unit/test_a.py\0'
            '-\t-\tapp/assets/img.png\0'
            '7\t2\tapp/lib/b.dart\0'
        )
        total, per_file = count_production_lines(numstat)
        self.assertEqual(total, 24)
        self.assertEqual([p for _, p in per_file], ['backend/utils/a.py', 'app/lib/b.dart'])

    def test_z_records_keep_non_ascii_paths_raw_and_classified(self) -> None:
        # With -z, git emits the real filename (no C-quoting), so suffix
        # excludes match non-ASCII names.
        numstat = '9\t0\tdocs/weird ü.md\0'
        self.assertEqual(count_production_lines(numstat), (0, []))


class AdvisoryTests(unittest.TestCase):
    def test_tiers_are_annotations_only(self) -> None:
        cases = [
            (100, '::notice'),
            (WARN_LINES, '::warning'),
            (REVIEW_COLLAPSE_LINES, '::warning'),
        ]
        for total, want_prefix in cases:
            message = evaluate(total)
            self.assertTrue(message.startswith(want_prefix), message)

    def test_review_collapse_tier_cites_the_audit(self) -> None:
        self.assertIn('regression', evaluate(REVIEW_COLLAPSE_LINES))

    def test_warnings_say_they_never_block(self) -> None:
        for total in (WARN_LINES, REVIEW_COLLAPSE_LINES):
            self.assertIn('never blocks', evaluate(total))

    def test_push_events_are_notice_only(self) -> None:
        message = evaluate(REVIEW_COLLAPSE_LINES, notice_only=True)
        self.assertTrue(message.startswith('::notice'), message)


if __name__ == '__main__':
    unittest.main()
