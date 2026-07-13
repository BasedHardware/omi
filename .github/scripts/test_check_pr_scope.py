#!/usr/bin/env python3
"""Unit tests for check_pr_scope.py classification, counting, and enforcement."""

from __future__ import annotations

import unittest

from check_pr_scope import (
    FAIL_LINES,
    LOCAL_OVERRIDE_ENV,
    OVERRIDE_LABEL,
    WARN_LINES,
    count_production_lines,
    evaluate,
    is_production_source,
    resolve_waiver,
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


class EnforcementTests(unittest.TestCase):
    def test_thresholds_label_and_waiver(self) -> None:
        cases = [
            (100, set(), None, 0, '::notice'),
            (WARN_LINES, set(), None, 0, '::warning'),
            (WARN_LINES, {OVERRIDE_LABEL}, None, 0, '::notice'),  # label silences the warn tier
            (WARN_LINES, set(), 'push event', 0, '::notice'),
            (FAIL_LINES, set(), None, 1, '::error'),
            (FAIL_LINES, {OVERRIDE_LABEL}, None, 0, '::notice'),
            (FAIL_LINES, {'unrelated'}, None, 1, '::error'),
            (FAIL_LINES, set(), 'push event', 0, '::notice'),
        ]
        for total, labels, waiver, want_code, want_prefix in cases:
            message, code = evaluate(total, labels, waiver_reason=waiver)
            self.assertEqual(code, want_code, (total, labels, waiver))
            self.assertTrue(message.startswith(want_prefix), message)

    def test_push_event_waives(self) -> None:
        self.assertIn('push', resolve_waiver({'GITHUB_EVENT_NAME': 'push'}) or '')

    def test_local_env_override_waives(self) -> None:
        self.assertIn(LOCAL_OVERRIDE_ENV, resolve_waiver({LOCAL_OVERRIDE_ENV: '1'}) or '')

    def test_pull_request_event_enforces(self) -> None:
        self.assertIsNone(resolve_waiver({'GITHUB_EVENT_NAME': 'pull_request'}))

    def test_no_author_editable_waiver_exists(self) -> None:
        # The waiver must come from maintainer-controlled signals only
        # (label, env, event type) — never from PR body/title text.
        self.assertIsNone(resolve_waiver({}))


if __name__ == '__main__':
    unittest.main()
