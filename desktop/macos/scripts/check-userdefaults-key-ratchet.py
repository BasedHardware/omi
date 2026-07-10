#!/usr/bin/env python3
"""Ratchet on raw inline UserDefaults string keys in the desktop Swift app.

BL-004 / S-13: `UserDefaults` keys were raw inline string literals scattered
across the app (`"auth_userId"` alone appeared inline ~18 times). A typo in one
silently reads `nil` with no error, breaking auth/onboarding state restore
invisibly. The durable fix is to route keys through the compile-checked
`DefaultsKey` enum (see `Desktop/Sources/DefaultsKey.swift`).

That migration is incremental, so this is an anti-regression ratchet, not a
full sweep: it counts the raw inline `forKey: "literal"` occurrences that remain
in production Swift sources and FAILS if that count rises above the pinned
baseline. The baseline may only shrink — every new UserDefaults key must go
through `DefaultsKey`, and every migrated call site lowers the ceiling.

What counts as a raw inline key: an occurrence of `forKey:` immediately followed
by a double-quoted string literal, in a `.swift` file under the scanned Sources
root, EXCLUDING:
  - `DefaultsKey.swift` (the allowlisted single source of truth), and
  - non-UserDefaults `forKey:` forms — Dictionary `removeValue(forKey:)` and KVC
    `setValue(_:forKey:)` — which are not defaults keys.

Wiring (see also `scripts/pre-push` and `.github/workflows/repo-checks.yml`):
  - Pre-push: run automatically for pushes that touch desktop Swift sources.
  - CI: a gated step in the Repo Checks workflow.
  - Manually:  python3 desktop/macos/scripts/check-userdefaults-key-ratchet.py
  - Show the count / offenders:  ... --print

Lowering the baseline: after migrating call sites, run with --print, then set
BASELINE to the new (lower) number in the same commit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Pinned baseline — the number of raw inline UserDefaults string keys remaining
# in the scanned sources. MAY ONLY DECREASE. Raising it is a regression and must
# not be done to make the gate pass; migrate the call site to `DefaultsKey`
# instead.
BASELINE = 183

# Sources root, relative to the repo root.
SOURCES_ROOT = "desktop/macos/Desktop/Sources"

# Files whose inline `forKey: "..."` occurrences are exempt (the typed-key
# definitions themselves may legitimately spell key strings).
ALLOWLISTED_FILES = {
    "desktop/macos/Desktop/Sources/DefaultsKey.swift",
}

# `forKey:` immediately followed by a double-quoted string literal.
FORKEY_LITERAL_RE = re.compile(r'forKey:\s*"[^"]*"')

# Non-UserDefaults `forKey:` forms to skip (Dictionary.removeValue, KVC setValue).
NON_USERDEFAULTS_RE = re.compile(r'removeValue\(forKey:|\.setValue\(')


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
    """Return (relative_path, line_number, line_text) for each raw inline key."""
    sources = root / SOURCES_ROOT
    offenders: list[tuple[str, int, str]] = []
    for path in sorted(sources.rglob("*.swift")):
        relative = path.relative_to(root).as_posix()
        if relative in ALLOWLISTED_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if NON_USERDEFAULTS_RE.search(line):
                continue
            for _ in FORKEY_LITERAL_RE.finditer(line):
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
        print(f"\nraw inline UserDefaults keys: {count} (baseline {BASELINE})")
        return 0

    if count > BASELINE:
        print(
            f"FAIL: raw inline UserDefaults string keys rose to {count} " f"(baseline {BASELINE}).",
            file=sys.stderr,
        )
        print(
            "Route new keys through DefaultsKey (desktop/macos/Desktop/Sources/"
            "DefaultsKey.swift) and read/write via the typed UserDefaults "
            "accessors instead of an inline forKey: \"...\" literal.",
            file=sys.stderr,
        )
        print(
            "See offenders with: python3 desktop/macos/scripts/" "check-userdefaults-key-ratchet.py --print",
            file=sys.stderr,
        )
        return 1

    if count < BASELINE:
        print(
            f"NOTE: raw inline UserDefaults keys dropped to {count} "
            f"(baseline {BASELINE}). Lower BASELINE to {count} in "
            "check-userdefaults-key-ratchet.py to ratchet the gain."
        )
        return 0

    print(f"OK: raw inline UserDefaults keys at baseline ({count}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
