#!/usr/bin/env python3
"""Fail closed when a production-family mobile package is not pinned to prod."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = (
    "ios-internal-auto",
    "android-internal-auto",
    "ios-prod-testflight",
    "android-prod-internal",
    "ios-prod-patch",
    "android-prod-patch",
    "macos-prod-appstore",
)
DESKTOP_WORKFLOW = "omi-desktop-swift-release"
PIN = "https://api.omi.me/"
DESKTOP_PIN = "https://api.omi.me"


def _workflow_block(text: str, workflow: str) -> str | None:
    match = re.search(rf"(?ms)^  {re.escape(workflow)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text)
    return match.group(1) if match else None


def validate(root: Path) -> list[str]:
    text = (root / "codemagic.yaml").read_text(encoding="utf-8")
    errors: list[str] = []
    for workflow in WORKFLOWS:
        block = _workflow_block(text, workflow)
        assignments = re.findall(r"(?m)^\s*echo API_BASE_URL=([^\s]+) >> \.env\s*$", block or "")
        if assignments != [PIN]:
            errors.append(
                f"{workflow} must contain exactly one immutable API_BASE_URL=https://api.omi.me/ assignment"
            )
    desktop_block = _workflow_block(text, DESKTOP_WORKFLOW)
    desktop_assignments = re.findall(r"(?m)^\s*OMI_PYTHON_API_URL:\s*[\"']?([^\"'\s]+)[\"']?\s*$", desktop_block or "")
    if desktop_assignments != [DESKTOP_PIN]:
        errors.append(
            f"{DESKTOP_WORKFLOW} must contain exactly one immutable OMI_PYTHON_API_URL=https://api.omi.me assignment"
        )
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
