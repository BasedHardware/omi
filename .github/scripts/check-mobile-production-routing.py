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
PIN = "echo API_BASE_URL=https://api.omi.me/ >> .env"


def validate(root: Path) -> list[str]:
    text = (root / "codemagic.yaml").read_text(encoding="utf-8")
    errors: list[str] = []
    for workflow in WORKFLOWS:
        match = re.search(rf"(?ms)^  {re.escape(workflow)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text)
        if not match or PIN not in match.group(1):
            errors.append(f"{workflow} must pin API_BASE_URL=https://api.omi.me/")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
