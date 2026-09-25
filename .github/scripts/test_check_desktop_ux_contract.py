#!/usr/bin/env python3
"""Tests for check_desktop_ux_contract.py (INV-UI-2).

Each rule is proven to *fail* on the shape of a defect that shipped, and to stay quiet on the shared
component that replaces it — the floor the invariant registry asks of every static guard.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_desktop_ux_contract as guard  # noqa: E402

SRC = guard.SOURCES_ROOT


def rule(rule_id: str) -> guard.Rule:
    return guard.RULE_BY_ID[rule_id]


class RuleCountingTests(unittest.TestCase):
    def test_hand_rolled_back_and_close(self) -> None:
        self.assertEqual(guard.count(rule("hand-rolled-back"), 'Image(systemName: "chevron.left")'), 1)
        self.assertEqual(guard.count(rule("hand-rolled-back"), 'Image(systemName: "chevron.up")'), 1)
        self.assertEqual(guard.count(rule("hand-rolled-back"), 'BackChip("Conversations") { pop() }'), 0)
        self.assertEqual(guard.count(rule("hand-rolled-close"), 'Image(systemName: "xmark")'), 1)
        self.assertEqual(guard.count(rule("hand-rolled-close"), 'Image(systemName: "xmark.circle.fill")'), 1)
        self.assertEqual(guard.count(rule("hand-rolled-close"), "DismissButton(action: close)"), 0)

    def test_system_alert_and_pasteboard(self) -> None:
        self.assertEqual(guard.count(rule("system-alert"), '.alert("Delete Conversation", isPresented: $x) {'), 1)
        self.assertEqual(guard.count(rule("system-alert"), ".shellConfirmation(isPresented: $x,"), 0)
        self.assertEqual(guard.count(rule("raw-pasteboard"), "NSPasteboard.general.setString(text, forType: .string)"), 1)
        self.assertEqual(guard.count(rule("raw-pasteboard"), 'OmiToastCenter.shared.copy(text, confirming: "Copied")'), 0)

    def test_dates_fonts_radii(self) -> None:
        self.assertEqual(guard.count(rule("date-format-string"), 'f.dateFormat = "h:mm a"'), 1)
        self.assertEqual(guard.count(rule("raw-system-font"), ".font(.system(size: 13, weight: .medium))"), 1)
        self.assertEqual(guard.count(rule("literal-font-size"), ".scaledFont(size: 12)"), 1)
        self.assertEqual(guard.count(rule("literal-font-size"), ".scaledFont(size: OmiType.body)"), 0)
        self.assertEqual(guard.count(rule("literal-corner-radius"), "RoundedRectangle(cornerRadius: 8)"), 1)
        self.assertEqual(guard.count(rule("literal-corner-radius"), "RoundedRectangle(cornerRadius: OmiChrome.cardRadius)"), 0)

    def test_ascii_ellipsis_only_in_ui_copy(self) -> None:
        self.assertEqual(guard.count(rule("ascii-ellipsis"), 'Text("Loading tasks...")'), 1)
        self.assertEqual(guard.count(rule("ascii-ellipsis"), 'Label("Edit title...", systemImage: "pencil")'), 1)
        self.assertEqual(guard.count(rule("ascii-ellipsis"), 'Text("Loading tasks…")'), 0)
        # A log line is not UI copy.
        self.assertEqual(guard.count(rule("ascii-ellipsis"), 'log("Starting...")'), 0)

    def test_cursor_push(self) -> None:
        self.assertEqual(guard.count(rule("raw-cursor-push"), "if hovering { NSCursor.pointingHand.push() }"), 1)
        self.assertEqual(guard.count(rule("raw-cursor-push"), ".pointingHandOnHover()"), 0)

    def test_scaled_progress_view_across_lines_and_modifier_chains(self) -> None:
        r = rule("scaled-progress-view")
        # The shapes that shipped: one line, a chain split over lines, and a style or tint in between.
        self.assertEqual(guard.count(r, "ProgressView().scaleEffect(0.6)"), 1)
        self.assertEqual(guard.count(r, "ProgressView()\n  .scaleEffect(1.2)\n  .tint(Ink.secondary)"), 1)
        self.assertEqual(
            guard.count(r, "ProgressView()\n  .progressViewStyle(.circular)\n  .tint(Ink.surface)\n  .scaleEffect(1.2)"), 1
        )
        self.assertEqual(guard.count(r, 'ProgressView("Loading")\n  .frame(width: 10, height: 10)\n  .scaleEffect(0.5)'), 1)
        # The replacements stay quiet.
        self.assertEqual(guard.count(r, "ProgressView()\n  .controlSize(.small)"), 0)
        self.assertEqual(guard.count(r, 'GlassLoadingState(label: "Loading tasks…")'), 0)
        # A scale on something that is not a spinner is not this rule's business.
        self.assertEqual(guard.count(r, "Image(systemName: \"star\")\n  .scaleEffect(isPulsing ? 1.5 : 1)"), 0)
        self.assertEqual(guard.count(r, "ProgressView()\nText(\"x\").scaleEffect(2)"), 0)

    def test_scaled_progress_view_allow_marker_on_any_line_of_the_match(self) -> None:
        r = rule("scaled-progress-view")
        text = "ProgressView()\n  .scaleEffect(0.4)  // omi-ux-allow: scaled-progress-view -- 8pt badge"
        self.assertEqual(guard.count(r, text), 0)
        self.assertEqual(guard.count(r, "// ProgressView().scaleEffect(0.5)"), 0)

    def test_hand_rolled_more_menu(self) -> None:
        self.assertEqual(
            guard.count(rule("hand-rolled-more-menu"), 'PageQueryActionLabel(icon: "ellipsis", title: "More")'), 1
        )
        self.assertEqual(
            guard.count(rule("hand-rolled-more-menu"), 'PageMoreMenu(help: "More task actions", accessibilityIdentifier: "x") {'),
            0,
        )
        self.assertTrue(guard.is_owner(rule("hand-rolled-more-menu"), SRC + "MainWindow/Components/PageQueryToolbar.swift"))

    def test_comments_do_not_count_but_strings_do(self) -> None:
        self.assertEqual(guard.count(rule("system-alert"), "// never use .alert( here"), 0)
        self.assertEqual(guard.count(rule("system-alert"), "/* .alert( */ let x = 1"), 0)
        # `//` inside a string is not a comment start.
        text = 'let url = "https://omi.me"; Text("Wait...")'
        self.assertEqual(guard.count(rule("ascii-ellipsis"), text), 1)

    def test_allow_marker_exempts_only_its_rule(self) -> None:
        line = 'Image(systemName: "chevron.left")  // omi-ux-allow: hand-rolled-back -- notch surface'
        self.assertEqual(guard.count(rule("hand-rolled-back"), line), 0)
        other = 'Image(systemName: "xmark")  // omi-ux-allow: hand-rolled-back -- wrong rule'
        self.assertEqual(guard.count(rule("hand-rolled-close"), other), 1)

    def test_owner_files_may_spell_the_primitive(self) -> None:
        self.assertTrue(guard.is_owner(rule("hand-rolled-close"), SRC + "MainWindow/Components/NavigationControls.swift"))
        self.assertTrue(guard.is_owner(rule("raw-system-font"), SRC + "Theme/OmiFont.swift"))
        self.assertFalse(guard.is_owner(rule("hand-rolled-close"), SRC + "MainWindow/Pages/TasksPage.swift"))

    def test_only_desktop_swift_sources_are_in_scope(self) -> None:
        self.assertTrue(guard.is_ux_source(SRC + "MainWindow/Pages/TasksPage.swift"))
        self.assertFalse(guard.is_ux_source(SRC + "Generated/Foo.swift"))
        self.assertFalse(guard.is_ux_source("app/lib/main.dart"))
        self.assertFalse(guard.is_ux_source("desktop/macos/Desktop/Tests/FooTests.swift"))


class RatchetTests(unittest.TestCase):
    """End to end against a throwaway git repo: base commit, then a HEAD edit."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.path = SRC + "MainWindow/Pages/Example.swift"
        self.write('Text("hi")\nImage(systemName: "xmark")\n')
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        self.changed = self.root / "changed.txt"
        self.changed.write_text(self.path + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.check_call(["git", "-C", str(self.root), *args])

    def write(self, text: str) -> None:
        target = self.root / self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def run_guard(self) -> int:
        return guard.main(["--changed-files", str(self.changed), "--base", "HEAD", "--root", str(self.root)])

    def test_existing_debt_may_stay(self) -> None:
        self.write('Text("hello")\nImage(systemName: "xmark")\n')
        self.assertEqual(self.run_guard(), 0)

    def test_adding_a_hand_rolled_close_fails(self) -> None:
        self.write('Image(systemName: "xmark")\nImage(systemName: "xmark")\n')
        self.assertEqual(self.run_guard(), 1)

    def test_paying_debt_down_passes(self) -> None:
        self.write("DismissButton(action: close)\n")
        self.assertEqual(self.run_guard(), 0)

    def test_new_file_starts_at_zero(self) -> None:
        self.path = SRC + "MainWindow/Pages/NewPage.swift"
        self.write('.alert("Delete?", isPresented: $x) {}\n')
        self.changed.write_text(self.path + "\n")
        self.assertEqual(self.run_guard(), 1)


if __name__ == "__main__":
    unittest.main()
