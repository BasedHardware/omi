#!/usr/bin/env python3
"""Lint desktop E2E flow YAML files for tier metadata and registered bridge actions."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - surfaced in CI with install hint
    print(
        "desktop-flow-lint: PyYAML is required; install with `python3 -m pip install PyYAML`",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = SCRIPT_DIR.parent
FLOWS_DIR = DESKTOP_DIR / "e2e" / "flows"
BRIDGE_SOURCE = DESKTOP_DIR / "Desktop/Sources/DesktopAutomationBridge.swift"
REWIND_GAUNTLET_SOURCE = DESKTOP_DIR / "Desktop/Sources/Rewind/Core/RewindArtifactGauntlet.swift"
HUB_SOURCE = DESKTOP_DIR / "Desktop/Sources/FloatingControlBar/RealtimeHubController.swift"
VIEW_MODEL_ACTION_SOURCES = (
    DESKTOP_DIR / "Desktop/Sources/MainWindow/Pages/TasksPage.swift",
    DESKTOP_DIR / "Desktop/Sources/MainWindow/Pages/MemoriesPage.swift",
    DESKTOP_DIR / "Desktop/Sources/MainWindow/ChatFirst/ChatFirstAutomationRuntime.swift",
)

TYPED_STEP_KEYS = {
    "bridge.navigate",
    "bridge.action",
    "visual.export",
    "visual.action_sequence",
    "state.expect",
    "log.expect",
    "trace.expect",
    "ax.activate",
    "ax.expect",
    "power.sample",
}

MANUAL_TIER = "manual"
FAULT_TIER = "fault"
ALLOWED_TIERS = {0, 1, 2, 3, MANUAL_TIER, FAULT_TIER}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def registered_actions() -> set[str]:
    actions: set[str] = set()
    pattern = re.compile(r'name:\s*"([^"]+)"')
    for path in (BRIDGE_SOURCE, REWIND_GAUNTLET_SOURCE, HUB_SOURCE, *VIEW_MODEL_ACTION_SOURCES):
        if not path.is_file():
            fail(f"missing automation source: {path}")
        actions.update(pattern.findall(path.read_text(encoding="utf-8")))
    return actions


def collect_bridge_action_names(step: dict) -> list[str]:
    names: list[str] = []
    if "bridge.action" in step:
        payload = step.get("bridge.action") or {}
        if isinstance(payload, dict) and payload.get("name"):
            names.append(str(payload["name"]))
    return names


def stable_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value))


def lint_ax_step(path: Path, step: dict) -> list[str]:
    errors: list[str] = []
    if "ax.activate" in step:
        payload = step.get("ax.activate") or {}
        if not isinstance(payload, dict) or not stable_identifier(payload.get("identifier")):
            errors.append(f"{path.name}: ax.activate requires a stable identifier")
        elif payload.get("action", "click") not in {"click", "press"}:
            errors.append(f"{path.name}: ax.activate action must be click or press")

    if "ax.expect" in step:
        payload = step.get("ax.expect") or {}
        if not isinstance(payload, dict):
            errors.append(f"{path.name}: ax.expect must be a mapping")
            return errors
        for key in ("identifiers_visible", "focus_order"):
            value = payload.get(key)
            if value is None:
                continue
            values = [value] if isinstance(value, str) else value
            if not isinstance(values, list) or not all(stable_identifier(item) for item in values):
                errors.append(f"{path.name}: ax.expect {key} must contain stable identifiers")
        focus_order = payload.get("focus_order")
        if (
            isinstance(focus_order, list)
            and all(stable_identifier(item) for item in focus_order)
            and len(set(focus_order)) != len(focus_order)
        ):
            errors.append(f"{path.name}: ax.expect focus_order must not repeat an identifier")
        labels = payload.get("voiceover_labels")
        if labels is not None and (
            not isinstance(labels, dict)
            or not all(
                stable_identifier(identifier) and isinstance(label, str) and label
                for identifier, label in labels.items()
            )
        ):
            errors.append(f"{path.name}: ax.expect voiceover_labels must map stable identifiers to non-empty labels")
    return errors


def is_typed_flow(flow: dict, steps: list) -> bool:
    if flow.get("tier") == MANUAL_TIER:
        return False
    if any("do" in step for step in steps if isinstance(step, dict)):
        return False
    return any(any(key in step for key in TYPED_STEP_KEYS) for step in steps if isinstance(step, dict))


def lint_flow(path: Path, actions: set[str]) -> list[str]:
    errors: list[str] = []
    flow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(flow, dict):
        return [f"{path.name}: flow root must be a mapping"]

    tier = flow.get("tier")
    if tier is None:
        errors.append(f"{path.name}: missing required tier metadata")
    elif tier not in ALLOWED_TIERS:
        errors.append(f"{path.name}: invalid tier {tier!r}; expected 0-3, manual, or fault")

    covers = flow.get("covers") or []
    repo_root = DESKTOP_DIR.parent.parent
    if covers and tier != MANUAL_TIER:
        for cover in covers:
            raw = str(cover)
            candidates = [
                repo_root / raw,
                repo_root / "desktop" / "macos" / raw.removeprefix("desktop/"),
            ]
            if not any(candidate.exists() for candidate in candidates):
                errors.append(f"{path.name}: stale covers path missing: {cover}")

    steps = flow.get("steps") or []
    if not isinstance(steps, list):
        errors.append(f"{path.name}: steps must be a list")
        return errors

    if not is_typed_flow(flow, steps):
        return errors

    for step in steps:
        if not isinstance(step, dict):
            continue
        if "do" in step:
            errors.append(f"{path.name}: typed flow must not contain do steps")
            continue
        errors.extend(lint_ax_step(path, step))
        for name in collect_bridge_action_names(step):
            if name not in actions:
                errors.append(f"{path.name}: unknown bridge action {name!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint desktop core E2E flows")
    parser.add_argument("--flows-dir", default=str(FLOWS_DIR))
    args = parser.parse_args()

    flows_dir = Path(args.flows_dir)
    if not flows_dir.is_dir():
        fail(f"flows directory missing: {flows_dir}")

    actions = registered_actions()
    all_errors: list[str] = []
    flow_paths = sorted(flows_dir.glob("*.yaml"))
    if not flow_paths:
        fail(f"no flow files under {flows_dir}")

    for path in flow_paths:
        all_errors.extend(lint_flow(path, actions))

    if all_errors:
        for error in all_errors:
            print(error, file=sys.stderr)
        print(f"desktop-flow-lint: {len(all_errors)} error(s)", file=sys.stderr)
        return 1

    print(f"desktop-flow-lint OK ({len(flow_paths)} flows, {len(actions)} registered actions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
