#!/usr/bin/env python3
"""Reject direct completion-handler UserNotifications registrations outside the bridge."""

from __future__ import annotations

import re
import sys
from pathlib import Path


# omi-test-quality: source-inspection -- static contract: a framework callback registered outside the
# nonisolated bridge can trap before a caller gets a chance to hop to MainActor (incident #10072).
ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "desktop" / "macos" / "Desktop" / "Sources"
BRIDGE = SOURCES / "ProactiveAssistants" / "ProactiveAssistantsPlugin+NotificationSettings.swift"
FORBIDDEN_CALLBACKS = (
    re.compile(r"UNUserNotificationCenter\.current\(\)\.getNotificationSettings\s*\{"),
    re.compile(r"UNUserNotificationCenter\.current\(\)\.requestAuthorization\s*\([^\n]*\)\s*\{"),
    re.compile(r"UNUserNotificationCenter\.current\(\)\.add\s*\([^\n]*\)\s*\{"),
)


def main() -> int:
    violations: list[str] = []
    for source in SOURCES.rglob("*.swift"):
        if source == BRIDGE:
            continue
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if any(pattern.search(line) for pattern in FORBIDDEN_CALLBACKS):
                violations.append(f"{source.relative_to(ROOT)}:{line_number}")

    if violations:
        print(
            "UserNotifications completion registrations must use UserNotificationCallbackBridge; "
            "direct callbacks can inherit MainActor and trap on the framework XPC queue:",
            file=sys.stderr,
        )
        print("\n".join(violations), file=sys.stderr)
        return 1

    print("UserNotifications callback boundary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
