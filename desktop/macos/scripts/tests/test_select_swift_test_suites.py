#!/usr/bin/env python3
"""The shadow selector may narrow only fully mapped test-only diffs."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from select_swift_test_suites import select  # noqa: E402


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = {
            "APIClientRoutingTests": {"APIClientRoutingTests.swift"},
            "AuthRefreshResilienceTests": {"AuthRefreshResilienceTests.swift"},
            "ChatDiscoverabilityTests": {"ChatDiscoverabilityTests.swift"},
            "ChangedTests": {"Nested/ChangedTests.swift"},
            "OtherTests": {"OtherTests.swift"},
        }
        self.runnable = list(self.mapping)

    def test_mapped_test_only_diff_selects_changed_and_smoke(self) -> None:
        selected, reason = select(self.mapping, self.runnable, ["desktop/macos/Desktop/Tests/Nested/ChangedTests.swift"])
        self.assertEqual(selected, self.runnable[:4])
        self.assertEqual(reason, "known test-only input")

    def test_source_and_unknown_test_inputs_keep_full(self) -> None:
        for changed in (["desktop/macos/Desktop/Sources/Foo.swift"],
                        ["desktop/macos/Desktop/Tests/NewTests.swift"], []):
            self.assertEqual(select(self.mapping, self.runnable, changed)[0], self.runnable)


if __name__ == "__main__":
    unittest.main()
