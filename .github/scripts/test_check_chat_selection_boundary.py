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
    sources = {
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
    sources.update(conversation_detail_sources())
    return sources

def conversation_detail_sources() -> dict[str, str]:
    return {
        CHECKER.CONVERSATION_DETAIL_FILES[0]: (
            "struct ConversationDetailView {\n"
            "  var summary: some View {\n"
            "    OmiMarkdown(text: selection.content, sender: .ai, appKitProseSelection: true)\n"
            "      .frame(maxWidth: .infinity, alignment: .leading)\n"
            "  }\n"
            "  var actionItem: some View {\n"
            "    Text(item.description)\n"
            "      .scaledFont(size: OmiType.body)\n"
            "      .strikethrough(item.completed)\n"
            "  }\n"
            "}\n"
        ),
        CHECKER.CONVERSATION_DETAIL_FILES[1]: (
            "struct ConversationSummarySections {\n"
            "  var heading: some View {\n"
            "    Text(section.heading)\n"
            "      .scaledFont(size: OmiType.body, weight: .semibold)\n"
            "  }\n"
            "  var body: some View {\n"
            "    OmiMarkdown(text: section.bodyMarkdown, sender: .ai, appKitProseSelection: true)\n"
            "  }\n"
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

    def test_accepts_appkit_prose_in_detail_without_swiftui_selection(self) -> None:
        sources = clean_sources()
        sources.update(conversation_detail_sources())

        self.assertEqual(CHECKER.check_sources(sources), [])

    def test_rejects_any_swiftui_selection_in_conversation_detail_files(self) -> None:
        """The detail files take the transcript's blanket ban: even short
        `Text` rows there (headings, action items) must not carry SwiftUI
        selection — copyable prose in this surface is AppKit-hosted."""
        snippets = {
            CHECKER.CONVERSATION_DETAIL_FILES[0]: (
                "  var actionItem: some View {\n"
                "    Text(item.description).textSelection(.enabled)\n"
                "  }\n"
            ),
            CHECKER.CONVERSATION_DETAIL_FILES[1]: (
                "  var heading: some View {\n"
                "    Text(section.heading)\n"
                "      .textSelection(.enabled)\n"
                "  }\n"
            ),
        }
        for relative, snippet in snippets.items():
            with self.subTest(relative=relative):
                sources = clean_sources()
                sources.update(conversation_detail_sources())
                sources[relative] += snippet

                failures = CHECKER.check_sources(sources)

                self.assertTrue(
                    any(
                        relative in failure and "conversation detail joins" in failure
                        for failure in failures
                    )
                )

    def test_rejects_swiftui_selection_chained_onto_detail_markdown(self) -> None:
        shapes = {
            "same-line": (
                'OmiMarkdown(text: x, sender: .ai).textSelection(.enabled)\n'
            ),
            "next-line": (
                "OmiMarkdown(text: selection.content, sender: .ai)\n"
                "  .textSelection(.enabled)\n"
            ),
            "through-another-modifier": (
                "OmiMarkdown(text: x, sender: .ai)\n"
                "  .padding(4)\n"
                "  .textSelection(.enabled)\n"
            ),
            "nested-parens-and-escape": (
                'OmiMarkdown(text: String(result.content.prefix(200)) + "\\u{2026}", sender: .ai)\n'
                "    .textSelection(.enabled)\n"
            ),
        }
        for relative in CHECKER.CONVERSATION_DETAIL_FILES:
            for name, snippet in shapes.items():
                with self.subTest(relative=relative, shape=name):
                    sources = clean_sources()
                    sources.update(conversation_detail_sources())
                    sources[relative] += snippet

                    failures = CHECKER.check_sources(sources)

                    self.assertTrue(
                        any(
                            relative in failure and "conversation detail joins" in failure
                            for failure in failures
                        )
                    )

    def test_rejects_chained_omimarkdown_selection_on_any_desktop_surface(self) -> None:
        """The rule is repo-wide, not a fixed file list: the next surface that
        reinstalls the banned ancestor is a file this checker has never heard
        of. This is what would have caught conversation detail on the PR that
        introduced it."""
        shapes = {
            "same-line": 'OmiMarkdown(text: x, sender: .ai).textSelection(.enabled)\n',
            "next-line": (
                "OmiMarkdown(text: insight, sender: .ai)\n"
                "  .frame(maxWidth: .infinity)\n"
                "  .textSelection(.enabled)\n"
            ),
        }
        for name, snippet in shapes.items():
            with self.subTest(shape=name):
                sources = clean_sources()
                sources.update(conversation_detail_sources())
                sources["desktop/macos/Desktop/Sources/Surfaces/InsightPanelView.swift"] = (
                    "struct InsightPanelView: View {\n" + snippet + "}\n"
                )

                failures = CHECKER.check_sources(sources)

                self.assertTrue(
                    any(
                        "InsightPanelView.swift" in failure
                        and "must not gain a SwiftUI-selection" in failure
                        for failure in failures
                    )
                )

    def test_short_text_selection_elsewhere_is_not_the_chained_rule(self) -> None:
        """Plain `Text(...).textSelection(.enabled)` on other surfaces — task
        panels, referrals, and the live transcript's per-bubble rows (a
        deliberate sibling, fixed separately) — is not this failure class: a
        single-line `Text` has a stable intrinsic size and installs no overlay
        around tall markdown."""
        sources = clean_sources()
        sources.update(conversation_detail_sources())
        sources["desktop/macos/Desktop/Sources/MainWindow/Components/LiveTranscriptView.swift"] = (
            "struct LiveTranscriptBubble: View {\n"
            "  var body: some View {\n"
            "    Text(segment.text)\n"
            "      .scaledFont(size: OmiType.body)\n"
            "      .textSelection(.enabled)\n"
            "      .padding(.horizontal, OmiSpacing.md)\n"
            "  }\n"
            "}\n"
        )
        sources["desktop/macos/Desktop/Sources/MainWindow/Tasks/TaskDetailPanel.swift"] = (
            "struct TaskRow: View {\n"
            "  var body: some View {\n"
            "    Text(value).textSelection(.enabled)\n"
            "  }\n"
            "}\n"
        )

        self.assertEqual(CHECKER.check_sources(sources), [])



if __name__ == "__main__":
    unittest.main()
