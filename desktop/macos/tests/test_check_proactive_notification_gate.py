#!/usr/bin/env python3
"""Prove the proactive-notification-gate checker catches the bug it exists for.

A checker that has never failed is not a guard. These cases are the two real lanes
that were found bypassing `NotificationService`, reduced to fixtures, plus the
false-positive shapes that would make the checker untrustworthy if it flagged them.
"""

import importlib.util
import pathlib
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check-proactive-notification-gate.py"
_spec = importlib.util.spec_from_file_location("gate_checker", SCRIPT)
gate_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate_checker)


class ProactiveNotificationGateCheckerTests(unittest.TestCase):
    def _scan(self, files: dict[str, str]):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "Sources"
            for rel, body in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            return gate_checker.violations(root)

    def test_flags_the_notch_moments_shape(self):
        """The real regression: a proactive lane posting straight to the primitive."""
        found = self._scan(
            {
                "FloatingControlBar/NotchMomentsCoordinator.swift": """
                private func post(title: String, message: String) {
                  _ = FloatingControlBarManager.shared.showNotification(
                    ownerID: ownerID, title: title, message: message)
                }
                """
            }
        )
        self.assertEqual(len(found), 1)
        self.assertIn("NotchMomentsCoordinator.swift", found[0][0])

    def test_allows_the_gated_service_itself(self):
        found = self._scan(
            {
                "ProactiveAssistants/Services/NotificationService.swift": """
                let presentation = FloatingControlBarManager.shared.showNotification(
                  ownerID: ownerID, title: title, message: message)
                """
            }
        )
        self.assertEqual(found, [])

    def test_allows_functional_callers_on_the_allowlist(self):
        found = self._scan(
            {
                "TrialBannerService.swift": "FloatingControlBarManager.shared.showNotification(\n)",
                "Onboarding/OnboardingChatView.swift": "FloatingControlBarManager.shared.showNotification(\n)",
            }
        )
        self.assertEqual(found, [])

    def test_ignores_the_primitive_named_in_a_comment(self):
        """Prose about the rule, including this PR's own rationale, must not trip it."""
        found = self._scan(
            {
                "Some/Lane.swift": """
                // Do not call FloatingControlBarManager.shared.showNotification( here —
                /* FloatingControlBarManager.shared.showNotification( bypasses the gates */
                func post() { NotificationService.shared.sendNotification() }
                """
            }
        )
        self.assertEqual(found, [])

    def test_ignores_the_primitive_inside_a_string_literal(self):
        found = self._scan(
            {"Some/Lane.swift": 'let hint = "FloatingControlBarManager.shared.showNotification("\n'}
        )
        self.assertEqual(found, [])

    def test_reports_the_line_number_of_the_call(self):
        found = self._scan(
            {
                "Some/Lane.swift": "\n\n\nFloatingControlBarManager.shared.showNotification(\n)\n",
            }
        )
        self.assertEqual(found[0][1], 4)

    def test_does_not_scan_tests(self):
        found = self._scan({"Tests/SomeTests.swift": "FloatingControlBarManager.shared.showNotification(\n)"})
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
