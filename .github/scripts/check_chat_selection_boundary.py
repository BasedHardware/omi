#!/usr/bin/env python3
"""Static boundary for FC-selection-overlay-layout-loop.

Omi Beta 0.12.146 reopened the failure class from PRs #9267 and #10471 when
PR #10834 added native SwiftUI selection back to settled chat messages. The
running app then spent every sampled main-thread stack in SelectionOverlay,
setFont, intrinsic-size invalidation, and AttributeGraph while memory grew
without bound.

SwiftUI has no type-level API that prevents an ancestor or message renderer
from installing SelectionOverlay. This deliberately narrow source tripwire
therefore protects the three authoritative live-transcript files. Behavioral
resize coverage remains in ChatTimelineContinuityTests.
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
)
MARKDOWN_FILE = LIVE_TRANSCRIPT_FILES[2]

FORBIDDEN_PATTERNS = {
    ".textSelection(.enabled)": (
        "live chat must not install SwiftUI SelectionOverlay; use the existing copy actions "
        "or a separate non-live reading surface"
    ),
    "textSelectionEnabled": (
        "OmiMarkdown must not expose a native-selection escape hatch"
    ),
}


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

    markdown_source = sources.get(MARKDOWN_FILE)
    if markdown_source is not None and ".textSelection(.disabled)" not in markdown_source:
        failures.append(
            f"{MARKDOWN_FILE}: OmiMarkdown must explicitly disable inherited native text selection"
        )

    return failures


def load_sources(root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in LIVE_TRANSCRIPT_FILES:
        path = root / relative
        if path.is_file():
            sources[relative] = path.read_text(encoding="utf-8")
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
