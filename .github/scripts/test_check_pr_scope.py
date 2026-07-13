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
    resolve_enforcement,
    unquote_git_path,
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


class GitPathTests(unittest.TestCase):
    def test_unquote_non_ascii(self) -> None:
        self.assertEqual(unquote_git_path('"docs/weird \\303\\274.md"'), 'docs/weird ü.md')

    def test_unquoted_passthrough(self) -> None:
        self.assertEqual(unquote_git_path('backend/utils/a.py'), 'backend/utils/a.py')

    def test_quoted_docs_path_is_excluded_after_unquoting(self) -> None:
        numstat = '9\t0\t"docs/weird \\303\\274.md"\n'
        total, per_file = count_production_lines(numstat)
        self.assertEqual((total, per_file), (0, []))


class CountingTests(unittest.TestCase):
    def test_counts_production_only_and_skips_binary(self) -> None:
        numstat = (
            '10\t5\tbackend/utils/a.py\n'
            '3\t0\tbackend/tests/unit/test_a.py\n'
            '-\t-\tapp/assets/img.png\n'
            '7\t2\tapp/lib/b.dart\n'
        )
        total, per_file = count_production_lines(numstat)
        self.assertEqual(total, 24)
        self.assertEqual([p for _, p in per_file], ['backend/utils/a.py', 'app/lib/b.dart'])


class EnforcementTests(unittest.TestCase):
    def test_thresholds_and_label_override(self) -> None:
        cases = [
            (100, set(), True, 0, '::notice'),
            (WARN_LINES, set(), True, 0, '::warning'),
            (FAIL_LINES, set(), True, 1, '::error'),
            (FAIL_LINES, {OVERRIDE_LABEL}, True, 0, '::notice'),
            (FAIL_LINES, {'unrelated'}, True, 1, '::error'),
            (FAIL_LINES, set(), False, 0, '::notice'),
        ]
        for total, labels, enforce, want_code, want_prefix in cases:
            message, code = evaluate(total, labels, enforce=enforce, enforce_reason='test')
            self.assertEqual(code, want_code, (total, labels, enforce))
            self.assertTrue(message.startswith(want_prefix), message)

    def test_revert_body_disables_enforcement(self) -> None:
        enforce, reason = resolve_enforcement('Reverts BasedHardware/omi#8429', {})
        self.assertFalse(enforce)
        self.assertIn('revert', reason)

    def test_non_revert_body_enforces(self) -> None:
        enforce, _ = resolve_enforcement('Fixes the thing. See #123.', {})
        self.assertTrue(enforce)

    def test_push_event_disables_enforcement(self) -> None:
        enforce, reason = resolve_enforcement('', {'GITHUB_EVENT_NAME': 'push'})
        self.assertFalse(enforce)
        self.assertIn('push', reason)

    def test_local_env_override_disables_enforcement(self) -> None:
        enforce, reason = resolve_enforcement('', {LOCAL_OVERRIDE_ENV: '1'})
        self.assertFalse(enforce)
        self.assertIn(LOCAL_OVERRIDE_ENV, reason)


if __name__ == '__main__':
    unittest.main()
