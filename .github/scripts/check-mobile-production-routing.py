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
)
PIN = "https://api.omi.me/"


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
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
