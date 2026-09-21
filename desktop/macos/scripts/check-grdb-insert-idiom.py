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

Two properties keep that rule honest without a Swift type checker:

  * Comments and string literals are blanked before matching, so
    `// never call record.insert(db)` and `let hint = "record.insert(db)"` are
    not reported. See `mask_comments_and_strings`.
  * A match must be a `try` expression. Every GRDB insert overload throws, so a
    real call always carries `try`; `Set.insert`/`Array.insert` do not throw, so
    `values.insert(db)` on a `Set<Int>` cannot be mistaken for one. This costs no
    false negatives, because an untried `record.insert(db)` does not compile.

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

# Two signals identify a GRDB persistence call without resolving the receiver's type:
#
# 1. The argument is a database handle. `db`/`database` name a GRDB
#    `Database`/`DatabaseQueue`/`DatabasePool` everywhere in Desktop/Sources; Set and
#    Array inserts pass ids, keys and elements (`.insert(task.id)`, `.insert(task, at: 0)`).
# 2. The call is a `try` expression. Every GRDB insert overload throws, so real calls
#    always carry `try`, while `Set.insert`/`Array.insert` do not throw and so cannot.
#
# Together these keep `values.insert(db)` on a `Set<Int>` out of the report without
# needing a Swift type checker, and they cannot hide a real insert: an untried
# `record.insert(db)` does not compile.
DB_HANDLE_NAMES = ("db", "database")
DIRECT_INSERT = re.compile(
    r"\btry\b[!?]?\s*(?:await\s+)?"
    r"[A-Za-z_][A-Za-z0-9_]*(?:[?!]?\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]\n]*\])*"
    r"\.insert\(\s*(?P<handle>" + "|".join(DB_HANDLE_NAMES) + r")\s*(?=[,)])"
)

REMEDY = (
    "use `inserted({handle})` instead: `record.insert({handle})` on a type conforming to "
    "PersistableRecord picks the non-mutating overload, whose `didInsert` is the empty "
    "default, so a `mutating didInsert` never runs and the rowid is dropped"
)


def mask_comments_and_strings(text: str) -> str:
    """Blank out Swift comments and string literals, preserving offsets and newlines.

    The checker matches source code, not prose: `// never call record.insert(db)` and
    `let hint = "record.insert(db)"` are not calls. Blanking rather than deleting keeps
    every byte offset and line number identical to the original file.

    Covers the Swift lexical forms that can contain the pattern: line comments, nested
    block comments, single-line strings with escapes, multiline `\"\"\"` strings, and raw
    strings with any number of `#` delimiters (where `\\` is not an escape).
    """
    out = list(text)
    length = len(text)
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, min(end, length)):
            if out[position] != "\n":
                out[position] = " "

    while index < length:
        char = text[index]

        if char == "/" and text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            blank(index, end)
            index = end
            continue

        if char == "/" and text.startswith("/*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth:
                if text.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif text.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            blank(index, cursor)
            index = cursor
            continue

        if char in '#"':
            hashes = 0
            cursor = index
            while cursor < length and text[cursor] == "#":
                hashes += 1
                cursor += 1
            if cursor >= length or text[cursor] != '"':
                # `#available`, `#selector`, a lone `#` — not a string literal.
                index = cursor + 1 if hashes else index + 1
                continue

            pound = "#" * hashes
            multiline = text.startswith('"""', cursor)
            terminator = ('"""' + pound) if multiline else ('"' + pound)
            cursor += 3 if multiline else 1

            while cursor < length:
                if hashes == 0 and text[cursor] == "\\":
                    cursor += 2
                    continue
                if hashes and text.startswith("\\" + pound, cursor):
                    cursor += 1 + hashes + 1
                    continue
                if text.startswith(terminator, cursor):
                    cursor += len(terminator)
                    break
                if not multiline and text[cursor] == "\n":
                    # Unterminated single-line string; do not swallow the rest of the file.
                    break
                cursor += 1

            blank(index, cursor)
            index = cursor
            continue

        index += 1

    return "".join(out)


def find_violations(sources_dir: Path) -> list[tuple[Path, int, str, str]]:
    """Return (path, line number, line text, handle) for every direct GRDB insert."""
    violations: list[tuple[Path, int, str, str]] = []
    for path in sorted(sources_dir.rglob("*.swift")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file is a real failure
            print(f"check-grdb-insert-idiom: cannot read {path}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        masked = mask_comments_and_strings(text)
        original_lines = text.splitlines()
        for match in DIRECT_INSERT.finditer(masked):
            # The call site is where `.insert(` sits, which may be a continuation line
            # below the `try` that opened the expression.
            insert_offset = masked.index(".insert(", match.start(), match.end())
            lineno = masked.count("\n", 0, insert_offset) + 1
            line = original_lines[lineno - 1].strip() if lineno <= len(original_lines) else ""
            violations.append((path, lineno, line, match.group("handle")))
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
    for path, lineno, line, handle in violations:
        try:
            display = path.relative_to(Path.cwd())
        except ValueError:
            display = path
        print(f"- {display}:{lineno}: {line}")
        print(f"  {REMEDY.format(handle=handle)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
