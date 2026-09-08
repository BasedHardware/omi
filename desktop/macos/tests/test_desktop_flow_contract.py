#!/usr/bin/env python3
"""Prove the flow contract sees every bridge action source.

`desktop_flow_contract` exists so "an added bridge action cannot skip its flow validation
route" — its own words. It failed at exactly that: three actions moved into
`DesktopAutomationBridge+Notifications.swift`, the hand-maintained list still named only the
base file, and `desktop-flow-lint` reported the flows using them as referencing unknown
actions. That failed the pre-push gate on every branch cut from main, on a file the pusher
never touched, while the actions were registered correctly the whole time.
"""

import pathlib
import re
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from desktop_flow_contract import ACTION_SOURCE_RELATIVE_PATHS  # noqa: E402

DESKTOP_MACOS = SCRIPTS.parent
SOURCES = DESKTOP_MACOS / "Desktop" / "Sources"
ACTION_NAME = re.compile(r'name:\s*"([^"]+)"')


class DesktopFlowContractTests(unittest.TestCase):
    def test_every_bridge_file_on_disk_is_an_action_source(self):
        """The regression: a bridge file present but unlisted is invisible to the lint."""
        on_disk = {
            path.relative_to(DESKTOP_MACOS).as_posix()
            for path in SOURCES.glob("DesktopAutomationBridge*.swift")
        }
        self.assertTrue(on_disk, "expected at least one DesktopAutomationBridge source")
        self.assertLessEqual(
            on_disk,
            set(ACTION_SOURCE_RELATIVE_PATHS),
            "a bridge source is not an action source, so the flows using its actions will "
            "be reported as referencing unknown actions",
        )

    def test_the_notifications_extension_actions_are_reachable(self):
        """The two names that were actually reported unknown, pinned by value."""
        registered: set[str] = set()
        for relative in ACTION_SOURCE_RELATIVE_PATHS:
            path = DESKTOP_MACOS / relative
            if path.is_file():
                registered.update(ACTION_NAME.findall(path.read_text(encoding="utf-8")))
        for action in ("settings_notifications_snapshot", "set_notification_settings"):
            self.assertIn(action, registered)

    def test_listed_sources_all_exist(self):
        """Discovery must not invent a path: the lint fails hard on a missing source."""
        for relative in ACTION_SOURCE_RELATIVE_PATHS:
            self.assertTrue(
                (DESKTOP_MACOS / relative).is_file(), f"listed action source is missing: {relative}"
            )


if __name__ == "__main__":
    unittest.main()
