#!/usr/bin/env python3
"""Self-tests for the analytics reachability static tripwire."""

from __future__ import annotations

import unittest

from check_analytics_reachability import (
    audit_platform,
    dart_call_counts,
    dart_methods,
    swift_call_counts,
    swift_methods,
    typescript_methods,
    windows_call_counts,
)

EMPTY_BASELINE = {
    "public_orphans": {},
    "private_orphans": {},
    "multi_call_minimums": {},
}


class AnalyticsReachabilityTests(unittest.TestCase):
    def test_flutter_lexes_methods_and_qualified_calls(self) -> None:
        manager = """
          class AnalyticsManager {
            void deviceConnected() => track('Device Connected');
            void _helper() { track('helper'); }
            void wrapper() { _helper(); }
          }
        """
        sources = ["""
              PlatformManager.instance.analytics.deviceConnected();
              AnalyticsManager().deviceConnected();
              // PlatformManager.instance.analytics.wrapper();
              const fake = 'AnalyticsManager().wrapper()';
              AnalyticsManager().wrapper();
            """]
        methods = dart_methods(manager)
        self.assertEqual([method.name for method in methods], ["deviceConnected", "_helper", "wrapper"])
        self.assertEqual(dart_call_counts(sources), {"deviceConnected": 2, "wrapper": 1})

    def test_swift_lexes_visibility_empty_body_and_calls(self) -> None:
        manager = """
          class AnalyticsManager {
            func live() { PostHogManager.shared.track("Live") }
            func empty() {}
            private func helper() { PostHogManager.shared.track("Helper") }
            func wrapper() { helper() }
          }
        """
        methods = swift_methods(manager)
        self.assertFalse(next(method for method in methods if method.name == "helper").public)
        self.assertFalse(next(method for method in methods if method.name == "empty").body)
        calls = swift_call_counts(["""
                  AnalyticsManager.shared.live()
                  // AnalyticsManager.shared.empty()
                  let fake = "AnalyticsManager.shared.empty()"
                  AnalyticsManager.shared.wrapper()
                """])
        self.assertEqual(calls, {"live": 1, "wrapper": 1})

    def test_swift_property_visibility_does_not_leak_onto_the_next_method(self) -> None:
        methods = swift_methods("""
              class AnalyticsManager {
                private var capture: (@MainActor (String, [String: Any]) -> Void)?

                /// Doc comment between the property and the method.
                func setCapture(_ value: (@MainActor (String, [String: Any]) -> Void)?) { capture = value }
              }
            """)
        self.assertTrue(next(method for method in methods if method.name == "setCapture").public)

    def test_windows_counts_only_imported_production_aliases(self) -> None:
        manager = """
          export function trackEvent(event: string, properties = {}): void { fetch(event, properties) }
          export function trackHow(source: string): void { trackEvent(source) }
        """
        source = """
          import { trackEvent as emit, trackHow } from '../lib/analytics'
          emit('started')
          trackHow('friend')
          // emit('comment')
          const fake = "trackHow('string')"
        """
        self.assertEqual(
            [method.name for method in typescript_methods(manager)],
            ["trackEvent", "trackHow"],
        )
        self.assertEqual(windows_call_counts([source]), {"trackEvent": 1, "trackHow": 1})

    def test_call_site_drop_is_rejected(self) -> None:
        methods = dart_methods("class AnalyticsManager { void deviceConnected() => track('Device Connected'); }")
        baseline = {
            **EMPTY_BASELINE,
            "multi_call_minimums": {"flutter": {"deviceConnected": 2}},
        }
        errors = audit_platform("flutter", methods, {"deviceConnected": 1}, baseline)
        self.assertIn("flutter.deviceConnected: production call sites fell 2->1", errors)

    def test_new_or_empty_public_and_unreachable_private_are_rejected(self) -> None:
        methods = swift_methods("""
              class AnalyticsManager {
                func noCaller() { PostHogManager.shared.track("x") }
                func empty() {}
                private func deadCollector() { print("dead") }
              }
            """)
        errors = audit_platform("macos", methods, {}, EMPTY_BASELINE)
        self.assertTrue(any("noCaller: no production call site" in error for error in errors))
        self.assertTrue(any("empty: empty analytics method" in error for error in errors))
        self.assertTrue(any("deadCollector: unreachable private analytics helper" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
