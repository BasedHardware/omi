#!/usr/bin/env python3
"""Regression tests for the bounded local CI-prediction selection."""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_push_ci_prediction import (  # noqa: E402
    ACCEPTED_EVENTS,
    DESKTOP_FLOW_LINT_INPUTS,
    DESKTOP_RELEASE_PATHSPECS,
    github_outputs,
    resolve_impact,
    select_checks,
)

WORKFLOWS_DIR = REPO_ROOT / ".github/workflows"
# Both call sites forward `${{ github.event_name }}` verbatim, so a workflow reaching
# either one can hand this script any trigger it declares. The direct pattern is
# anchored on the script name rather than on `--event` alone: other workflows forward
# `github.event_name` to unrelated scripts with their own `--event` flag, and matching
# those would fail this test for a script it does not govern.
_PREDICTOR_INVOCATION = "pre_push_ci_prediction.py"
_EVENT_NAME_FORWARD = re.compile(r"--event\s+\"\$\{\{\s*github\.event_name\s*\}\}\"")
_USES_DETECT_CHANGES = re.compile(r"uses:\s*\./\.github/actions/detect-changes")
# A shell invocation continues across backslash-newlines; the flag always lands within
# a few lines of the script name.
_INVOCATION_TAIL_LINES = 12


def _forwards_event_name_to_the_predictor(text: str) -> bool:
    """True if some `pre_push_ci_prediction.py` call passes `${{ github.event_name }}`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _PREDICTOR_INVOCATION not in line:
            continue
        tail = "\n".join(lines[index : index + _INVOCATION_TAIL_LINES])
        if _EVENT_NAME_FORWARD.search(tail):
            return True
    return False


def _declared_triggers(workflow_text: str) -> list[str]:
    """Trigger names from a workflow's top-level `on:` block, both YAML spellings."""
    block = re.search(r"^on:[ \t]*(.*)\n((?:(?:[ \t].*)?\n)*?)(?=^\S)", workflow_text, re.MULTILINE)
    if not block:
        return []
    inline = block.group(1).strip()
    if inline.startswith("["):
        return [name.strip().strip("'\"") for name in inline.strip("[]").split(",") if name.strip()]
    if inline:
        return [inline.strip("'\"")]
    return re.findall(r"^  ([A-Za-z_]+):", block.group(2), re.MULTILINE)


def _workflows_reaching_the_predictor() -> dict[str, list[str]]:
    """-> {workflow filename: declared triggers} for every caller of this script."""
    reaching = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if _forwards_event_name_to_the_predictor(text) or _USES_DETECT_CHANGES.search(text):
            reaching[path.name] = _declared_triggers(text)
    return reaching


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
            "desktop-flow-lint",
            "desktop-swift-tests",
            "app-analysis-tests",
            "app-compile-smoke",
        ):
            with self.subTest(phase=phase):
                self.assertTrue(plan.includes(phase))

    def test_routing_only_diff_does_not_wake_flutter_regeneration(self) -> None:
        for path in (".github/checks-manifest.yaml", "scripts/pre_push_ci_prediction.py"):
            with self.subTest(path=path):
                plan = self.plan([path])
                self.assertFalse(plan.includes("flutter-codegen"))
                self.assertFalse(plan.includes("flutter-l10n"))
                self.assertEqual(github_outputs(plan)["has_flutter_generated"], "false")

    def test_manifest_only_diff_still_skips_flutter_regeneration(self) -> None:
        plan = self.plan([".github/checks-manifest.yaml"])

        self.assertFalse(plan.includes("flutter-codegen"))
        self.assertFalse(plan.includes("flutter-l10n"))
        self.assertEqual(github_outputs(plan)["has_flutter_generated"], "false")

    def test_mobile_workflow_change_wakes_flutter_regeneration(self) -> None:
        plan = self.plan([".github/workflows/mobile-app-checks.yml"])

        self.assertTrue(plan.includes("flutter-codegen"))
        self.assertTrue(plan.includes("flutter-l10n"))
        outputs = github_outputs(plan)
        self.assertEqual(outputs["has_flutter_generated"], "true")
        self.assertEqual(outputs["has_app_codegen"], "true")
        self.assertEqual(outputs["has_app_l10n"], "true")

    def test_detect_changes_action_change_wakes_flutter_regeneration(self) -> None:
        plan = self.plan([".github/actions/detect-changes/action.yml"])

        self.assertTrue(plan.includes("flutter-codegen"))
        self.assertTrue(plan.includes("flutter-l10n"))
        outputs = github_outputs(plan)
        self.assertEqual(outputs["has_flutter_generated"], "true")
        self.assertEqual(outputs["has_app_codegen"], "true")
        self.assertEqual(outputs["has_app_l10n"], "true")

    def test_real_generator_inputs_still_wake_flutter_regeneration(self) -> None:
        codegen = self.plan(["app/build.yaml"])
        self.assertTrue(codegen.includes("flutter-codegen"))
        annotated = self.plan(
            ["app/lib/models/thing.dart"],
            {"app/lib/models/thing.dart": "@JsonSerializable()\nclass Thing {}"},
        )
        self.assertTrue(annotated.includes("flutter-codegen"))
        l10n = self.plan(["app/lib/l10n/app_en.arb"])
        self.assertTrue(l10n.includes("flutter-l10n"))
        self.assertEqual(github_outputs(l10n)["has_flutter_generated"], "true")

    def test_release_compile_preserves_pr_and_main_asymmetry(self) -> None:
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

    def test_every_declared_workflow_trigger_is_an_accepted_event(self) -> None:
        """A trigger this script rejects kills change detection before it writes an output.

        `--event` is validated by argparse, so an unlisted value exits 2 and the calling
        step fails outright — no outputs, every dependent job skipped. `desktop-swift-ci.yml`
        declared `workflow_dispatch` while the choices were push/pull_request only, so its
        documented recovery hatch failed on every manual run. Deriving the requirement from
        the workflows' own `on:` blocks makes the next added trigger fail here instead.
        """
        reaching = _workflows_reaching_the_predictor()
        self.assertIn("desktop-swift-ci.yml", reaching, "predictor call sites moved; update the discovery patterns")
        for workflow, triggers in reaching.items():
            self.assertTrue(triggers, f"{workflow}: no triggers parsed out of its `on:` block")
            for trigger in triggers:
                with self.subTest(workflow=workflow, trigger=trigger):
                    self.assertIn(trigger, ACCEPTED_EVENTS, f"{workflow} declares {trigger}, which --event rejects")

    def test_accepted_events_keep_the_local_hook_value(self) -> None:
        """`scripts/pre-push` relies on the default; dropping it would break the hook."""
        self.assertIn("local", ACCEPTED_EVENTS)

    def test_event_does_not_change_the_resolved_plan(self) -> None:
        """Widening `--event` is safe precisely because no routing decision reads it."""
        paths = ["desktop/macos/Desktop/Package.swift", "backend/database/users.py", "app/lib/main.dart"]
        baseline = self.plan(paths, event="push").ordered()
        for event in ACCEPTED_EVENTS:
            with self.subTest(event=event):
                self.assertEqual(self.plan(paths, event=event).ordered(), baseline)


if __name__ == "__main__":
    unittest.main()
