#!/usr/bin/env python3
"""Behavioral fixtures for the live-chat selection boundary checker."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_chat_selection_boundary",
    SCRIPT_DIR / "check_chat_selection_boundary.py",
)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def clean_sources() -> dict[str, str]:
    return {
        CHECKER.LIVE_TRANSCRIPT_FILES[0]: (
            "struct ChatBubble { let body = OmiMarkdown(text: text, sender: .ai) }\n"
        ),
        CHECKER.LIVE_TRANSCRIPT_FILES[1]: (
            "struct ChatMessagesView { let body = LazyVStack { ChatBubble() } }\n"
        ),
        CHECKER.MARKDOWN_FILE: (
            "struct OmiMarkdown { var body: some View { Text(text).textSelection(.disabled) } }\n"
        ),
        CHECKER.SELECTION_FILE: (
            "struct ChatSelectableProseText: NSViewRepresentable {\n"
            "  func makeNSView(context: Context) -> NSTextView { ChatProseTextView() }\n"
            "}\n"
        ),
    }


class ChatSelectionBoundaryTests(unittest.TestCase):
    def test_accepts_copy_only_live_transcript(self) -> None:
        self.assertEqual(CHECKER.check_sources(clean_sources()), [])

    def test_rejects_enabled_selection_in_every_protected_surface(self) -> None:
        for relative in CHECKER.LIVE_TRANSCRIPT_FILES:
            with self.subTest(relative=relative):
                sources = clean_sources()
                sources[relative] += "let selectable = Text(\"reply\").textSelection(.enabled)\n"

                failures = CHECKER.check_sources(sources)

                self.assertTrue(any(relative in failure and "SelectionOverlay" in failure for failure in failures))

    def test_rejects_selection_escape_hatch(self) -> None:
        sources = clean_sources()
        sources[CHECKER.MARKDOWN_FILE] += "let textSelectionEnabled = true\n"

        failures = CHECKER.check_sources(sources)

        self.assertTrue(any("escape hatch" in failure for failure in failures))

    def test_requires_explicit_disabled_boundary(self) -> None:
        sources = clean_sources()
        sources[CHECKER.MARKDOWN_FILE] = "struct OmiMarkdown { var body: some View { Text(text) } }\n"

        failures = CHECKER.check_sources(sources)

        self.assertTrue(any("explicitly disable" in failure for failure in failures))

    def test_requires_the_selection_surface_to_stay_appkit(self) -> None:
        """The remedy is an NSTextView owning its own selection. A SwiftUI
        rewrite of this file would put SelectionOverlay back in the transcript
        under a name the pattern check cannot see."""
        sources = clean_sources()
        sources[CHECKER.SELECTION_FILE] = (
            "struct ChatSelectableProseText: View { var body: some View { Text(text) } }\n"
        )

        failures = CHECKER.check_sources(sources)

        self.assertTrue(any("NSTextView" in failure for failure in failures))

    def test_rejects_missing_protected_source(self) -> None:
        sources = clean_sources()
        missing = CHECKER.LIVE_TRANSCRIPT_FILES[1]
        del sources[missing]

        failures = CHECKER.check_sources(sources)

        self.assertIn(f"{missing}: protected live-transcript source is missing", failures)


if __name__ == "__main__":
    unittest.main()
