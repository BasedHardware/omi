#!/usr/bin/env python3
"""Regression tests for the bounded local CI-prediction selection."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_push_ci_prediction import (  # noqa: E402
    DESKTOP_FLOW_LINT_INPUTS,
    DESKTOP_RELEASE_PATHSPECS,
    github_outputs,
    resolve_impact,
    select_checks,
)

_PLANNER_SPEC = importlib.util.spec_from_file_location(
    "plan_desktop_release_pre_push_contract",
    REPO_ROOT / ".github/scripts/plan-desktop-release.py",
)
assert _PLANNER_SPEC and _PLANNER_SPEC.loader
planner = importlib.util.module_from_spec(_PLANNER_SPEC)
_PLANNER_SPEC.loader.exec_module(planner)


class PrePushCiPredictionTests(unittest.TestCase):
    def select(
        self,
        paths: list[str],
        contents: dict[str, str | None] | None = None,
        base_contents: dict[str, str | None] | None = None,
    ) -> list[str]:
        source_contents = contents or {}
        base_source_contents = base_contents if base_contents is not None else source_contents
        return select_checks(
            paths,
            read_text=lambda path: source_contents.get(path),
            read_base_text=lambda path: base_source_contents.get(path),
        )

    def plan(
        self,
        paths: list[str],
        contents: dict[str, str | None] | None = None,
        base_contents: dict[str, str | None] | None = None,
        event: str = "local",
    ):
        source_contents = contents or {}
        base_source_contents = base_contents if base_contents is not None else source_contents
        return resolve_impact(
            paths,
            read_text=lambda path: source_contents.get(path),
            read_base_text=lambda path: base_source_contents.get(path),
            event=event,
        )

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

    def test_removing_last_generator_marker_selects_build_runner(self) -> None:
        path = "app/lib/models/task.dart"
        self.assertIn(
            "flutter-codegen",
            self.select(
                [path],
                {path: "class Task {}"},
                {path: "@JsonSerializable()\nclass Task {}"},
            ),
        )

    def test_asset_change_is_an_explicit_codegen_input(self) -> None:
        plan = self.plan(["app/assets/icons/omi.png"])
        self.assertTrue(plan.includes("flutter-codegen"))
        self.assertEqual(github_outputs(plan)["has_app_codegen"], "true")

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

    def test_every_desktop_flow_reader_input_selects_flow_lint(self) -> None:
        for path in DESKTOP_FLOW_LINT_INPUTS:
            with self.subTest(path=path):
                self.assertTrue(self.plan([path]).includes("desktop-flow-lint"))

    def test_canonical_swift_driver_selects_the_expensive_test_phase(self) -> None:
        plan = self.plan(["desktop/macos/scripts/run-swift-ci.sh"])
        self.assertTrue(plan.includes("desktop-swift-tests"))
        self.assertEqual(github_outputs(plan)["should_run_tests"], "true")

    def test_swift_skip_policy_change_selects_the_expensive_test_phase(self) -> None:
        plan = self.plan(["desktop/macos/scripts/swift-test-skips.json"])
        self.assertTrue(plan.includes("desktop-swift-tests"))
        self.assertEqual(github_outputs(plan)["should_run_tests"], "true")

    def test_unknown_component_paths_select_the_normal_component_lane(self) -> None:
        app = self.plan(["app/tooling/unknown-input.txt"])
        desktop = self.plan(["desktop/macos/Resources/unknown-input.txt"])
        self.assertTrue(app.includes("app-analysis-tests"))
        self.assertTrue(desktop.includes("desktop-ci-only"))

    def test_selector_change_exercises_broad_resolver_fixtures(self) -> None:
        plan = self.plan(["scripts/pre_push_ci_prediction.py"])
        for phase in (
            "flutter-codegen",
            "flutter-l10n",
            "desktop-flow-lint",
            "desktop-swift-tests",
            "app-analysis-tests",
        ):
            with self.subTest(phase=phase):
                self.assertTrue(plan.includes(phase))

    def test_release_compile_runs_on_prs_and_pushes_for_releasable_desktop_changes(self) -> None:
        # Release-lane-only breaks (whole-module strict concurrency) must die in
        # PRs: the KG ResolveOutcome Sendable error (#11373/#11374) merged with a
        # green debug lane and wedged every candidate for three merges.
        paths = ["desktop/macos/Resources/Info.plist"]
        self.assertTrue(self.plan(paths, event="pull_request").includes("desktop-swift-release-compile"))
        self.assertTrue(self.plan(paths, event="push").includes("desktop-swift-release-compile"))
        self.assertTrue(
            self.plan(["desktop/macos/Desktop/Package.resolved"], event="pull_request").includes(
                "desktop-swift-release-compile"
            )
        )
        self.assertFalse(
            self.plan(["backend/routers/updates.py"], event="pull_request").includes(
                "desktop-swift-release-compile"
            )
        )

    def test_ci_producer_pathspecs_cover_every_planner_desktop_release_path(self) -> None:
        """Planner release inputs must wake exact-SHA desktop CI, with no silent drift."""
        self.assertEqual(DESKTOP_RELEASE_PATHSPECS, planner.DESKTOP_RELEASE_PATHS)
        for pathspec in planner.DESKTOP_RELEASE_PATHS:
            probe = pathspec if Path(pathspec).suffix else f"{pathspec.rstrip('/')}/Resources/Info.plist"
            with self.subTest(pathspec=pathspec, probe=probe):
                plan = self.plan([probe], event="push")
                self.assertTrue(plan.includes("desktop-ci-only"), probe)
                self.assertTrue(plan.includes("desktop-swift-release-compile"), probe)
                outputs = github_outputs(plan)
                self.assertEqual(outputs["should_run"], "true", probe)
                self.assertEqual(outputs["should_release_compile"], "true", probe)

    def test_changelog_and_agents_docs_are_not_releasable_ci_inputs(self) -> None:
        for path in (
            "desktop/macos/CHANGELOG.json",
            "desktop/macos/AGENTS.md",
            "desktop/macos/changelog/unreleased/example.json",
        ):
            with self.subTest(path=path):
                plan = self.plan([path], event="push")
                self.assertFalse(plan.includes("desktop-ci-only"), path)
                self.assertFalse(plan.includes("desktop-swift-release-compile"), path)

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
