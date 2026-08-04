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
from unittest.mock import patch

from git_bash import bash_executable, bash_path, native_path_from_bash
from run_checks import (
    VALID_PLATFORMS,
    Check,
    Manifest,
    command_for_host,
    detect_platform,
    execute_checks,
    load_manifest,
    resolve_check_selections,
    resolve_checks,
    resolve_explicit_checks,
    run_git,
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
    invoking_blocks = [node for node in main_blocks if any(isinstance(inner, ast.Call) for inner in ast.walk(node))]
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
            "from pathlib import Path\n" "\n" "def test_something(tmp_path: Path) -> None:\n" "    assert True\n"
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
        self.assertIn("no TestCase subclass", non_self_running_reason(unittest_main_without_test_case) or "")

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
    def test_run_git_decodes_unicode_checkout_path_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "路径 checkout"
            root.mkdir()
            env = os.environ.copy()
            for key in tuple(env):
                if key.startswith("GIT_"):
                    del env[key]
            subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)

            with patch.dict(os.environ, env, clear=True):
                resolved = run_git(root, "rev-parse", "--show-toplevel")

        self.assertEqual(Path(resolved).resolve(), root.resolve())

    def test_windows_manifest_interpreters_use_the_active_toolchain(self) -> None:
        with patch("run_checks.bash_executable", return_value="C:\\Git\\bin\\bash.exe"):
            self.assertEqual(
                command_for_host(["bash", "scripts/check.sh"], platform_name="nt"),
                ["C:\\Git\\bin\\bash.exe", "scripts/check.sh"],
            )
        self.assertEqual(
            command_for_host(
                ["python3", ".github/scripts/check.py"],
                platform_name="nt",
                python_executable="C:\\Python\\python.exe",
            ),
            ["C:\\Python\\python.exe", ".github/scripts/check.py"],
        )

    def test_non_interpreter_and_non_windows_commands_are_unchanged(self) -> None:
        node_command = ["node", "--test", "test.mjs"]
        bash_command = ["bash", "scripts/check.sh"]

        self.assertIs(command_for_host(node_command, platform_name="nt"), node_command)
        self.assertIs(command_for_host(bash_command, platform_name="posix"), bash_command)

    def test_execute_checks_normalizes_the_manifest_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = root / "changed.txt"
            changed.write_text("example.txt\n", encoding="utf-8")
            body = root / "body.txt"
            body.write_text("", encoding="utf-8")
            check = Check("shell", ("bash", "check.sh"), ("all",), ("ci",), "fixture")

            with (
                patch("run_checks.command_for_host", return_value=["git-bash.exe", "check.sh"]) as normalize,
                patch(
                    "run_checks.subprocess.run",
                    return_value=subprocess.CompletedProcess(["git-bash.exe", "check.sh"], 0),
                ) as run,
                redirect_stdout(StringIO()),
            ):
                result = execute_checks(
                    root,
                    [check],
                    changed_files_path=changed,
                    base="base",
                    head="HEAD",
                    pr_body_file=body,
                )

            self.assertEqual(result, 0)
            normalize.assert_called_once_with(["bash", "check.sh"])
            run.assert_called_once_with(["git-bash.exe", "check.sh"], cwd=root, check=False)

    def test_windows_bash_resolution_uses_the_git_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            git_root = Path(tmp)
            git = git_root / "cmd/git.exe"
            git.parent.mkdir()
            git.touch()
            bash = git_root / "bin/bash.exe"
            bash.parent.mkdir()
            bash.touch()

            resolved = bash_executable(
                platform_name="nt",
                which=lambda name: str(git) if name == "git" else None,
            )

            self.assertTrue(Path(resolved).samefile(bash))

    def test_windows_bash_path_is_converted_back_to_native(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="C:\\Temp\\guard.py\n", stderr="")

        converted = native_path_from_bash(
            "/tmp/guard.py",
            "git-bash.exe",
            platform_name="nt",
            run=fake_run,
        )

        self.assertEqual(converted, Path("C:\\Temp\\guard.py"))
        self.assertEqual(
            commands,
            [["git-bash.exe", "-c", 'cygpath -w "$1"', "bash", "/tmp/guard.py"]],
        )

    def test_windows_native_path_is_converted_for_bash(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="/c/Temp/body.md\n", stderr="")

        converted = bash_path(
            Path("C:\\Temp\\body.md"),
            "git-bash.exe",
            platform_name="nt",
            run=fake_run,
        )

        self.assertEqual(converted, "/c/Temp/body.md")
        self.assertEqual(
            commands,
            [["git-bash.exe", "-c", 'cygpath -u "$1"', "bash", "C:\\Temp\\body.md"]],
        )

    @unittest.skipIf(os.name == "nt", "requires a POSIX shell")
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
                "node": f"""#!/bin/sh
case "$1" in
  -p) echo 22 ;;
  *emulator_config.mjs) printf '45678 45679\\n' ;;
  *supervise.mjs) printf '%s\\n' "$@" > "{capture}" ;;
esac
""",
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

    def test_manifest_only_trigger_requires_own_entry_change(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        selected = {
            check.id
            for check in resolve_checks(
                manifest,
                [".github/checks-manifest.yaml"],
                "ci",
                platform="macos",
                manifest_changed_ids={"backend-deploy-source-admission"},
            )
        }
        self.assertIn("backend-deploy-source-admission", selected)
        self.assertNotIn("rayban-dat-build-wrapper", selected)

    def test_manifest_only_trigger_without_diff_context_selects_all_manifest_checks(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        selected = {
            check.id
            for check in resolve_checks(
                manifest,
                [".github/checks-manifest.yaml"],
                "ci",
                platform="macos",
            )
        }
        self.assertIn("rayban-dat-build-wrapper", selected)

    def test_manifest_worktree_edit_selects_only_changed_check_entry(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        selected = {
            check.id
            for check in resolve_checks(
                manifest,
                [".github/checks-manifest.yaml"],
                "local",
                platform="macos",
                manifest_changed_ids={"backend-runtime-env-compose"},
            )
        }
        self.assertIn("backend-runtime-env-compose", selected)
        self.assertNotIn("rayban-dat-build-wrapper", selected)

    def test_posix_contracts_skip_windows_without_dropping_linux_ci(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        expected_by_path = {
            "app/ios/Podfile": {
                "rayban-dat-plugin-boundary",
                "rayban-dat-xcode-graph",
                "rayban-dat-build-wrapper",
            },
            ".github/workflows/desktop_qualify_beta.yml": {
                "desktop-release-one-path-contract",
            },
        }
        for path, expected in expected_by_path.items():
            windows = {check.id for check in resolve_checks(manifest, [path], "ci", platform="windows")}
            linux = {check.id for check in resolve_checks(manifest, [path], "ci", platform="linux")}
            self.assertTrue(expected.isdisjoint(windows), path)
            self.assertTrue(expected <= linux, path)

    def test_shared_windows_entrypoints_route_their_behavioral_contracts(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        expected_by_path = {
            "Makefile": {"dev-harness-unit-tests", "setup-pre-push-prerequisites"},
            "scripts/dev-harness/_resolve_python.sh": {
                "dev-harness-unit-tests",
                "desktop-release-process-guards",
                "pre-tag-readiness-contract",
            },
            "scripts/pre-push-singleflight": {"pr-preflight-contract-tests"},
            ".github/scripts/preflight_runner.py": {"pr-preflight-contract-tests"},
            "desktop/macos/scripts/check-e2e-flow-coverage.py": {
                "desktop-e2e-flow-coverage",
                "pr-preflight-contract-tests",
            },
            ".github/scripts/git_bash.py": {
                "check-manifest-contract",
                "desktop-release-process-guards",
                "desktop-swiftlint-config",
                "pre-tag-readiness-behavior",
            },
        }
        for path, expected in expected_by_path.items():
            selected = {check.id for check in resolve_checks(manifest, [path], "ci", platform="macos")}
            self.assertTrue(expected <= selected, f"{path}: missing {sorted(expected - selected)}")

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

    def test_release_process_guard_uses_locked_pyyaml_in_every_declared_lane(self) -> None:
        """The guard must never depend on a runner-global PyYAML install."""
        manifest = load_manifest(MANIFEST_PATH)
        check = next(check for check in manifest.checks if check.id == "desktop-release-process-guards")
        self.assertEqual(check.command, ("bash", "scripts/run-release-process-guards.sh"))
        for lane in ("local", "ci"):
            selected = resolve_checks(manifest, list(check.triggers), lane)
            self.assertIn(check, selected)

        runner = REPO_ROOT / check.command[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copied_runner = root / check.command[1]
            copied_runner.parent.mkdir(parents=True)
            shutil.copy2(runner, copied_runner)
            resolver = root / "scripts/dev-harness/_resolve_python.sh"
            resolver.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "scripts/dev-harness/_resolve_python.sh", resolver)

            sync = root / "backend/scripts/sync-python-deps.sh"
            sync.parent.mkdir(parents=True)
            python = root / "backend/.venv/bin/python"
            sync.write_text(
                f'''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "{python.parent}"
cat > "{python}" <<'PYTHON'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-c" ]]; then
  [[ "$2" == "import yaml" ]]
  exit
fi
printf '%s\\n' "$@" > "{root / 'guard-args.txt'}"
PYTHON
chmod +x "{python}"
''',
                encoding="utf-8",
            )
            sync.chmod(0o755)
            guard = root / ".github/scripts/check-release-process-guards.py"
            guard.parent.mkdir(parents=True, exist_ok=True)
            guard.write_text("# fixture\n", encoding="utf-8")

            try:
                bash = bash_executable()
            except FileNotFoundError as exc:
                self.skipTest(str(exc))
            env = os.environ.copy()
            env["PYTHON"] = "ambient-python-must-not-run"
            result = subprocess.run(
                [bash, str(copied_runner)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            recorded_guard = (root / "guard-args.txt").read_text(encoding="utf-8").strip()
            self.assertTrue(
                native_path_from_bash(recorded_guard, bash).samefile(guard),
                f"release guard received {recorded_guard!r}, expected {str(guard)!r}",
            )

        self.assertRegex(
            (REPO_ROOT / "backend/requirements.txt").read_text(encoding="utf-8"),
            r"(?im)^pyyaml==6\.0\.1$",
        )
        for lock in REPO_ROOT.glob("backend/pylock*.toml"):
            self.assertRegex(
                lock.read_text(encoding="utf-8"),
                r'(?ms)^\[\[packages\]\]\nname = "pyyaml"\nversion = "6\.0\.1"$',
            )

    def test_runtime_env_compose_uses_locked_pyyaml_in_every_declared_lane(self) -> None:
        """The compose check must never depend on a runner-global PyYAML install."""
        manifest = load_manifest(MANIFEST_PATH)
        check = next(check for check in manifest.checks if check.id == "backend-runtime-env-compose")
        self.assertEqual(check.command, ("bash", "backend/scripts/check_runtime_env_compose.sh"))
        for lane in ("local", "ci"):
            selected = resolve_checks(manifest, list(check.triggers), lane)
            self.assertIn(check, selected)

        runner = REPO_ROOT / check.command[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copied_runner = root / check.command[1]
            copied_runner.parent.mkdir(parents=True)
            shutil.copy2(runner, copied_runner)
            resolver = root / "scripts/dev-harness/_resolve_python.sh"
            resolver.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "scripts/dev-harness/_resolve_python.sh", resolver)

            sync = root / "backend/scripts/sync-python-deps.sh"
            sync.parent.mkdir(parents=True, exist_ok=True)
            python = root / "backend/.venv/bin/python"
            compose = root / "backend/deploy/compose_runtime_env.py"
            compose.parent.mkdir(parents=True)
            compose.write_text("# fixture\n", encoding="utf-8")
            sync.write_text(
                f'''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "{python.parent}"
cat > "{python}" <<'PYTHON'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-c" ]]; then
  [[ "$2" == "import yaml" ]]
  exit
fi
printf '%s\\n' "$@" > "{root / 'compose-args.txt'}"
PYTHON
chmod +x "{python}"
''',
                encoding="utf-8",
            )
            sync.chmod(0o755)

            try:
                bash = bash_executable()
            except FileNotFoundError as exc:
                self.skipTest(str(exc))
            env = os.environ.copy()
            env["PYTHON"] = "ambient-python-must-not-run"
            result = subprocess.run(
                [bash, str(copied_runner)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            recorded_lines = (root / "compose-args.txt").read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(recorded_lines), 1)
            recorded_script = native_path_from_bash(recorded_lines[0], bash)
            self.assertTrue(
                recorded_script.samefile(compose),
                f"compose check received {recorded_lines[0]!r}, expected {str(compose)!r}",
            )
            self.assertIn("--check", recorded_lines[1:])


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

    def test_explicit_check_ids_preserve_manifest_commands(self):
        manifest = Manifest(
            checks=(
                Check(
                    id="portable",
                    command=("python3", "check.py"),
                    triggers=("never/**",),
                    lanes=("ci",),
                    reason="test",
                ),
            ),
            exempt=(),
        )

        selections = resolve_explicit_checks(
            manifest,
            ["portable"],
            "ci",
            include_pr_body_checks=True,
            platform="windows",
        )

        self.assertEqual([selection.check.id for selection in selections], ["portable"])
        with self.assertRaisesRegex(ValueError, "unknown check id"):
            resolve_explicit_checks(
                manifest,
                ["missing"],
                "ci",
                include_pr_body_checks=True,
                platform="windows",
            )

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
                Check(id="bad", command=("true",), triggers=("all",), lanes=("ci",), reason="t", platforms=("plan9",)),
            ),
            exempt=(),
        )
        errors = validate_manifest(manifest, REPO_ROOT)
        self.assertTrue(any("invalid platforms" in e for e in errors))

    def test_detect_platform_maps_windows(self):
        with patch("run_checks._platform_mod.system", return_value="Windows"):
            self.assertEqual(detect_platform(), "windows")

    def test_detect_platform_returns_known_value(self):
        plat = detect_platform()
        self.assertIn(plat, VALID_PLATFORMS - {"all"})


class DeferredMarkerTests(unittest.TestCase):
    def test_git_content_reads_are_utf8(self) -> None:
        module = load_deferred_marker_module()
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(module.subprocess, "run", return_value=completed) as run:
            self.assertEqual(module.added_lines("origin/main", "fixture.txt"), [])
            self.assertEqual(module.marker_counts_at_base("origin/main", "fixture.txt"), Counter())

        content_reads = [call for call in run.call_args_list if call.args[0][1] in {"diff", "show"}]
        self.assertEqual(len(content_reads), 2)
        for call in content_reads:
            self.assertEqual(call.kwargs.get("encoding"), "utf-8")

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
