#!/usr/bin/env python3
"""Ratchet on `DispatchQueue.*.asyncAfter` calls in the floating-bar / PTT sources.

BL-005 / S-14b: the floating control bar and push-to-talk manager coordinate UI
and capture state through a large number of fixed-delay `asyncAfter(...)` calls.
Fixed delays are fragile — they race the very transitions they try to sequence
(a window that hasn't opened yet, a view that hasn't mounted, an animation still
running), so they surface as intermittent "sometimes the field isn't focused" /
"the switcher didn't reopen" bugs. Where a real signal exists (a window becoming
key, a view lifecycle event, a state change) the transition should key off that
signal instead.

That migration is incremental and some `asyncAfter` uses are legitimate
(cancellable watchdogs, reconnect backoffs, deliberate gesture/debounce windows),
so this is an anti-regression ratchet, not a full sweep: it counts the
`.asyncAfter(` call sites under the scanned root and FAILS if that count rises
above the pinned baseline. The baseline may only shrink — every new timing-based
transition must justify itself, and every conversion to a signal lowers the
ceiling.

What counts: an occurrence of `.asyncAfter(` in a `.swift` file under the scanned
root. The leading dot + open paren deliberately excludes prose mentions of the
word `asyncAfter` (e.g. in doc comments).

Wiring (see also `scripts/pre-push` and `.github/workflows/repo-checks.yml`):
  - Pre-push: run automatically for pushes that touch the floating-bar sources.
  - CI: a gated step in the Repo Checks workflow.
  - Manually:  python3 desktop/macos/scripts/check-async-after-ratchet.py
  - Show the count / offenders:  ... --print

Lowering the baseline: after converting call sites to signal-driven transitions,
run with --print, then set BASELINE to the new (lower) number in the same commit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Pinned baseline — the number of `.asyncAfter(` call sites remaining in the
# scanned sources. MAY ONLY DECREASE. Raising it is a regression and must not be
# done to make the gate pass; key the new transition off a real signal (a window
# becoming key, a view lifecycle event, a state change) instead.
BASELINE = 23

# Scanned root, relative to the repo root. Covers the floating control bar and the
# push-to-talk manager (which lives under FloatingControlBar/).
SCAN_ROOT = "desktop/macos/Desktop/Sources/FloatingControlBar"

# `.asyncAfter(` call site. The leading dot + open paren excludes prose mentions
# of the word in comments (e.g. a backtick-quoted `asyncAfter`).
ASYNC_AFTER_RE = re.compile(r"\.asyncAfter\(")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root (default: inferred from this script's location).",
    )
    parser.add_argument(
        "--print",
        dest="print_offenders",
        action="store_true",
        help="Print the current count and every offending file:line, then exit 0.",
    )
    return parser.parse_args()


def repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # scripts/ -> desktop/macos -> desktop -> repo root
    return Path(__file__).resolve().parents[3]


def scan(root: Path) -> list[tuple[str, int, str]]:
    """Return (relative_path, line_number, line_text) for each asyncAfter call."""
    sources = root / SCAN_ROOT
    if not sources.is_dir():
        # Fail loud: a missing scan root (renamed/moved/wrong path) would make
        # rglob return zero matches, drop the count below baseline, and pass —
        # silently disabling the ratchet. Refuse to run instead.
        raise SystemExit(
            f"FAIL: scan root not found: {sources}. Fix SCAN_ROOT in "
            "check-async-after-ratchet.py or the repository layout."
        )
    offenders: list[tuple[str, int, str]] = []
    for path in sorted(sources.rglob("*.swift")):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for _ in ASYNC_AFTER_RE.finditer(line):
                offenders.append((relative, lineno, line.strip()))
    return offenders


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    offenders = scan(root)
    count = len(offenders)

    if args.print_offenders:
        for relative, lineno, line in offenders:
            print(f"{relative}:{lineno}: {line}")
        print(f"\n.asyncAfter( call sites: {count} (baseline {BASELINE})")
        return 0

    if count > BASELINE:
        print(
            f"FAIL: .asyncAfter( call sites rose to {count} (baseline {BASELINE}).",
            file=sys.stderr,
        )
        print(
            "Key the new transition off a real signal (window didBecomeKey, a "
            "view lifecycle event, a state change / onChange) instead of a fixed "
            "delay. If a delay is genuinely required (cancellable watchdog, "
            "reconnect backoff, gesture/debounce window), discuss it in review.",
            file=sys.stderr,
        )
        print(
            "See offenders with: python3 desktop/macos/scripts/check-async-after-ratchet.py --print",
            file=sys.stderr,
        )
        return 1

    if count < BASELINE:
        print(
            f"NOTE: .asyncAfter( call sites dropped to {count} (baseline "
            f"{BASELINE}). Lower BASELINE to {count} in "
            "check-async-after-ratchet.py to ratchet the gain."
        )
        return 0

    print(f"OK: .asyncAfter( call sites at baseline ({count}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
