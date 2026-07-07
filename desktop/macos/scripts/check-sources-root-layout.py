#!/usr/bin/env python3
"""Ratchet on loose Swift files directly under Desktop/Sources/.

Issue #8848: the desktop app had ~100+ `.swift` files sitting in the
`Sources/` root instead of feature directories. New code should land in a
feature folder (e.g. `Onboarding/`, `MainWindow/`) so module boundaries stay
obvious and future SPM carve-outs stay mechanical.

This gate counts `*.swift` files at `desktop/macos/Desktop/Sources/*.swift`
(max depth 1) and FAILS if that count rises above the pinned baseline. The
baseline may only shrink — after organizing files into directories, lower
BASELINE in the same commit.

Wiring (see also `.github/workflows/lint.yml`):
  - CI: gated step in the Lint workflow when desktop Swift sources change.
  - Manually: python3 desktop/macos/scripts/check-sources-root-layout.py
  - Show offenders: ... --print
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Pinned baseline — loose root-level Swift files. MAY ONLY DECREASE.
BASELINE = 77

SOURCES_ROOT = "desktop/macos/Desktop/Sources"


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
        help="Print the current count and every offending path, then exit 0.",
    )
    return parser.parse_args()


def repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[3]


def scan(root: Path) -> list[str]:
    sources = root / SOURCES_ROOT
    return sorted(
        path.relative_to(root).as_posix()
        for path in sources.glob("*.swift")
        if path.is_file()
    )


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    offenders = scan(root)
    count = len(offenders)

    if args.print_offenders:
        for relative in offenders:
            print(relative)
        print(f"\nloose Sources-root Swift files: {count} (baseline {BASELINE})")
        return 0

    if count > BASELINE:
        print(
            f"FAIL: loose Sources-root Swift files rose to {count} (baseline {BASELINE}).",
            file=sys.stderr,
        )
        print(
            "Place new desktop Swift sources in a feature directory under "
            f"{SOURCES_ROOT}/ instead of the root. See desktop/macos/AGENTS.md.",
            file=sys.stderr,
        )
        print(
            "Offenders: python3 desktop/macos/scripts/check-sources-root-layout.py --print",
            file=sys.stderr,
        )
        return 1

    if count < BASELINE:
        print(
            f"NOTE: loose Sources-root Swift files dropped to {count} "
            f"(baseline {BASELINE}). Lower BASELINE to {count} in "
            "check-sources-root-layout.py to ratchet the gain."
        )
        return 0

    print(f"OK: loose Sources-root Swift files at baseline ({count}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
