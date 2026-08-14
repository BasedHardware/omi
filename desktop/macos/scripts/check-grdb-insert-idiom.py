#!/usr/bin/env python3
"""Keep desktop GRDB inserts on the one idiom that always runs `didInsert`.

This is a **static checker**, not behavioral coverage. It exists because the
hazard it guards is invisible at runtime: a record whose rowid is captured by a
`mutating func didInsert` silently never captures it when inserted through
`PersistableRecord`'s non-mutating `insert(_:)`, and the field is optional by
design, so the value is simply always nil and every dependent path quietly does
nothing. No error, no warning, no crash.

Mechanism, measured against the pinned GRDB (Desktop/Package.resolved):

  PersistableRecord+Insert.swift:34   `extension PersistableRecord { func insert(...) }`
                                      non-mutating; its `didInsert` resolves to
                                      the empty default at :10 -> rowid dropped.
  MutablePersistableRecord+Insert.swift:79
                                      `inserted(_:)` does `var result = self;
                                      try result.insert(db)` inside an
                                      `extension MutablePersistableRecord`, so it
                                      binds the *mutating* insert and the record's
                                      own `mutating didInsert` is the witness.

The precise hazard is "a direct `record.insert(db)` on a concrete type whose
`didInsert` is mutating", which needs receiver-type resolution a source scrape
cannot do soundly. Flagging the *declaration* shape instead (PersistableRecord +
mutating didInsert) would flag 14 types that are not affected, because they all
insert via `inserted(db)`.

So this checker enforces the cheap, sound rule instead: the codebase uses exactly
one insert idiom, `inserted(db)`. The direct form buys nothing here, every
production seam already uses `inserted(db)`, and any new direct `.insert(db)` is
rejected regardless of the receiver's conformance.

Real instances this would have caught, both fixed before this checker landed:
  * `Screenshot` in RewindDatabase.insertScreenshot (#11208) - RewindIndexer
    never queued a captured frame for embedding, because every consumer was
    written `if let id = inserted.id`.
  * `AIUserProfileRecord` in AIUserProfileService - Settings -> Advanced -> AI
    User Profile stored `aiProfileId = nil` after Regenerate, so Save and Delete
    both silently no-opped.

Scope is production sources only. Tests may construct the broken shape
deliberately to prove it is broken.

Exit codes: 0 clean, 1 violations found, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = SCRIPT_DIR.parent
DEFAULT_SOURCES_DIR = DESKTOP_DIR / "Desktop" / "Sources"

# A GRDB persistence call is identified by its database-handle argument. Set and
# Array inserts in this codebase pass ids, keys and elements (`.insert(task.id)`,
# `.insert(task, at: 0)`), never a bare `db`/`database`, so this cannot collide
# with them.
DB_HANDLE_NAMES = ("db", "database")
DIRECT_INSERT = re.compile(
    r"\.insert\(\s*(?P<handle>" + "|".join(DB_HANDLE_NAMES) + r")\s*(?=[,)])"
)

REMEDY = (
    "use `inserted({handle})` instead: `record.insert({handle})` on a type conforming to "
    "PersistableRecord picks the non-mutating overload, whose `didInsert` is the empty "
    "default, so a `mutating didInsert` never runs and the rowid is dropped"
)


def find_violations(sources_dir: Path) -> list[tuple[Path, int, str]]:
    """Return (path, line number, line text) for every direct GRDB insert."""
    violations: list[tuple[Path, int, str]] = []
    for path in sorted(sources_dir.rglob("*.swift")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file is a real failure
            print(f"check-grdb-insert-idiom: cannot read {path}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DIRECT_INSERT.search(line):
                violations.append((path, lineno, line.strip()))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=DEFAULT_SOURCES_DIR,
        help="root of the Swift sources to scan (default: desktop/macos/Desktop/Sources)",
    )
    args = parser.parse_args(argv)

    sources_dir: Path = args.sources_dir
    if not sources_dir.is_dir():
        print(
            f"check-grdb-insert-idiom: sources dir not found: {sources_dir}",
            file=sys.stderr,
        )
        return 2

    violations = find_violations(sources_dir)
    if not violations:
        print("ok: desktop GRDB inserts all use the inserted(db) idiom")
        return 0

    print("FAIL: direct GRDB insert(db) found; the rowid-capturing idiom is inserted(db)")
    for path, lineno, line in violations:
        try:
            display = path.relative_to(Path.cwd())
        except ValueError:
            display = path
        handle_match = DIRECT_INSERT.search(line)
        handle = handle_match.group("handle") if handle_match else "db"
        print(f"- {display}:{lineno}: {line}")
        print(f"  {REMEDY.format(handle=handle)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
