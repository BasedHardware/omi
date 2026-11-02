#!/usr/bin/env python3
"""Tests for the fast worktree environment doctor that opens the pre-push gate."""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import worktree_env_doctor as doctor  # noqa: E402

ALL_TOOLS = {"flutter", "dart", "uv", "uvx", "xcrun", "pnpm", "clang-format", "actionlint"}


def which_from(tools):
    return lambda name: f"/usr/bin/{name}" if name in tools else None


def healthy_probe(python, modules):
    return {"version": [3, 11], "missing": []}


class Fixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("backend/.python-version", "3.11.15\n")

    def close(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def venv(self) -> None:
        python = self.write("backend/.venv/bin/python", "#!/bin/sh\n")
        python.chmod(0o755)

    def pub_get(self) -> None:
        self.write("app/pubspec.yaml", "name: omi\n")
        self.write("app/pubspec.lock", "packages: {}\n")
        config = self.write(doctor.APP_PACKAGE_CONFIG, '{"configVersion": 2, "packages": []}\n')
        later = time.time() + 5
        os.utime(config, (later, later))

    def swift_state(self, artifacts=(), dependencies=()) -> Path:
        build = self.root / doctor.SWIFT_PACKAGE / ".build"
        build.mkdir(parents=True, exist_ok=True)
        state = {
            "object": {
                "artifacts": [
                    {"kind": {"xcframework": {}}, "packageRef": {"identity": identity}, "path": str(path)}
                    for identity, path in artifacts
                ],
                "dependencies": [
                    {"packageRef": {"identity": sub}, "state": {"name": "sourceControlCheckout"}, "subpath": sub}
                    for sub in dependencies
                ],
                "prebuilts": [],
            },
            "version": 7,
        }
        (build / "workspace-state.json").write_text(json.dumps(state))
        return build


class DoctorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()
        self.addCleanup(self.fx.close)

    def diff(self, changed, selection=(), env=None, tools=ALL_TOOLS, probe=healthy_probe):
        for path in changed:
            if not (self.fx.root / path).exists():
                self.fx.write(path)
        return doctor.run_diff_checks(
            self.fx.root,
            list(changed),
            set(selection),
            env or {},
            "/usr/bin/python3",
            which=which_from(tools),
            probe=probe,
            stamp="STAMP",
        )


class AppDependencyTests(DoctorTestCase):
    def test_missing_package_config_is_reported_with_pub_get(self) -> None:
        report = self.diff(["app/lib/main.dart"], selection=["app-dart-format"])
        self.assertFalse(report.ok)
        self.assertIn("package_config.json is missing", report.findings[0].problem)
        self.assertEqual(report.findings[0].fix, "(cd app && flutter pub get)")

    def test_resolved_dependencies_pass(self) -> None:
        self.fx.pub_get()
        self.assertTrue(self.diff(["app/lib/main.dart"], selection=["app-dart-format"]).ok)

    def test_package_config_older_than_lock_is_stale(self) -> None:
        self.fx.pub_get()
        later = time.time() + 60
        os.utime(self.fx.root / "app/pubspec.lock", (later, later))
        report = self.diff(["app/lib/main.dart"])
        self.assertEqual(len(report.findings), 1)
        self.assertIn("older than app/pubspec.lock", report.findings[0].problem)

    def test_generated_dart_alone_does_not_need_dependencies(self) -> None:
        self.assertTrue(self.diff(["app/lib/models/user.g.dart"]).ok)

    def test_generator_selection_needs_dependencies_without_dart_changes(self) -> None:
        report = self.diff(["app/pubspec.yaml"], selection=["flutter-codegen"])
        self.assertIn("app", {finding.component for finding in report.findings})

    def test_dart_format_hatch_is_honored(self) -> None:
        report = self.diff(["app/lib/main.dart"], selection=["app-dart-format"], env={"PRE_PUSH_SKIP_DART_FORMAT": "1"})
        self.assertTrue(report.ok)

    def test_missing_flutter_is_a_manual_step(self) -> None:
        report = self.diff(["app/lib/main.dart"], tools=ALL_TOOLS - {"flutter"})
        self.assertTrue(report.findings[0].manual)


class BackendVenvTests(DoctorTestCase):
    def test_missing_venv_is_reported_for_a_backend_change(self) -> None:
        report = self.diff(["backend/routers/users.py"])
        problems = [f for f in report.findings if f.component == "backend"]
        self.assertEqual(len(problems), 1)
        self.assertIn("no interpreter", problems[0].problem)
        self.assertEqual(problems[0].fix, "make setup-backend")
        self.assertIn("backend type check", problems[0].needed_by)

    def test_healthy_venv_passes(self) -> None:
        self.fx.venv()
        self.assertTrue(self.diff(["backend/routers/users.py"]).ok)

    def test_probe_requests_the_modules_selected_phases_import(self) -> None:
        self.fx.venv()
        seen = []

        def probe(python, modules):
            seen.extend(modules)
            return {"version": [3, 11], "missing": []}

        self.diff(["backend/routers/users.py"], probe=probe)
        self.assertTrue({"yaml", "dotenv", "pyright", "pytest"} <= set(seen))

    def test_incomplete_venv_names_the_missing_modules(self) -> None:
        self.fx.venv()
        report = self.diff(["backend/routers/users.py"], probe=lambda p, m: {"version": [3, 11], "missing": ["pyright"]})
        self.assertIn("cannot import pyright", report.findings[0].problem)

    def test_wrong_python_version_is_reported(self) -> None:
        self.fx.venv()
        report = self.diff(["backend/routers/users.py"], probe=lambda p, m: {"version": [3, 12], "missing": []})
        self.assertIn("pins 3.11", report.findings[0].problem)

    def test_symlinked_venv_is_replaced_not_followed(self) -> None:
        other = self.fx.root / "elsewhere"
        other.mkdir()
        (self.fx.root / "backend/.venv").symlink_to(other)
        report = self.diff(["backend/routers/users.py"])
        self.assertTrue(report.findings[0].fix.startswith("rm backend/.venv && "))

    def test_all_backend_hatches_skip_the_venv(self) -> None:
        env = {
            "PRE_PUSH_SKIP_BACKEND_TYPECHECK": "1",
            "PRE_PUSH_SKIP_BACKEND_UNIT_TESTS": "1",
            "PRE_PUSH_SKIP_OPENAPI_CONTRACT": "1",
        }
        self.assertTrue(self.diff(["backend/routers/users.py"], env=env).ok)

    def test_unrelated_change_checks_nothing(self) -> None:
        report = self.diff(["docs/doc/getting-started.mdx"])
        self.assertTrue(report.ok)
        self.assertEqual(report.checked, [])


class SwiftPMStateTests(DoctorTestCase):
    SWIFT_CHANGE = ["desktop/macos/Desktop/Sources/OmiApp.swift"]

    def test_recorded_artifact_missing_on_disk_is_stale(self) -> None:
        build = self.fx.root / doctor.SWIFT_PACKAGE / ".build"
        self.fx.swift_state(artifacts=[("sparkle", build / "artifacts/sparkle/Sparkle/Sparkle.xcframework")])
        report = self.diff(self.SWIFT_CHANGE)
        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertIn("1 recorded binary artifact(s) are missing on disk (sparkle)", finding.problem)
        self.assertEqual(
            finding.fix,
            "mv desktop/macos/Desktop/.build desktop/macos/Desktop/.build.stale-STAMP"
            " && xcrun swift package resolve --package-path desktop/macos/Desktop",
        )

    def test_present_artifacts_and_checkouts_pass(self) -> None:
        build = self.fx.root / doctor.SWIFT_PACKAGE / ".build"
        framework = build / "artifacts/sparkle/Sparkle/Sparkle.xcframework"
        framework.mkdir(parents=True)
        (build / "checkouts/GRDB.swift").mkdir(parents=True)
        self.fx.swift_state(artifacts=[("sparkle", framework)], dependencies=["GRDB.swift"])
        self.assertTrue(self.diff(self.SWIFT_CHANGE).ok)

    def test_no_build_directory_is_fine(self) -> None:
        self.assertTrue(self.diff(self.SWIFT_CHANGE).ok)

    def test_missing_checkout_is_stale(self) -> None:
        self.fx.swift_state(dependencies=["GRDB.swift"])
        report = self.diff(self.SWIFT_CHANGE)
        self.assertIn("missing from .build/checkouts (GRDB.swift)", report.findings[0].problem)

    def test_artifact_from_another_tree_is_stale(self) -> None:
        foreign = self.fx.root / "other-worktree/.build/artifacts/sparkle/Sparkle.xcframework"
        foreign.mkdir(parents=True)
        self.fx.swift_state(artifacts=[("sparkle", foreign)])
        report = self.diff(self.SWIFT_CHANGE)
        self.assertIn("outside this .build", report.findings[0].problem)

    def test_unreadable_state_is_stale(self) -> None:
        build = self.fx.swift_state()
        (build / "workspace-state.json").write_text("{not json")
        self.assertFalse(self.diff(self.SWIFT_CHANGE).ok)

    def test_swift_hatch_and_non_swift_diffs_skip_the_check(self) -> None:
        self.fx.swift_state(dependencies=["GRDB.swift"])
        self.assertTrue(self.diff(self.SWIFT_CHANGE, env={"PRE_PUSH_SKIP_DESKTOP_SWIFT": "1"}).ok)
        self.assertTrue(self.diff(["desktop/macos/README.md"]).ok)

    def test_stale_build_directories_are_ignored_by_git(self) -> None:
        ignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(".build.stale-*/", ignore)


class OtherPrerequisiteTests(DoctorTestCase):
    def test_windows_dependencies_follow_the_selection(self) -> None:
        report = self.diff(["desktop/windows/package.json"], selection=["windows-kgworker-native-closure"])
        self.assertEqual(report.findings[0].fix, "(cd desktop/windows && pnpm install --frozen-lockfile)")

    def test_flow_lint_checks_the_hook_interpreter(self) -> None:
        report = self.diff(["desktop/macos/e2e/flows/a.yaml"], selection=["desktop-flow-lint"], probe=lambda p, m: {"version": [3, 11], "missing": ["yaml"]})
        self.assertEqual(report.findings[0].component, "desktop-flow-lint")

    def test_missing_tools_for_touched_sources_are_manual(self) -> None:
        report = self.diff(["omi/firmware/src/main.c", ".github/workflows/x.yml"], tools=set())
        self.assertEqual({f.component for f in report.findings}, {"firmware", "workflows"})
        self.assertTrue(all(f.manual and not f.fix for f in report.findings))


class ReportTests(DoctorTestCase):
    def test_one_command_fixes_everything_once(self) -> None:
        build = self.fx.root / doctor.SWIFT_PACKAGE / ".build"
        self.fx.swift_state(artifacts=[("sparkle", build / "artifacts/missing.xcframework")])
        report = self.diff(
            ["app/lib/main.dart", "backend/routers/users.py", "desktop/macos/Desktop/Sources/OmiApp.swift"],
            selection=["desktop-flow-lint"],
            probe=lambda p, m: {"version": [3, 11], "missing": ["yaml"]},
        )
        command = report.fix_command()
        self.assertTrue(command.startswith("cd "))
        self.assertIn("(cd app && flutter pub get)", command)
        self.assertIn("xcrun swift package resolve", command)
        self.assertEqual(command.count("make setup-backend"), 1)
        out = io.StringIO()
        doctor.render(report, out)
        self.assertIn("Fix everything with:", out.getvalue())
        self.assertIn(doctor.SKIP_HATCH, out.getvalue())

    def test_apply_fixes_runs_from_the_root_and_stops_on_failure(self) -> None:
        report = doctor.Report(
            findings=[
                doctor.Finding("a", "x", fix="touch fixed"),
                doctor.Finding("b", "y", fix="false"),
                doctor.Finding("c", "z", fix="touch never"),
            ]
        )
        self.assertFalse(doctor.apply_fixes(report, self.fx.root))
        self.assertTrue((self.fx.root / "fixed").exists())
        self.assertFalse((self.fx.root / "never").exists())

    def test_bootstrap_skips_absent_toolchains(self) -> None:
        self.fx.venv()
        report = doctor.run_all_checks(self.fx.root, which=which_from({"uv"}), probe=healthy_probe)
        self.assertTrue(report.ok)
        self.assertEqual(len(report.skipped), 2)

    def test_bootstrap_reports_missing_app_dependencies(self) -> None:
        self.fx.venv()
        report = doctor.run_all_checks(self.fx.root, which=which_from(ALL_TOOLS), probe=healthy_probe)
        self.assertEqual([f.component for f in report.findings], ["app"])

    def test_push_hatch_exits_zero(self) -> None:
        os.environ[doctor.SKIP_HATCH] = "1"
        self.addCleanup(os.environ.pop, doctor.SKIP_HATCH, None)
        listing = self.fx.write("changed.txt", "backend/main.py\n")
        self.assertEqual(doctor.main(["--changed-files", str(listing)]), 0)


def hook_function(name: str) -> str:
    text = (REPO_ROOT / "scripts/pre-push").read_text()
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}\n", text, re.S | re.M)
    if not match:
        raise AssertionError(f"scripts/pre-push no longer defines {name}")
    return match.group(1)


