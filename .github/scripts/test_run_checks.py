#!/usr/bin/env python3
"""Regression tests and drift guard for the deterministic check manifest."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib.util
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from run_checks import (
    VALID_PLATFORMS,
    Check,
    Manifest,
    detect_platform,
    execute_checks,
    load_manifest,
    resolve_check_selections,
    resolve_checks,
    skipped_platform_checks,
    validate_manifest,
)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MANIFEST_PATH = REPO_ROOT / ".github/checks-manifest.yaml"
WORKFLOWS_DIR = REPO_ROOT / ".github/workflows"
SCRIPT_REFERENCE_RE = re.compile(r"(?P<path>(?:\.github|backend|desktop/macos)/scripts/[A-Za-z0-9_.-]+\.py)")


def load_deferred_marker_module():
    path = SCRIPT_DIR / "deferred-work-marker-count.py"
    spec = importlib.util.spec_from_file_location("deferred_work_marker_count", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deterministic_workflow_references(workflows_dir: Path) -> set[str]:
    references: set[str] = set()
    for workflow in sorted(workflows_dir.glob("*.y*ml")):
        for match in SCRIPT_REFERENCE_RE.finditer(workflow.read_text(encoding="utf-8")):
            path = match.group("path")
            name = Path(path).name
            if (
                (
                    path.startswith(".github/scripts/")
                    and (name.startswith(("check_", "check-")) or name.endswith("-count.py"))
                )
                or (path.startswith("backend/scripts/") and name.startswith(("scan_", "check_")))
                or (path.startswith("desktop/macos/scripts/") and name.startswith(("check_", "check-")))
            ):
                references.add(path)
    return references


def registered_script_paths() -> set[str]:
    manifest = load_manifest(MANIFEST_PATH)
    return {token for check in manifest.checks for token in check.command if token.endswith(".py")}


TEST_MODULE_RE = re.compile(r"(?:^|/)test[_-][A-Za-z0-9_.-]*\.py$")


def interpreter_invoked_test_modules(command: tuple[str, ...]) -> list[str]:
    """Test modules a command hands straight to the interpreter.

    Commands that name an explicit runner (`-m pytest`, `-m unittest`) delegate
    discovery to that runner and are not subject to the self-running contract.
    """
    if any(token in {"-m", "pytest", "unittest"} for token in command):
        return []
    return [token for token in command if TEST_MODULE_RE.search(token)]


def non_self_running_reason(source: str) -> str | None:
    """Explain why `python3 <module>` would execute no test cases, or None.

    Two shapes execute nothing and still exit 0:
      * no `__main__` block at all -- a pytest-only module handed to the
        interpreter defines its functions and exits.
      * a `__main__` block calling `unittest.main()` in a module with no
        `TestCase` subclass -- discovery finds nothing to run.

    A script-style module whose `__main__` calls its own `main()` of assertions
    is self-running and must not be reported.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - a syntax error fails louder elsewhere
        return f"could not be parsed: {exc}"

    main_blocks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and any(
            isinstance(cmp_, ast.Constant) and cmp_.value == "__main__"
            for cmp_ in getattr(node.test, "comparators", [])
        )
    ]
    invoking_blocks = [
        node for node in main_blocks if any(isinstance(inner, ast.Call) for inner in ast.walk(node))
    ]
    if not invoking_blocks:
        return "has no __main__ block invoking a test runner, so the interpreter runs no cases"

    delegates_to_unittest = any(
        isinstance(inner, ast.Attribute) and inner.attr == "main" and getattr(inner.value, "id", "") == "unittest"
        for block in invoking_blocks
        for inner in ast.walk(block)
    )
    if not delegates_to_unittest:
        # Script-style: `__main__` calls the module's own assertions directly.
        return None

    has_test_case = any(
        isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Attribute) and base.attr.endswith("TestCase"))
            or (isinstance(base, ast.Name) and base.id.endswith("TestCase"))
            for base in node.bases
        )
        for node in ast.walk(tree)
    )
    if not has_test_case:
        return "calls unittest.main() with no TestCase subclass, so discovery collects nothing"
    return None


