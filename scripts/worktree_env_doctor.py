#!/usr/bin/env python3
"""Fail in seconds when a worktree's local environment cannot run the push checks.

The pre-push gate discovers a missing local prerequisite only when the phase that
needs it runs, often minutes in. A fresh task worktree hit three in a row on one
push: no ``app/.dart_tool/package_config.json``, no ``backend/.venv``, and a
SwiftPM ``.build`` whose ``workspace-state.json`` recorded binary artifacts that
were not on disk. Each cost a full preflight run to find.

This doctor runs first. Given the push's changed files and the CI-prediction
selection, it checks only the prerequisites the selected phases will need, and
prints one command that fixes every state problem it found. ``--fix`` runs that
command. ``--all`` checks the component state a new worktree should have, without
a diff, for worktree bootstrap.

It reads files and runs one interpreter probe; it never builds or resolves
anything unless ``--fix`` is given. Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

APP_PACKAGE_CONFIG = "app/.dart_tool/package_config.json"
APP_PUB_INPUTS = ("app/pubspec.yaml", "app/pubspec.lock")
BACKEND_VENV = "backend/.venv"
SWIFT_PACKAGE = "desktop/macos/Desktop"
WINDOWS_DIR = "desktop/windows"
WINDOWS_REQUIRED_FILES = (
    "desktop/windows/node_modules/.bin/vitest",
    "desktop/windows/node_modules/better-sqlite3/package.json",
    "desktop/windows/node_modules/electron-builder/package.json",
)

# Path triggers copied from the scripts/pre-push phases that need the canonical
# backend interpreter. test_worktree_env_doctor.py parses the hook and fails when
# these drift from it. Bash `case` globs let `*` cross `/`, as fnmatch does.
BACKEND_RUNTIME_ENV_TRIGGERS = (
    "backend/deploy/runtime_env.yaml",
    "backend/deploy/runtime_env/*.yaml",
    "backend/charts/backend-listen/*_values.yaml",
    "backend/charts/backend-listen/**/*_values.yaml",
    "backend/charts/pusher/*_values.yaml",
    "backend/charts/pusher/**/*_values.yaml",
    "backend/scripts/render-backend-runtime-env.py",
    "backend/scripts/validate-backend-runtime-env.py",
    "backend/scripts/runtime_env_capability_contracts.py",
    "backend/scripts/runtime_env_validation/*.py",
    ".github/workflows/gcp_backend*.yml",
    ".github/workflows/gcp_backend*.yaml",
    ".github/workflows/repo-checks.yml",
    ".github/workflows/backend-checks.yml",
    ".github/actions/detect-changes/*",
    ".github/actions/detect-changes/**/*",
)

# backend/scripts/needs-typecheck.sh
BACKEND_TYPECHECK_TRIGGERS = (
    "backend/*.py",
    "backend/pyrightconfig.json",
    "backend/scripts/typecheck.sh",
    "backend/scripts/needs-typecheck.sh",
    "backend/requirements.txt",
    "backend/pylock*.toml",
    ".github/workflows/backend-unit-tests.yml",
    "scripts/pre-push",
)

BACKEND_UNIT_TEST_TRIGGERS = (
    ".gitignore",
    "backend/*.py",
    "backend/**/*.py",
    "backend/*.yaml",
    "backend/**/*.yaml",
    "backend/*.yml",
    "backend/**/*.yml",
    ".github/actions/detect-changes/*",
    ".github/actions/detect-changes/**/*",
    ".github/workflows/backend-checks.yml",
    ".github/workflows/backend-unit-tests.yml",
    ".github/workflows/desktop-checks.yml",
    ".github/workflows/desktop-swift-ci.yml",
    ".github/workflows/repo-checks.yml",
    ".github/workflows/desktop_promote_beta.yml",
    ".github/workflows/desktop_promote_prod.yml",
    ".github/workflows/gcp_backend*.yml",
    ".github/workflows/gcp_notifications_job.yml",
    "scripts/changed-files",
    "scripts/install-git-hooks.sh",
    "scripts/pre-push",
    "scripts/pre-push-singleflight",
)

OPENAPI_CONTRACT_TRIGGERS = (
    "backend/models/*.py",
    "backend/models/**/*.py",
    "backend/routers/*.py",
    "backend/routers/**/*.py",
    "docs/api-reference/app-client-openapi.json",
    "app/lib/backend/http/api/**",
    "app/lib/backend/schema/**",
    ".github/workflows/openapi-contract.yml",
    "scripts/pre-push",
)

RELEASE_GUARD_TRIGGERS = (
    ".github/scripts/check-release-process-guards.py",
    "scripts/run-release-process-guards.sh",
    "backend/tests/unit/test_desktop_release_scripts.py",
)

DESKTOP_SWIFT_TRIGGERS = (
    "desktop/macos/Desktop/*.swift",
    "desktop/macos/Desktop/**/*.swift",
    "desktop/macos/Desktop/Package.swift",
    "desktop/macos/Desktop/Package.resolved",
    "scripts/pre-push",
)

FIRMWARE_SOURCE_PATTERNS = tuple(
    f"{root}/*.{ext}" for root in ("omi", "omiGlass") for ext in ("c", "cc", "cpp", "cxx", "h", "hpp")
)

# (phase, hatch env var, triggers, interpreter modules the phase imports)
BACKEND_PHASES = (
    ("backend runtime env validation", "PRE_PUSH_SKIP_BACKEND_RUNTIME_ENV", BACKEND_RUNTIME_ENV_TRIGGERS, ()),
    ("backend type check", "PRE_PUSH_SKIP_BACKEND_TYPECHECK", BACKEND_TYPECHECK_TRIGGERS, ("pyright",)),
    ("backend unit tests", "PRE_PUSH_SKIP_BACKEND_UNIT_TESTS", BACKEND_UNIT_TEST_TRIGGERS, ("pytest",)),
    ("OpenAPI contract", "PRE_PUSH_SKIP_OPENAPI_CONTRACT", OPENAPI_CONTRACT_TRIGGERS, ()),
    ("release process guards", None, RELEASE_GUARD_TRIGGERS, ("pytest",)),
)

# The canonical-interpreter probe in scripts/dev-harness/_resolve_python.sh.
BACKEND_BASE_MODULES = ("yaml", "dotenv")

SKIP_HATCH = "PRE_PUSH_SKIP_ENV_DOCTOR"


@dataclass
class Finding:
    """One unmet prerequisite.

    ``fix`` is a shell command, run from the repository root, that resolves the
    state problem. ``manual`` is set instead when only the developer can fix it
    (installing a toolchain), so ``--fix`` never installs software.
    """

    component: str
    problem: str
    fix: Optional[str] = None
    manual: Optional[str] = None
    needed_by: tuple[str, ...] = ()


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def fix_command(self) -> Optional[str]:
        fixes: list[str] = []
        for finding in self.findings:
            if finding.fix and finding.fix not in fixes:
                fixes.append(finding.fix)
        if not fixes:
            return None
        return " && ".join([f"cd {shlex.quote(str(REPO_ROOT))}", *fixes])


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def changed_matches(changed: Iterable[str], patterns: Iterable[str]) -> bool:
    patterns = tuple(patterns)
    return any(matches_any(path, patterns) for path in changed)


def hatch_set(env: dict[str, str], name: Optional[str]) -> bool:
    return bool(name) and env.get(name or "") == "1"


# ── individual prerequisite checks ──────────────────────────────────────────


def check_app_dependencies(root: Path, needed_by: tuple[str, ...], which: Callable[[str], Optional[str]]) -> list[Finding]:
    package_config = root / APP_PACKAGE_CONFIG
    fix = "(cd app && flutter pub get)"
    manual = None if which("flutter") else "Install the Flutter version pinned in .github/workflows/repo-checks.yml and put 'flutter' on PATH."
    if not package_config.is_file():
        return [
            Finding(
                "app",
                f"{APP_PACKAGE_CONFIG} is missing, so dart format cannot read the package language version.",
                fix=fix,
                manual=manual,
                needed_by=needed_by,
            )
        ]
    config_mtime = package_config.stat().st_mtime
    newer = [name for name in APP_PUB_INPUTS if (root / name).is_file() and (root / name).stat().st_mtime > config_mtime]
    if newer:
        return [
            Finding(
                "app",
                f"{APP_PACKAGE_CONFIG} is older than {', '.join(newer)}; app dependencies are stale.",
                fix=fix,
                manual=manual,
                needed_by=needed_by,
            )
        ]
    return []


def read_python_version(root: Path) -> Optional[tuple[int, int]]:
    try:
        raw = (root / "backend/.python-version").read_text().strip()
        major, minor = raw.split(".")[:2]
        return int(major), int(minor)
    except (OSError, ValueError):
        return None


def venv_python(root: Path) -> Optional[Path]:
    for candidate in (root / BACKEND_VENV / "bin/python", root / BACKEND_VENV / "Scripts/python.exe"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def probe_interpreter(python: str, modules: Iterable[str]) -> Optional[dict]:
    code = (
        "import importlib.util, json, sys\n"
        "print(json.dumps({'version': list(sys.version_info[:2]),"
        " 'missing': [m for m in sys.argv[1:] if importlib.util.find_spec(m) is None]}))"
    )
    try:
        result = subprocess.run(
            [python, "-c", code, *modules],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def check_backend_venv(
    root: Path,
    needed_by: tuple[str, ...],
    modules: Iterable[str],
    which: Callable[[str], Optional[str]],
    probe: Callable[[str, Iterable[str]], Optional[dict]] = probe_interpreter,
) -> list[Finding]:
    fix = "make setup-backend"
    manual = None if which("uv") else "Install uv (https://docs.astral.sh/uv/getting-started/installation/); make setup-backend needs it."
    venv = root / BACKEND_VENV
    if venv.is_symlink():
        return [
            Finding(
                "backend",
                f"{BACKEND_VENV} is a symlink to {os.readlink(venv)}; each worktree owns its own environment.",
                fix=f"rm {BACKEND_VENV} && {fix}",
                manual=manual,
                needed_by=needed_by,
            )
        ]
    python = venv_python(root)
    if python is None:
        return [
            Finding(
                "backend",
                f"{BACKEND_VENV} has no interpreter; the selected backend checks require the canonical backend/.venv.",
                fix=fix,
                manual=manual,
                needed_by=needed_by,
            )
        ]
    wanted = tuple(dict.fromkeys((*BACKEND_BASE_MODULES, *modules)))
    result = probe(str(python), wanted)
    if result is None:
        return [Finding("backend", f"{python} does not run.", fix=fix, manual=manual, needed_by=needed_by)]
    problems = []
    pinned = read_python_version(root)
    version = tuple(result.get("version") or ())
    if pinned and version != pinned:
        problems.append(f"runs Python {'.'.join(map(str, version))}, but backend/.python-version pins {pinned[0]}.{pinned[1]}")
    missing = result.get("missing") or []
    if missing:
        problems.append(f"cannot import {', '.join(missing)}")
    if problems:
        return [Finding("backend", f"{BACKEND_VENV} is incomplete: {'; '.join(problems)}.", fix=fix, manual=manual, needed_by=needed_by)]
    return []


def _within(path: str, directory: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(directory)]) == os.path.realpath(directory)
    except ValueError:
        return False


def swiftpm_state_problems(build_dir: Path) -> list[str]:
    """Describe where ``workspace-state.json`` disagrees with the disk.

    SwiftPM trusts its recorded state: when it lists a binary artifact or a
    checkout that is gone (or that lives in another tree the directory was
    copied from), ``swift build`` fails with "There is no XCFramework found"
    instead of fetching it again.
    """

    state_path = build_dir / "workspace-state.json"
    if not state_path.is_file():
        return []
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError) as exc:
        return [f"{state_path.name} is unreadable ({exc})"]
    obj = state.get("object") or {}
    missing: list[str] = []
    foreign: list[str] = []
    for artifact in obj.get("artifacts") or []:
        path = artifact.get("path")
        if not path:
            continue
        name = (artifact.get("packageRef") or {}).get("identity") or Path(path).name
        if not os.path.exists(path):
            missing.append(name)
        elif not _within(path, str(build_dir)):
            foreign.append(f"{name} at {path}")
    checkouts = [
        dependency["subpath"]
        for dependency in obj.get("dependencies") or []
        if (dependency.get("state") or {}).get("name") == "sourceControlCheckout"
        and dependency.get("subpath")
        and not (build_dir / "checkouts" / dependency["subpath"]).is_dir()
    ]
    problems: list[str] = []
    if missing:
        problems.append(f"{len(missing)} recorded binary artifact(s) are missing on disk ({_names(missing)})")
    if foreign:
        problems.append(f"{len(foreign)} artifact(s) resolve outside this .build ({_names(foreign)})")
    if checkouts:
        problems.append(f"{len(checkouts)} recorded checkout(s) are missing from .build/checkouts ({_names(checkouts)})")
    return problems


def _names(items: list[str], limit: int = 4) -> str:
    unique = list(dict.fromkeys(items))
    shown = ", ".join(unique[:limit])
    return shown + (f", +{len(unique) - limit} more" if len(unique) > limit else "")


def check_desktop_swiftpm(root: Path, needed_by: tuple[str, ...], which: Callable[[str], Optional[str]], stamp: str) -> list[Finding]:
    build_dir = root / SWIFT_PACKAGE / ".build"
    problems = swiftpm_state_problems(build_dir)
    if not problems:
        return []
    aside = f"{SWIFT_PACKAGE}/.build.stale-{stamp}"
    return [
        Finding(
            "desktop-swift",
            f"{SWIFT_PACKAGE}/.build is stale: workspace-state.json says " + "; ".join(problems) + ".",
            fix=f"mv {SWIFT_PACKAGE}/.build {aside} && xcrun swift package resolve --package-path {SWIFT_PACKAGE}",
            manual=None if which("xcrun") else "Install the Xcode command line tools; the fix runs xcrun swift package resolve.",
            needed_by=needed_by,
        )
    ]


def check_tool(component: str, names: tuple[str, ...], needed_by: tuple[str, ...], manual: str, which: Callable[[str], Optional[str]]) -> list[Finding]:
    if any(which(name) for name in names):
        return []
    return [Finding(component, f"{' or '.join(names)} is not on PATH.", manual=manual, needed_by=needed_by)]


# ── selection ───────────────────────────────────────────────────────────────


def existing(root: Path, changed: Iterable[str]) -> list[str]:
    return [path for path in changed if (root / path).is_file()]


def run_diff_checks(
    root: Path,
    changed: list[str],
    selection: set[str],
    env: dict[str, str],
    python: str,
    which: Callable[[str], Optional[str]] = shutil.which,
    probe: Callable[[str, Iterable[str]], Optional[dict]] = probe_interpreter,
    stamp: Optional[str] = None,
) -> Report:
    report = Report()
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    present = existing(root, changed)

    # Flutter app: dart format reads the package language version from
    # package_config.json; the generated-output phases run flutter in app/.
    app_needs: list[str] = []
    app_dart = [p for p in present if p.startswith("app/") and p.endswith(".dart") and not p.endswith((".g.dart", ".gen.dart"))]
    if app_dart and not hatch_set(env, "PRE_PUSH_SKIP_DART_FORMAT"):
        app_needs.append("Dart formatting")
    generated = sorted({"flutter-codegen", "flutter-l10n"} & selection)
    if generated and not hatch_set(env, "PRE_PUSH_SKIP_FLUTTER_GENERATED"):
        app_needs.append("Flutter generated output")
    if app_needs:
        report.checked.append("app dependencies")
        report.findings += check_app_dependencies(root, tuple(app_needs), which)
    if "app-dart-format" in selection and any(p.endswith(".dart") for p in present) and not hatch_set(env, "PRE_PUSH_SKIP_DART_FORMAT"):
        report.findings += check_tool("app", ("dart",), ("Dart formatting",), "Install Flutter (which bundles dart) and put it on PATH.", which)
    if generated and not hatch_set(env, "PRE_PUSH_SKIP_FLUTTER_GENERATED"):
        report.findings += check_tool("app", ("flutter",), ("Flutter generated output",), "Install Flutter and put 'flutter' on PATH.", which)

    # Backend: every phase below calls require_backend_python.
    backend_needs: list[str] = []
    backend_modules: list[str] = []
    for phase, hatch, triggers, modules in BACKEND_PHASES:
        if hatch_set(env, hatch) or not changed_matches(changed, triggers):
            continue
        backend_needs.append(phase)
        backend_modules += modules
    if backend_needs:
        report.checked.append("backend/.venv")
        report.findings += check_backend_venv(root, tuple(backend_needs), backend_modules, which, probe)

    # Formatter for changed backend Python (scripts/backend-python-format).
    if any(p.startswith("backend/") and p.endswith(".py") for p in present):
        report.findings += check_tool(
            "backend",
            ("uvx", "black"),
            ("backend Python formatting",),
            "Install uv (https://docs.astral.sh/uv/getting-started/installation/); the formatter runs through uvx.",
            which,
        )

    # macOS desktop Swift compile.
    if changed_matches(changed, DESKTOP_SWIFT_TRIGGERS) and not hatch_set(env, "PRE_PUSH_SKIP_DESKTOP_SWIFT"):
        report.checked.append("desktop SwiftPM state")
        report.findings += check_tool("desktop-swift", ("xcrun",), ("desktop Swift compile",), "Push from macOS with the Xcode command line tools installed.", which)
        report.findings += check_desktop_swiftpm(root, ("desktop Swift compile",), which, stamp)

    # Desktop E2E flow lint imports PyYAML in the hook's own interpreter.
    if "desktop-flow-lint" in selection and not hatch_set(env, "PRE_PUSH_SKIP_DESKTOP_FLOW_LINT"):
        report.checked.append("hook interpreter PyYAML")
        result = probe(python, ("yaml",))
        if result is None or result.get("missing"):
            report.findings.append(
                Finding(
                    "desktop-flow-lint",
                    f"the hook interpreter {python} cannot import yaml.",
                    fix="make setup-backend",
                    needed_by=("desktop E2E flow lint",),
                )
            )

    # Windows KG worker native closure.
    if "windows-kgworker-native-closure" in selection and not hatch_set(env, "PRE_PUSH_SKIP_WINDOWS_KGWORKER_NATIVE_CLOSURE"):
        report.checked.append("desktop/windows dependencies")
        needed = ("Windows KG worker native closure",)
        report.findings += check_tool("desktop-windows", ("pnpm",), needed, "Install pnpm and put it on PATH.", which)
        missing = [p for p in WINDOWS_REQUIRED_FILES if not (root / p).is_file()]
        if missing:
            report.findings.append(
                Finding(
                    "desktop-windows",
                    f"desktop/windows dependencies are not installed ({missing[0]} is missing).",
                    fix=f"(cd {WINDOWS_DIR} && pnpm install --frozen-lockfile)",
                    needed_by=needed,
                )
            )

    if any(matches_any(p, FIRMWARE_SOURCE_PATTERNS) for p in present) and not hatch_set(env, "PRE_PUSH_SKIP_FIRMWARE_FORMAT"):
        report.findings += check_tool("firmware", ("clang-format",), ("firmware C/C++ formatting",), "Install clang-format (brew install clang-format).", which)

    workflows = [p for p in present if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))]
    if workflows and not hatch_set(env, "PRE_PUSH_SKIP_ACTIONLINT"):
        report.findings += check_tool("workflows", ("actionlint", "go"), ("actionlint",), "Install actionlint (brew install actionlint) or go.", which)

    return report


def run_all_checks(
    root: Path,
    which: Callable[[str], Optional[str]] = shutil.which,
    probe: Callable[[str, Iterable[str]], Optional[dict]] = probe_interpreter,
    stamp: Optional[str] = None,
) -> Report:
    """Component state a freshly bootstrapped worktree should already have.

    Components whose toolchain is absent are skipped rather than failed: a host
    without Flutter cannot push app changes either, and the diff-scoped run
    reports the missing tool when such a push happens.
    """

    report = Report()
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    report.checked.append("backend/.venv")
    report.findings += check_backend_venv(root, ("bootstrap",), ("pyright", "pytest"), which, probe)
    if which("flutter"):
        report.checked.append("app dependencies")
        report.findings += check_app_dependencies(root, ("bootstrap",), which)
    else:
        report.skipped.append("app dependencies (flutter is not on PATH)")
    if which("xcrun"):
        report.checked.append("desktop SwiftPM state")
        report.findings += check_desktop_swiftpm(root, ("bootstrap",), which, stamp)
    else:
        report.skipped.append("desktop SwiftPM state (xcrun is not on PATH)")
    return report


# ── output and repair ───────────────────────────────────────────────────────


def render(report: Report, stream, bootstrap: bool = False) -> None:
    if report.ok:
        checked = ", ".join(report.checked) if report.checked else "nothing the selected checks need"
        print(f"worktree env doctor: OK ({checked})", file=stream)
        for item in report.skipped:
            print(f"  skipped: {item}", file=stream)
        return
    print(f"FAIL: this worktree is missing {len(report.findings)} local prerequisite(s) for the selected checks.", file=stream)
    for finding in report.findings:
        needed = f" [needed by: {', '.join(finding.needed_by)}]" if finding.needed_by else ""
        print(f"  - {finding.component}: {finding.problem}{needed}", file=stream)
    for item in report.skipped:
        print(f"  skipped: {item}", file=stream)
    manual = list(dict.fromkeys(f.manual for f in report.findings if f.manual))
    if manual:
        print("Install first:", file=stream)
        for item in manual:
            print(f"  - {item}", file=stream)
    command = report.fix_command()
    if command:
        print("Fix everything with:", file=stream)
        print(f"  {command}", file=stream)
        if bootstrap:
            print("or run: python3 scripts/worktree_env_doctor.py --all --fix", file=stream)
    if not bootstrap:
        print(f"Deliberate hatch for the push gate: {SKIP_HATCH}=1 git push", file=stream)


def apply_fixes(report: Report, root: Path) -> bool:
    ok = True
    seen: list[str] = []
    for finding in report.findings:
        if not finding.fix or finding.fix in seen:
            continue
        seen.append(finding.fix)
        print(f"==> {finding.fix}", flush=True)
        result = subprocess.run(["bash", "-c", finding.fix], cwd=root, check=False)
        if result.returncode != 0:
            print(f"FAIL ({result.returncode}): {finding.fix}", file=sys.stderr)
            ok = False
            break
    return ok


def read_lines(path: Optional[str]) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--changed-files", help="file listing the push's changed paths, one per line")
    scope.add_argument("--all", action="store_true", help="check every component a bootstrapped worktree should have")
    parser.add_argument("--selection", default="", help="newline-separated CI-prediction selection from the pre-push hook")
    parser.add_argument("--fix", action="store_true", help="run the fix command, then check again")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if not args.all and hatch_set(env, SKIP_HATCH):
        print(f"Skipping worktree env doctor because {SKIP_HATCH}=1.")
        return 0

    bootstrap = args.all or not args.changed_files

    def check() -> Report:
        if bootstrap:
            return run_all_checks(REPO_ROOT)
        selection = {line.strip() for line in args.selection.splitlines() if line.strip()}
        return run_diff_checks(REPO_ROOT, read_lines(args.changed_files), selection, env, sys.executable)

    report = check()
    if report.ok or not args.fix:
        render(report, sys.stdout if report.ok else sys.stderr, bootstrap)
        return 0 if report.ok else 1

    if not apply_fixes(report, REPO_ROOT):
        render(check(), sys.stderr, bootstrap)
        return 1
    report = check()
    render(report, sys.stdout if report.ok else sys.stderr, bootstrap)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
