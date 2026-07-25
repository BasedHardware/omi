#!/usr/bin/env python3
"""Select the bounded local checks that predict PR CI from a file diff.

This intentionally describes only checks that are cheap enough to run before a
push.  The full app test/compile matrix and release/platform work stay in CI.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECK_ORDER = (
    "app-dart-format",
    "flutter-l10n",
    "flutter-codegen",
    "desktop-flow-lint",
    "windows-kgworker-native-closure",
    "app-ci-only",
    "desktop-ci-only",
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

DESKTOP_FLOW_LINT_INPUTS = {
    "desktop/macos/scripts/desktop-core-harness.sh",
    "desktop/macos/scripts/desktop-flow-lint.py",
    "desktop/macos/Desktop/Sources/DesktopAutomationBridge.swift",
    "desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController.swift",
    "desktop/macos/Desktop/Sources/Rewind/Core/RewindArtifactGauntlet.swift",
    "desktop/macos/Desktop/Sources/MainWindow/Pages/TasksPage.swift",
    "desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift",
}

WINDOWS_KGWORKER_NATIVE_CLOSURE_INPUTS = {
    "desktop/windows/scripts/kgworker-native-closure.mjs",
    "desktop/windows/scripts/kgworker-native-closure.test.mjs",
    "desktop/windows/electron-builder.config.mjs",
    "desktop/windows/package.json",
    "desktop/windows/pnpm-lock.yaml",
}


def _default_read_text(path: str) -> str | None:
    try:
        return (REPO_ROOT / path).read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return None


def _is_generated_dart(path: str) -> bool:
    return path.endswith((".g.dart", ".gen.dart", ".freezed.dart")) or path.startswith("app/lib/l10n/app_localizations")


def _is_codegen_input(path: str, read_text: Callable[[str], str | None]) -> bool:
    if path in CODEGEN_CONFIG_INPUTS:
        return True
    if not path.startswith("app/lib/") or not path.endswith(".dart") or _is_generated_dart(path):
        return False

    # A deleted Dart library might have owned generated output.  Regenerate in
    # that case rather than guessing from a file that no longer exists.
    source = read_text(path)
    if source is None:
        return True
    return any(marker in source for marker in CODEGEN_MARKERS)


def select_checks(paths: Iterable[str], read_text: Callable[[str], str | None] = _default_read_text) -> list[str]:
    """Return selected checks in stable, agent-readable order."""

    selected: set[str] = set()
    for raw_path in paths:
        path = raw_path.strip()
        if not path:
            continue

        if path.startswith("app/"):
            selected.add("app-ci-only")
        if path.startswith("desktop/macos/"):
            selected.add("desktop-ci-only")

        if path.startswith("app/") and path.endswith(".dart") and not _is_generated_dart(path):
            selected.add("app-dart-format")

        if path.startswith("app/lib/l10n/") and path.endswith(".arb") or path == "app/l10n.yaml":
            selected.add("flutter-l10n")

        if _is_codegen_input(path, read_text):
            selected.add("flutter-codegen")

        if path.startswith("desktop/macos/e2e/") or path in DESKTOP_FLOW_LINT_INPUTS:
            selected.add("desktop-flow-lint")

        if path in WINDOWS_KGWORKER_NATIVE_CLOSURE_INPUTS:
            selected.add("windows-kgworker-native-closure")

    return [check for check in CHECK_ORDER if check in selected]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", type=Path, required=True)
    args = parser.parse_args()

    try:
        paths = args.changed_files.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        parser.error(f"changed-files list not found: {args.changed_files}")

    print("\n".join(select_checks(paths)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