class ManifestContractTests(unittest.TestCase):
    def test_manifest_is_valid(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        self.assertEqual(validate_manifest(manifest, REPO_ROOT), [])

    def test_removing_ci_lane_is_invalid(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        first = manifest.checks[0]
        local_only = Check(first.id, first.command, first.triggers, ("local",), first.reason)
        invalid = type(manifest)((local_only, *manifest.checks[1:]), manifest.exempt)
        self.assertTrue(any("missing required lanes: ci" in error for error in validate_manifest(invalid, REPO_ROOT)))

    def test_requires_pr_body_must_be_boolean(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        first = manifest.checks[0]
        malformed = Check(
            first.id,
            first.command,
            first.triggers,
            first.lanes,
            first.reason,
            requires_pr_body="yes",  # type: ignore[arg-type]
        )
        invalid = type(manifest)((malformed, *manifest.checks[1:]), manifest.exempt)
        self.assertIn(
            f"{first.id}: requires_pr_body must be a boolean",
            validate_manifest(invalid, REPO_ROOT),
        )

    def test_explicit_trigger_path_must_exist(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        first = manifest.checks[0]
        missing = ".github/scripts/does-not-exist.py"
        malformed = Check(
            first.id,
            first.command,
            (*first.triggers, missing),
            first.lanes,
            first.reason,
        )
        invalid = type(manifest)((malformed, *manifest.checks[1:]), manifest.exempt)
        self.assertIn(
            f"{first.id}: explicit trigger path does not exist: {missing}",
            validate_manifest(invalid, REPO_ROOT),
        )

    def test_workflow_checks_are_registered_or_exempt(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        registered = registered_script_paths()
        exempt = {item.path for item in manifest.exempt}
        missing = sorted(deterministic_workflow_references(WORKFLOWS_DIR) - registered - exempt)
        self.assertEqual(missing, [], f"workflow checks missing from manifest/exempt: {missing}")

    def test_ci_lane_is_reachable_from_repo_checks(self) -> None:
        workflow = (WORKFLOWS_DIR / "repo-checks.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"run_checks\.py\s+--lane\s+ci")
        self.assertIn("--skip-pr-body-checks", workflow)
        manifest = load_manifest(MANIFEST_PATH)
        self.assertTrue(any("ci" in check.lanes for check in manifest.checks))

    def test_manifest_test_modules_execute_their_cases(self) -> None:
        """A registered test command must not be able to pass without running tests.

        `python3 some_test_module.py` exits 0 when the module defines only
        module-level `def test_*` functions, because `unittest.main()` discovers
        `TestCase` subclasses. Such a check is green forever without asserting
        anything, which is indistinguishable from a guard that works.
        """
        manifest = load_manifest(MANIFEST_PATH)
        offenders: list[str] = []
        for check in manifest.checks:
            for relative in interpreter_invoked_test_modules(check.command):
                path = REPO_ROOT / relative
                if not path.exists():
                    offenders.append(f"{check.id}: {relative} does not exist")
                    continue
                reason = non_self_running_reason(path.read_text(encoding="utf-8"))
                if reason:
                    offenders.append(f"{check.id}: {relative} {reason}")
        self.assertEqual(offenders, [], f"manifest test commands that execute no cases: {offenders}")

    def test_pytest_only_module_is_reported_as_non_self_running(self) -> None:
        """The guard above must fail on the real historical shape it exists to catch."""
        pytest_only = (
            "from pathlib import Path\n"
            "\n"
            "def test_something(tmp_path: Path) -> None:\n"
            "    assert True\n"
        )
        self.assertIn("has no __main__", non_self_running_reason(pytest_only) or "")

        with_runner = (
            "import unittest\n"
            "\n"
            "class T(unittest.TestCase):\n"
            "    def test_something(self) -> None:\n"
            "        self.assertTrue(True)\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        )
        self.assertIsNone(non_self_running_reason(with_runner))

        no_main = (
            "import unittest\n"
            "\n"
            "class T(unittest.TestCase):\n"
            "    def test_something(self) -> None:\n"
            "        self.assertTrue(True)\n"
        )
        self.assertIn("has no __main__", non_self_running_reason(no_main) or "")

        unittest_main_without_test_case = (
            "import unittest\n"
            "\n"
            "def test_something() -> None:\n"
            "    assert True\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        )
        self.assertIn(
            "no TestCase subclass", non_self_running_reason(unittest_main_without_test_case) or ""
        )

        # Script-style: a module whose __main__ runs its own assertions is fine.
        script_style = (
            "def main() -> int:\n"
            "    assert True\n"
            "    return 0\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(main())\n"
        )
        self.assertIsNone(non_self_running_reason(script_style))

    def test_unregistered_fake_workflow_check_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp)
            fake_name = "check_" + "something.py"
            (workflows / "fake.yml").write_text(
                f"steps:\n  - run: python3 .github/scripts/{fake_name}\n",
                encoding="utf-8",
            )
            self.assertEqual(deterministic_workflow_references(workflows), {f".github/scripts/{fake_name}"})


class RunnerBehaviorTests(unittest.TestCase):
    def test_firestore_contention_runner_uses_uv_without_backend_venv(self) -> None:
        source = REPO_ROOT / "backend/testing/desktop_beta_admission/run.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = root / "backend/testing/desktop_beta_admission/run.sh"
            runner.parent.mkdir(parents=True)
            shutil.copy2(source, runner)
            (root / "backend/.python-version").write_text("3.11\n", encoding="utf-8")
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            capture = root / "node-args.txt"
            for name, body in {
                "uv": "#!/bin/sh\nexit 99\n",
                "node": f'''#!/bin/sh
case "$1" in
  -p) echo 22 ;;
  *emulator_config.mjs) printf '45678 45679\\n' ;;
  *supervise.mjs) printf '%s\\n' "$@" > "{capture}" ;;
esac
''',
                "java": "#!/bin/sh\necho '    java.version = 21.0.1' >&2\n",
            }.items():
                path = fake_bin / name
                path.write_text(body, encoding="utf-8")
                path.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            result = subprocess.run(["bash", str(runner)], text=True, capture_output=True, env=env, check=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            captured = capture.read_text(encoding="utf-8")
            self.assertIn("uv run --no-project", captured)
            self.assertIn("--cleanup-path", captured)

    def test_trigger_matching_selects_only_relevant_checks(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        selected = {check.id for check in resolve_checks(manifest, ["app/lib/widgets/example.dart"], "ci")}
        self.assertIn("brand-ui", selected)
        self.assertNotIn("backend-async-blockers", selected)
        self.assertNotIn("backend-route-policy-baseline", selected)

    def test_root_agents_md_selects_agent_doc_checks(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        # `**/AGENTS.md` does not match the root file under fnmatch/PurePath.match,
        # so the root guide needs an explicit trigger or a docs-only root edit
        # skips both the size ratchet and the dead-pointer check.
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, ["AGENTS.md"], lane)}
            self.assertIn("agents-md-lean", selected)
            self.assertIn("agent-doc-references", selected)

    def test_backend_route_change_selects_route_policy_baseline_in_both_lanes(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        changed = ["backend/routers/chat_sessions.py"]
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, changed, lane)}
            self.assertIn("backend-route-policy-baseline", selected)

    def test_failure_class_protocol_runs_in_both_lanes(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, ["app/lib/example.dart"], lane)}
            self.assertIn("failure-class-protocol", selected)

    def test_main_push_excludes_only_pr_body_checks(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        selected = {
            check.id
            for check in resolve_checks(
                manifest,
                ["app/lib/example.dart"],
                "ci",
                include_pr_body_checks=False,
            )
        }
        self.assertNotIn("product-invariants", selected)
        self.assertNotIn("failure-class-protocol", selected)
        self.assertIn("diff-hygiene", selected)

    def test_backend_datetime_sort_sentinel_ratchet_runs_for_backend_sources(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        for lane in ("local", "ci"):
            selected = {check.id for check in resolve_checks(manifest, ["backend/routers/example.py"], lane)}
            self.assertIn("backend-datetime-sort-sentinel-ratchet", selected)

    def test_failure_is_propagated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fail = root / "fail.py"
            fail.write_text("raise SystemExit(7)\n", encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("example.txt\n", encoding="utf-8")
            body = root / "body.txt"
            body.write_text("", encoding="utf-8")
            check = Check("fails", (sys.executable, str(fail)), ("all",), ("ci",), "fixture")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                result = execute_checks(
                    root,
                    [check],
                    changed_files_path=changed,
                    base="base",
                    head="HEAD",
                    pr_body_file=body,
                )
            self.assertEqual(result, 1)


class PlatformTests(unittest.TestCase):
    """Tests for the platform-aware manifest model (#9843 Ticket 02)."""

    def test_macos_check_selected_on_macos(self):
        manifest = Manifest(
            checks=(
                Check(
                    id="mac-only", command=("true",), triggers=("all",), lanes=("ci",), reason="t", platforms=("macos",)
                ),
            ),
            exempt=(),
        )
        selected = resolve_checks(manifest, ["any/file"], "ci", platform="macos")
        self.assertEqual([c.id for c in selected], ["mac-only"])

    def test_macos_check_skipped_on_linux(self):
        manifest = Manifest(
            checks=(
                Check(
                    id="mac-only", command=("true",), triggers=("all",), lanes=("ci",), reason="t", platforms=("macos",)
                ),
            ),
            exempt=(),
        )
        selected = resolve_checks(manifest, ["any/file"], "ci", platform="linux")
        self.assertEqual(selected, [])

    def test_no_platforms_means_all_platforms(self):
        manifest = Manifest(
            checks=(Check(id="portable", command=("true",), triggers=("all",), lanes=("ci",), reason="t"),), exempt=()
        )
        for plat in ("macos", "linux"):
            selected = resolve_checks(manifest, ["any/file"], "ci", platform=plat)
            self.assertEqual([c.id for c in selected], ["portable"])

    def test_exclusive_macos_query_excludes_portable_checks(self):
        manifest = Manifest(
            checks=(
                Check(id="portable", command=("true",), triggers=("all",), lanes=("ci",), reason="portable"),
                Check(
                    id="mac-only",
                    command=("true",),
                    triggers=("all",),
                    lanes=("ci",),
                    reason="macOS",
                    platforms=("macos",),
                ),
            ),
            exempt=(),
        )
        self.assertEqual(
            [check.id for check in resolve_checks(manifest, ["any/file"], "ci", platform="macos")],
            ["portable", "mac-only"],
        )
        self.assertEqual(
            [
                check.id
                for check in resolve_checks(
                    manifest,
                    ["any/file"],
                    "ci",
                    platform="macos",
                    exclusive_platform=True,
                )
            ],
            ["mac-only"],
        )

    def test_machine_readable_selection_carries_path_and_reason(self):
        manifest = Manifest(
            checks=(
                Check(
                    id="target",
                    command=("true",),
                    triggers=("desktop/macos/**",),
                    lanes=("ci",),
                    reason="desktop source changed",
                ),
            ),
            exempt=(),
        )
        selections = resolve_check_selections(manifest, ["desktop/macos/Desktop/Sources/App.swift"], "ci")
        self.assertEqual(len(selections), 1)
        self.assertEqual(selections[0].check.id, "target")
        self.assertEqual(selections[0].matched_paths, ("desktop/macos/Desktop/Sources/App.swift",))
        self.assertEqual(selections[0].check.reason, "desktop source changed")

    def test_skipped_platform_checks_reports_macos_on_linux(self):
        manifest = Manifest(
            checks=(
                Check(
                    id="mac-only", command=("true",), triggers=("all",), lanes=("ci",), reason="t", platforms=("macos",)
                ),
            ),
            exempt=(),
        )
        skipped = skipped_platform_checks(manifest, ["any/file"], "ci", "linux")
        self.assertEqual([c.id for c in skipped], ["mac-only"])

    def test_invalid_platform_rejected_by_validation(self):
        manifest = Manifest(
            checks=(
                Check(
                    id="bad", command=("true",), triggers=("all",), lanes=("ci",), reason="t", platforms=("windows",)
                ),
            ),
            exempt=(),
        )
        errors = validate_manifest(manifest, REPO_ROOT)
        self.assertTrue(any("invalid platforms" in e for e in errors))

    def test_detect_platform_returns_known_value(self):
        plat = detect_platform()
        self.assertIn(plat, VALID_PLATFORMS - {"all"})


class DeferredMarkerTests(unittest.TestCase):
    def test_new_marker_requires_tracking_issue(self) -> None:
        module = load_deferred_marker_module()
        marker = "TO" + "DO"
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix=".manifest-marker-") as tmp:
            root = Path(tmp)
            candidate = root / "fixture.txt"
            changed = root / "changed.txt"
            relative = candidate.relative_to(REPO_ROOT).as_posix()
            changed.write_text(f"{relative}\n", encoding="utf-8")

            candidate.write_text(f"// {marker}: missing owner\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(module.check_new_markers("origin/main", changed), 1)

            candidate.write_text(f"// {marker}(#9448): owned follow-up\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(module.check_new_markers("origin/main", changed), 0)

    def test_marker_guard_ignores_product_text_and_reformatted_existing_comments(self) -> None:
        module = load_deferred_marker_module()
        self.assertIsNone(module.marker_signature('let status = item.completed ? "done" : "todo"'))
        original = "    // TODO: Implement when adding watchOS support"
        reformatted = "  // TODO: Implement when adding watchOS support"
        signature = module.marker_signature(original)
        assert signature is not None
        self.assertEqual(
            module.new_marker_violations([(88, reformatted)], Counter({signature: 1})),
            [],
        )


if __name__ == "__main__":
    unittest.main()
