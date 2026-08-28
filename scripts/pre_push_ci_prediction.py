#!/usr/bin/env python3
"""Resolve CI impact from a changed-file list without non-stdlib dependencies.

The pre-push hook consumes the bounded local phases while GitHub Actions
consumes the same plan for component and expensive macOS phases.  The executor
chooses its own budget; path ownership lives here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LOCAL_CHECK_ORDER = (
    "app-dart-format",
    "flutter-l10n",
    "flutter-codegen",
    "desktop-flow-lint",
    "windows-kgworker-native-closure",
    "app-ci-only",
    "desktop-ci-only",
)

PHASE_ORDER = (
    *LOCAL_CHECK_ORDER,
    "app-analysis-tests",
    "app-compile-smoke",
    "desktop-agent-runtime",
    "desktop-swift-tests",
    "desktop-swift-release-compile",
    "desktop-swift-notification-release-regression",
)

CODEGEN_CONFIG_INPUTS = {
    "app/build.yaml",
    "app/pubspec.yaml",
    "app/pubspec.lock",
    "app/lib/pigeon_interfaces.dart",
}

CODEGEN_MARKERS = (
    "@JsonSerializable",
    "@freezed",
    "@Freezed",
    "@HiveType",
    "@Riverpod",
    "@riverpod",
    "@Envied",
    "@Pigeon",
    "part '",
    'part "',
)

WINDOWS_KGWORKER_NATIVE_CLOSURE_INPUTS = {
    "desktop/windows/scripts/kgworker-native-closure.mjs",
    "desktop/windows/scripts/kgworker-native-closure.test.mjs",
    "desktop/windows/electron-builder.config.mjs",
    "desktop/windows/package.json",
    "desktop/windows/pnpm-lock.yaml",
}

# Every value a caller may pass to `--event`. "local" is the pre-push hook; the rest
# are GitHub event names, and each one is a trigger some workflow that reaches this
# script actually declares.
#
# This is a hard-failure surface, not a hint: argparse rejects an unlisted value and
# exits 2, so the calling step dies before it writes a single detect-changes output and
# every job gated on those outputs is skipped. `desktop-swift-ci.yml` declares
# `workflow_dispatch` and forwards `${{ github.event_name }}` straight through, so every
# manual run of it failed at "Detect changed paths" — including the recovery hatch that
# workflow's own `on:` comment documents as the only way to re-mint exact-SHA release
# evidence for a commit already on main.
# `test_every_declared_workflow_trigger_is_an_accepted_event` derives the required set
# from the workflows' own `on:` blocks, so adding a trigger without adding it here fails
# that test instead of failing the first manual run.
ACCEPTED_EVENTS = (
    "local",
    "pull_request",
    "push",
    "workflow_dispatch",
)

ROUTING_INPUTS = {
    ".github/checks-manifest.yaml",
    ".github/scripts/run_checks.py",
    ".github/scripts/test_run_checks.py",
    ".github/scripts/test_desktop_manifest_routes.py",
    ".github/scripts/test_desktop_swift_ci_contract.py",
    ".github/actions/detect-changes/action.yml",
    ".github/workflows/desktop-swift-ci.yml",
    ".github/workflows/mobile-app-checks.yml",
    "scripts/pre_push_ci_prediction.py",
    ".github/scripts/test_pre_push_ci_prediction.py",
}

FLUTTER_GENERATION_DEFINITION_INPUTS = {
    ".github/workflows/mobile-app-checks.yml",
}

FLUTTER_GENERATION_DEFINITION_PREFIXES = (".github/actions/detect-changes/",)

DESKTOP_SWIFT_TEST_INPUTS = {
    "desktop/macos/Desktop/Package.swift",
    "desktop/macos/Desktop/Package.resolved",
    "desktop/macos/test.sh",
    "desktop/macos/scripts/run-swift-ci.sh",
    "desktop/macos/scripts/swift-test-suites.sh",
    "desktop/macos/scripts/swift-test-skips.json",
    "desktop/macos/scripts/swift-test-skip-ratchet.py",
    "desktop/macos/scripts/check_desktop_test_quality.py",
    "desktop/macos/scripts/check-main-actor-xctest-hooks.py",
}

DESKTOP_NOTIFICATION_REGRESSION_INPUTS = {
    "desktop/macos/Desktop/Sources/AppState/AppState+Permissions.swift",
    "desktop/macos/Desktop/Sources/OmiApp.swift",
    "desktop/macos/Desktop/Sources/Providers/ChatToolExecutor.swift",
    "desktop/macos/Desktop/Sources/Providers/DeviceProvider.swift",
}

DESKTOP_AGENT_RUNTIME_INPUTS = {
    "desktop/macos/run.sh",
    "desktop/macos/scripts/audit-desktop-bundle-deps.sh",
    "desktop/macos/scripts/prepare-agent-runtime.sh",
    "desktop/macos/scripts/prepare-desktop-bundle-native-deps.sh",
    "desktop/macos/scripts/test-tool-surfaces.sh",
    "desktop/macos/scripts/agent-logic-harness.sh",
    "codemagic.yaml",
    "scripts/pre-push",
}


def _load_desktop_flow_lint_inputs() -> frozenset[str]:
    """Load the lint's own source inventory without importing PyYAML."""
    path = REPO_ROOT / "desktop/macos/scripts/desktop_flow_contract.py"
    spec = importlib.util.spec_from_file_location("desktop_flow_contract", path)
    if spec is None or spec.loader is None:  # pragma: no cover - repository corruption
        raise RuntimeError(f"cannot load desktop flow contract from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return frozenset(module.FLOW_LINT_INPUTS)


DESKTOP_FLOW_LINT_INPUTS = _load_desktop_flow_lint_inputs()


def _load_desktop_release_pathspecs() -> tuple[str, ...]:
    """Load the planner's releasable pathspecs so exact-SHA CI stays aligned."""
    path = REPO_ROOT / ".github/scripts/plan-desktop-release.py"
    spec = importlib.util.spec_from_file_location("plan_desktop_release_for_ci", path)
    if spec is None or spec.loader is None:  # pragma: no cover - repository corruption
        raise RuntimeError(f"cannot load desktop release planner from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.DESKTOP_RELEASE_PATHS)


DESKTOP_RELEASE_PATHSPECS = _load_desktop_release_pathspecs()


def _default_read_text(path: str) -> str | None:
    try:
        return (REPO_ROOT / path).read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return None


def read_text_at_revision(revision: str) -> Callable[[str], str | None]:
    """Return a stdlib-only reader for paths as they existed at *revision*."""

    def read(path: str) -> str | None:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            return None
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return None

    return read


def _is_generated_dart(path: str) -> bool:
    return path.endswith((".g.dart", ".gen.dart", ".freezed.dart")) or path.startswith("app/lib/l10n/app_localizations")


def _contains_codegen_marker(source: str | None) -> bool:
    return source is not None and any(marker in source for marker in CODEGEN_MARKERS)


def _is_codegen_input(
    path: str,
    read_text: Callable[[str], str | None],
    read_base_text: Callable[[str], str | None],
) -> bool:
    if path in CODEGEN_CONFIG_INPUTS or path.startswith("app/assets/"):
        return True
    if not path.startswith("app/lib/") or not path.endswith(".dart") or _is_generated_dart(path):
        return False

    source = read_text(path)
    base_source = read_base_text(path)
    # A deleted library or a removed final generator marker has no post-change
    # annotation to inspect. The base revision is the ownership proof.
    return (
        source is None
        or base_source is None
        or _contains_codegen_marker(source)
        or _contains_codegen_marker(base_source)
    )


def _is_app_l10n_input(path: str) -> bool:
    return (path.startswith("app/lib/l10n/") and path.endswith(".arb")) or path == "app/l10n.yaml"


def _defines_flutter_generation(path: str) -> bool:
    # Routing metadata cannot make a committed generated file stale, but the
    # files that define the regeneration commands or forward their outputs can:
    # they must keep waking the regeneration lanes they own.
    return path in FLUTTER_GENERATION_DEFINITION_INPUTS or path.startswith(FLUTTER_GENERATION_DEFINITION_PREFIXES)


def _is_app_compile_smoke_input(path: str) -> bool:
    if path.startswith("app/lib/l10n/app_") and (path.endswith(".arb") or path.endswith(".dart")):
        return False
    return path.startswith(
        (
            "app/lib/",
            "app/android/",
            "app/ios/",
            "app/setup/prebuilt/",
            "app/setup/scripts/",
            "app/config/",
            "app/assets/",
        )
    ) or path in {
        "app/pubspec.yaml",
        "app/pubspec.lock",
        "app/build.yaml",
        "app/analysis_options.yaml",
        "app/l10n.yaml",
        "app/flavorizr.yaml",
    }


def _matches_desktop_release_pathspec(path: str, pathspec: str) -> bool:
    """Match a changed file against one planner git pathspec."""
    if path == pathspec:
        return True
    # Planner directory pathspecs (for example desktop/macos) have no suffix.
    if Path(pathspec).suffix:
        return False
    prefix = pathspec.rstrip("/") + "/"
    return path.startswith(prefix)


def _is_releasable_desktop_path(path: str) -> bool:
    if path.startswith("desktop/macos/changelog/"):
        return False
    if path in {"desktop/macos/CHANGELOG.json", "desktop/macos/AGENTS.md"}:
        return False
    return any(_matches_desktop_release_pathspec(path, pathspec) for pathspec in DESKTOP_RELEASE_PATHSPECS)


def _is_desktop_swift_test_input(path: str) -> bool:
    return (
        path in DESKTOP_SWIFT_TEST_INPUTS
        or (
            path.startswith(("desktop/macos/Desktop/Sources/", "desktop/macos/Desktop/Tests/"))
            and path.endswith(".swift")
        )
        or (path.startswith("desktop/macos/tests/") and path.endswith(".sh"))
    )


def _is_desktop_notification_input(path: str) -> bool:
    return (
        path in DESKTOP_NOTIFICATION_REGRESSION_INPUTS
        or (path.startswith("desktop/macos/Desktop/Sources/") and path.endswith(".swift") and "Notification" in path)
        or (path.startswith("desktop/macos/Desktop/Tests/") and path.endswith(".swift") and "Notification" in path)
    )


def _is_desktop_agent_runtime_input(path: str) -> bool:
    return path in DESKTOP_AGENT_RUNTIME_INPUTS or path.startswith(
        ("desktop/macos/agent/", "desktop/macos/pi-mono-extension/")
    )


@dataclass(frozen=True)
class ImpactPlan:
    """Selected phase IDs in stable display order."""

    phases: frozenset[str]

    def includes(self, phase: str) -> bool:
        return phase in self.phases

    def ordered(self) -> list[str]:
        return [phase for phase in PHASE_ORDER if phase in self.phases]


def resolve_impact(
    paths: Iterable[str],
    *,
    read_text: Callable[[str], str | None] = _default_read_text,
    read_base_text: Callable[[str], str | None] | None = None,
    event: str = "local",
) -> ImpactPlan:
    """Resolve component and expensive CI phases for a changed path set."""
    # Callers that only need the current-tree behavior (for example a focused
    # unit fixture) can omit the base reader. Diff callers pass one so deleted
    # inputs and marker removals remain conservative.
    read_base_text = read_base_text or read_text
    selected: set[str] = set()
    normalized_paths = [raw_path.strip() for raw_path in paths if raw_path.strip()]
    selector_changed = any(
        path in ROUTING_INPUTS or path.startswith(".github/actions/detect-changes/") for path in normalized_paths
    )

    for path in normalized_paths:
        if path.startswith("app/"):
            # Unknown paths within a component remain conservative: they wake
            # its normal analyzer/test lane rather than silently doing nothing.
            selected.update({"app-ci-only", "app-analysis-tests"})
            if _is_app_compile_smoke_input(path):
                selected.add("app-compile-smoke")
            if path.endswith(".dart") and not _is_generated_dart(path):
                selected.add("app-dart-format")
            if _is_app_l10n_input(path):
                selected.add("flutter-l10n")
            if _is_codegen_input(path, read_text, read_base_text):
                selected.add("flutter-codegen")

        if path.startswith("desktop/macos/"):
            if _is_releasable_desktop_path(path):
                selected.add("desktop-ci-only")
            if _is_desktop_swift_test_input(path):
                selected.add("desktop-swift-tests")
            if _is_desktop_notification_input(path):
                selected.add("desktop-swift-notification-release-regression")
            if _is_desktop_agent_runtime_input(path):
                selected.add("desktop-agent-runtime")
            if path.startswith("desktop/macos/e2e/") or path in DESKTOP_FLOW_LINT_INPUTS:
                selected.add("desktop-flow-lint")

        if path in WINDOWS_KGWORKER_NATIVE_CLOSURE_INPUTS:
            selected.add("windows-kgworker-native-closure")

    if any(_defines_flutter_generation(path) for path in normalized_paths):
        selected.update({"flutter-codegen", "flutter-l10n"})

    if selector_changed:
        # The selector is the boundary. A change to it conservatively wakes each
        # component lane it can influence. It deliberately excludes the
        # generated-artifact regeneration lanes (flutter-codegen, flutter-l10n):
        # editing routing metadata cannot make a committed generated file stale,
        # and waking build_runner from a manifest-only diff costs ~17 minutes at
        # push time. Those lanes stay owned by their real generator inputs.
        selected.update(
            {
                "app-ci-only",
                "app-analysis-tests",
                "app-compile-smoke",
                "desktop-ci-only",
                "desktop-flow-lint",
                "desktop-swift-tests",
            }
        )

    releasable_desktop = any(_is_releasable_desktop_path(path) for path in normalized_paths) or selector_changed
    package_changed = any(
        path in {"desktop/macos/Desktop/Package.swift", "desktop/macos/Desktop/Package.resolved"}
        for path in normalized_paths
    )
    if releasable_desktop:
        selected.add("desktop-ci-only")
        # Release compile runs on PRs too, not just pushes: strict-concurrency
        # errors that only manifest under whole-module release optimization
        # otherwise land on main and wedge the release train (#11373/#11374 —
        # the KG ResolveOutcome Sendable break shipped through a PR whose debug
        # lane stayed green and blocked every candidate for three merges).
        selected.add("desktop-swift-release-compile")

    return ImpactPlan(frozenset(selected))


def select_checks(
    paths: Iterable[str],
    read_text: Callable[[str], str | None] = _default_read_text,
    read_base_text: Callable[[str], str | None] | None = None,
) -> list[str]:
    """Return the bounded local subset in stable, agent-readable order."""
    plan = resolve_impact(paths, read_text=read_text, read_base_text=read_base_text)
    return [phase for phase in LOCAL_CHECK_ORDER if plan.includes(phase)]


def github_outputs(plan: ImpactPlan) -> dict[str, str]:
    """Map shared phases to the established detect-changes action contract."""
    return {
        "has_app_codegen": str(plan.includes("flutter-codegen")).lower(),
        "has_app_l10n": str(plan.includes("flutter-l10n")).lower(),
        "has_flutter_generated": str(plan.includes("flutter-codegen") or plan.includes("flutter-l10n")).lower(),
        "has_app_compile_smoke": str(plan.includes("app-compile-smoke")).lower(),
        "has_app_dart": str(plan.includes("app-analysis-tests")).lower(),
        "has_desktop_agent_runtime": str(plan.includes("desktop-agent-runtime")).lower(),
        "should_run": str(plan.includes("desktop-ci-only")).lower(),
        "should_run_tests": str(plan.includes("desktop-swift-tests")).lower(),
        "should_release_compile": str(plan.includes("desktop-swift-release-compile")).lower(),
        "should_notification_release_regression": str(
            plan.includes("desktop-swift-notification-release-regression")
        ).lower(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--base", help="Optional Git revision used to detect deleted inputs and marker removals.")
    parser.add_argument("--event", choices=ACCEPTED_EVENTS, default="local")
    parser.add_argument("--github-output", type=Path, help="Append established detect-changes outputs to this file.")
    parser.add_argument("--output", choices=("lines", "json"), default="lines")
    args = parser.parse_args()

    try:
        paths = args.changed_files.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        parser.error(f"changed-files list not found: {args.changed_files}")

    plan = resolve_impact(
        paths,
        read_base_text=read_text_at_revision(args.base) if args.base else None,
        event=args.event,
    )
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            for name, value in github_outputs(plan).items():
                output.write(f"{name}={value}\n")

    if args.output == "json":
        print(json.dumps({"phases": plan.ordered(), "github_outputs": github_outputs(plan)}, sort_keys=True))
    else:
        print("\n".join(plan.ordered()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
