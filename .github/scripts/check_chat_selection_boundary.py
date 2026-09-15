#!/usr/bin/env python3
"""Static boundary for FC-selection-overlay-layout-loop.

Omi Beta 0.12.146 reopened the failure class from PRs #9267 and #10471 when
PR #10834 added native SwiftUI selection back to settled chat messages. The
running app then spent every sampled main-thread stack in SelectionOverlay,
setFont, intrinsic-size invalidation, and AttributeGraph while memory grew
without bound.

SwiftUI has no type-level API that prevents an ancestor or message renderer
from installing SelectionOverlay. This deliberately narrow source tripwire
therefore protects the authoritative live-transcript files. Behavioral resize
coverage remains in ChatTimelineContinuityTests.

The bar is on `SelectionOverlay`, not on selecting. The transcript now hosts
selection through `ChatSelectableProse` — one `NSTextView` per prose block,
which *is* its own selection and installs no per-`Text` overlay for a parent
rebuild to thrash. That file is protected here too, so the AppKit path can
never quietly acquire the SwiftUI one.

The conversation-detail summary pane joined the same failure class when its
markdown gained a SwiftUI-selection ancestor: the pane hosts the tallest
attributed block in the app, and a background list refresh or app-catalog
load re-rendering that ancestor re-laid-out the visible summary 2–3 times
while the reader scrolled. Two guards came out of that:

- The conversation-detail files carry the same blanket ban as the
  transcript: no SwiftUI native selection there at all. Selectable summary
  prose is hosted through `OmiMarkdown(appKitProseSelection: true)`.
- A repo-wide chained-modifier rule: `OmiMarkdown(` followed, within its
  SwiftUI modifier chain, by enabled native selection must fail CI wherever
  it appears. That is what would have caught conversation detail on the PR
  that introduced it. Short plain-`Text` selections elsewhere (task panels,
  referrals, the live transcript's per-bubble rows) still pass: a
  single-line `Text` has a stable intrinsic size and is not this failure
  class.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LIVE_TRANSCRIPT_FILES = (
    "desktop/macos/Desktop/Sources/MainWindow/Components/ChatBubble.swift",
    "desktop/macos/Desktop/Sources/MainWindow/Components/ChatMessagesView.swift",
    "desktop/macos/Desktop/Sources/MainWindow/Components/OmiMarkdown.swift",
    "desktop/macos/Desktop/Sources/MainWindow/Components/ChatSelectableProse.swift",
)
MARKDOWN_FILE = LIVE_TRANSCRIPT_FILES[2]
SELECTION_FILE = LIVE_TRANSCRIPT_FILES[3]

# The conversation-detail summary is the same failure class on a new host: it
# renders the tallest markdown in the app, and a SwiftUI-selection ancestor
# chained onto `OmiMarkdown` installs SelectionOverlay on exactly that block.
# These files take the transcript's blanket ban — even their short `Text`
# rows (section headings, action items) stay SwiftUI-selection-free, because
# copyable prose here is hosted by AppKit, not by an overlay.
CONVERSATION_DETAIL_FILES = (
    "desktop/macos/Desktop/Sources/MainWindow/Pages/ConversationDetailView.swift",
    "desktop/macos/Desktop/Sources/MainWindow/Components/ConversationSummarySections.swift",
)

# The chained-modifier rule scans every desktop Swift source, not a fixed
# list: the next surface that reinstalls the banned ancestor is usually a
# file this checker has never heard of. Generated sources are out of scope,
# matching the formatter's exclusion.
DESKTOP_SWIFT_ROOT = "desktop/macos/Desktop/Sources"
DESKTOP_SWIFT_EXCLUDED_PARTS = ("Generated",)

FORBIDDEN_PATTERNS = {
    ".textSelection(.enabled)": (
        "this protected surface must not install SwiftUI SelectionOverlay; selection belongs "
        "to ChatSelectableProse, whose NSTextView owns it without one"
    ),
    "textSelectionEnabled": (
        "OmiMarkdown must not expose a native-selection escape hatch"
    ),
}


def omimarkdown_swiftui_selection_lines(source: str) -> list[int]:
    """Line numbers (1-based) where enabled native selection chains onto an
    `OmiMarkdown(...)` call: the modifier sits on the same line as the call,
    or on the chain of modifier lines (first non-whitespace character `.`)
    directly below it. Deliberately a line heuristic rather than a paren
    parser: it never false-positives on the short plain-`Text` selections
    other surfaces legitimately keep, which a naive "OmiMarkdown followed by
    .textSelection" regex cannot promise across Swift escapes like
    `\\u{2026}` inside nested call arguments."""
    lines = source.splitlines()
    hits: list[int] = []
    for index, line in enumerate(lines):
        if ".textSelection(.enabled)" not in line:
            continue
        anchor = index
        while anchor > 0 and lines[anchor - 1].lstrip().startswith("."):
            anchor -= 1
        # Same line (`OmiMarkdown(...).textSelection(.enabled)`) or the head of
        # the modifier chain one line above it.
        if "OmiMarkdown(" in lines[anchor] or (anchor > 0 and "OmiMarkdown(" in lines[anchor - 1]):
            hits.append(index + 1)
    return hits


def check_sources(sources: Mapping[str, str]) -> list[str]:
    failures: list[str] = []

    for relative in LIVE_TRANSCRIPT_FILES:
        source = sources.get(relative)
        if source is None:
            failures.append(f"{relative}: protected live-transcript source is missing")
            continue

        for pattern, explanation in FORBIDDEN_PATTERNS.items():
            for line_number, line in enumerate(source.splitlines(), start=1):
                if pattern in line:
                    failures.append(f"{relative}:{line_number}: {explanation}")

    for relative in CONVERSATION_DETAIL_FILES:
        source = sources.get(relative)
        if source is None:
            failures.append(f"{relative}: protected conversation-detail source is missing")
            continue

        for pattern, explanation in FORBIDDEN_PATTERNS.items():
            for line_number, line in enumerate(source.splitlines(), start=1):
                if pattern in line:
                    failures.append(
                        f"{relative}:{line_number}: conversation detail joins the transcript's "
                        f"selection ban ({explanation}); selectable summary prose is hosted "
                        "through OmiMarkdown(appKitProseSelection: true)"
                    )

    for relative, source in sources.items():
        if relative in LIVE_TRANSCRIPT_FILES or relative in CONVERSATION_DETAIL_FILES:
            continue
        for line_number in omimarkdown_swiftui_selection_lines(source):
            failures.append(
                f"{relative}:{line_number}: OmiMarkdown must not gain a SwiftUI-selection "
                "ancestor anywhere on desktop; selectable prose is hosted through "
                "OmiMarkdown(appKitProseSelection: true), whose NSTextView owns selection "
                "without an overlay"
            )

    markdown_source = sources.get(MARKDOWN_FILE)
    if markdown_source is not None and ".textSelection(.disabled)" not in markdown_source:
        failures.append(
            f"{MARKDOWN_FILE}: OmiMarkdown must explicitly disable inherited native text selection"
        )

    # The sanctioned remedy has to stay AppKit. An NSTextView owning its own
    # selection is the whole reason selection is allowed back into the
    # transcript; a SwiftUI Text here would reopen the failure class.
    selection_source = sources.get(SELECTION_FILE)
    if selection_source is not None and "NSTextView" not in selection_source:
        failures.append(
            f"{SELECTION_FILE}: transcript selection must be hosted by an NSTextView"
        )

    return failures


def load_sources(root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    protected = LIVE_TRANSCRIPT_FILES + CONVERSATION_DETAIL_FILES
    for relative in protected:
        path = root / relative
        if path.is_file():
            sources[relative] = path.read_text(encoding="utf-8")
    swift_root = root / DESKTOP_SWIFT_ROOT
    for path in sorted(swift_root.rglob("*.swift")):
        relative = path.relative_to(root).as_posix()
        if relative in sources:
            continue
        if any(part in DESKTOP_SWIFT_EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            sources[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return sources


def main() -> int:
    failures = check_sources(load_sources(ROOT))
    if failures:
        print("FC-selection-overlay-layout-loop boundary failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("FC-selection-overlay-layout-loop boundary passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
