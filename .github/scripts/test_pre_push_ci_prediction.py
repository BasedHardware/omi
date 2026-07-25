#!/usr/bin/env python3
"""Regression tests for the bounded local CI-prediction selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_push_ci_prediction import select_checks  # noqa: E402


class PrePushCiPredictionTests(unittest.TestCase):
    def select(self, paths: list[str], contents: dict[str, str | None] | None = None) -> list[str]:
        source_contents = contents or {}
        return select_checks(paths, read_text=lambda path: source_contents.get(path))

    def test_regular_app_dart_change_does_not_start_build_runner(self) -> None:
        self.assertEqual(
            self.select(
                ["app/lib/utils/date_formats.dart"], {"app/lib/utils/date_formats.dart": "class DateFormats {}"}
            ),
            ["app-dart-format", "app-ci-only"],
        )

    def test_codegen_annotation_selects_build_runner_check(self) -> None:
        self.assertEqual(
            self.select(
                ["app/lib/models/task.dart"],
                {"app/lib/models/task.dart": "@JsonSerializable()\nclass Task {}"},
            ),
            ["app-dart-format", "flutter-codegen", "app-ci-only"],
        )

    def test_deleted_dart_generator_input_is_conservative(self) -> None:
        self.assertEqual(
            self.select(["app/lib/models/obsolete.dart"]),
            ["app-dart-format", "flutter-codegen", "app-ci-only"],
        )

    def test_l10n_and_generated_dart_have_the_right_local_contracts(self) -> None:
        self.assertEqual(
            self.select(["app/lib/l10n/app_en.arb", "app/lib/l10n/app_localizations.dart"]),
            ["flutter-l10n", "app-ci-only"],
        )

    def test_desktop_flow_contract_sources_select_flow_lint_only(self) -> None:
        self.assertEqual(
            self.select(["desktop/macos/e2e/flows/new-flow.yaml"]),
            ["desktop-flow-lint", "desktop-ci-only"],
        )

    def test_windows_kgworker_closure_inputs_select_only_the_targeted_test(self) -> None:
        for path in (
            "desktop/windows/scripts/kgworker-native-closure.mjs",
            "desktop/windows/scripts/kgworker-native-closure.test.mjs",
            "desktop/windows/electron-builder.config.mjs",
            "desktop/windows/package.json",
            "desktop/windows/pnpm-lock.yaml",
        ):
            self.assertEqual(self.select([path]), ["windows-kgworker-native-closure"])

    def test_unrelated_windows_changes_do_not_select_kgworker_closure_test(self) -> None:
        self.assertEqual(self.select(["desktop/windows/src/renderer/src/pages/Tasks.tsx"]), [])


if __name__ == "__main__":
    unittest.main()