def hook_triggers(name: str) -> tuple[str, ...]:
    body = hook_function(name)
    match = re.search(r"changed_matches \\\n(.*?)\n\s*then", body, re.S)
    if not match:
        raise AssertionError(f"{name} no longer gates on changed_matches")
    return tuple(re.findall(r"'([^']+)'", match.group(1)))


class HookContractTests(unittest.TestCase):
    """The doctor mirrors hook triggers; drift would make it miss or over-demand."""

    def test_backend_triggers_match_the_hook(self) -> None:
        expected = {
            "check_backend_runtime_env_if_needed": doctor.BACKEND_RUNTIME_ENV_TRIGGERS,
            "check_backend_unit_tests_if_needed": doctor.BACKEND_UNIT_TEST_TRIGGERS,
            "check_openapi_contract_if_needed": doctor.OPENAPI_CONTRACT_TRIGGERS,
            "check_release_process_guards_if_needed": doctor.RELEASE_GUARD_TRIGGERS,
            "check_desktop_swift_if_needed": doctor.DESKTOP_SWIFT_TRIGGERS,
        }
        for function, triggers in expected.items():
            with self.subTest(function=function):
                self.assertEqual(hook_triggers(function), triggers)

    def test_typecheck_triggers_match_needs_typecheck(self) -> None:
        text = (REPO_ROOT / "backend/scripts/needs-typecheck.sh").read_text()
        match = re.search(r"^\s+([^\n]*backend/\*\.py[^\n]*)\)\n", text, re.M)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(match.group(1).split("|")), doctor.BACKEND_TYPECHECK_TRIGGERS)

    def test_every_backend_phase_still_requires_the_canonical_interpreter(self) -> None:
        for function in (
            "check_backend_runtime_env_if_needed",
            "check_backend_typecheck_if_needed",
            "check_backend_unit_tests_if_needed",
            "check_openapi_contract_if_needed",
        ):
            with self.subTest(function=function):
                self.assertIn("require_backend_python", hook_function(function))

    def test_hatches_named_by_the_doctor_exist_in_the_hook(self) -> None:
        text = (REPO_ROOT / "scripts/pre-push").read_text()
        for _, hatch, _, _ in doctor.BACKEND_PHASES:
            if hatch:
                self.assertIn(hatch, text)
        self.assertIn(doctor.SKIP_HATCH, text)

    def test_doctor_is_the_first_phase(self) -> None:
        text = (REPO_ROOT / "scripts/pre-push").read_text()
        steps = re.findall(r"^run_step (\S+)", text, re.M)
        self.assertEqual(steps[0], "check_worktree_env")
        self.assertIn("worktree_env_doctor.py", hook_function("check_worktree_env"))


if __name__ == "__main__":
    unittest.main()
