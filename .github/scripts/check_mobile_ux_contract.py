#!/usr/bin/env python3
"""INV-UI-3: no-increase ratchet on hand-rolled UI patterns in the Flutter app.

The mobile UX contract (app/docs/ux-contract.md) gives every recurring UI job one shared
primitive under app/lib/ui/: OmiBackButton, showOmiSheet, showOmiConfirm, OmiFeedback,
OmiClipboard, OmiDateFormat, OmiSpinner, tokens and l10n. Each rule below counts one way of
doing that job by hand. For every changed Dart file under app/lib/, no rule's count may rise
above the file's count at the merge base; a new file starts at zero. Existing debt may remain
and is expected to shrink as files are touched.

Escape hatch: end the offending line with
    // omi-ux-allow: <rule-id> -- <reason>
(several ids may be comma-separated). The reason is required; an allow without one is ignored.

Excluded: generated code (lib/gen/, lib/l10n/, *.g.dart, *.gen.dart, *.freezed.dart) and the
primitives themselves (lib/ui/), which are where the raw widgets are supposed to live.

Usage:
    check_mobile_ux_contract.py --changed-files FILE --base REF   # the ratchet (CI)
    check_mobile_ux_contract.py --report app/lib/pages/foo.dart   # counts for a file, no base
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = "app/lib/"
EXCLUDED_PREFIXES = ("app/lib/gen/", "app/lib/l10n/", "app/lib/ui/")
EXCLUDED_SUFFIXES = (".g.dart", ".gen.dart", ".freezed.dart", ".mocks.dart")

# A Dart string literal on one line: single- or double-quoted, escapes honoured. Scanning with
# finditer pairs quotes left to right, so `'a', ...list, 'b'` yields 'a' and 'b', never the
# spread operator between them.
STRING_LITERAL = re.compile(r"""'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*\"""")
INTERPOLATION = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_]\w*")
LETTER = re.compile(r"[^\W\d_]")
ALLOW = re.compile(r"//\s*omi-ux-allow:\s*([\w\-, ]+?)\s+--\s+\S")


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    fix: str
    # Extra test on the match (text, match) -> counts?
    accept: object = None


def _leading_context(text: str, match: re.Match[str]) -> bool:
    """`Icons.chevron_left` only counts as a back glyph when it sits in a `leading:` slot."""
    window = text[max(0, match.start() - 160) : match.start()]
    return "leading" in window


def _letter_bearing_literal(text: str, match: re.Match[str]) -> bool:
    literal = match.group("lit")
    body = INTERPOLATION.sub("", literal[1:-1])
    return bool(LETTER.search(body))


RULES: tuple[Rule, ...] = (
    Rule(
        "raw-back-glyph",
        re.compile(
            r"\bIcons\.arrow_back(?:_ios_new|_ios)?(?:_rounded|_outlined|_sharp)?\b"
            r"|\bFontAwesomeIcons\.(?:arrowLeft|chevronLeft)\b"
        ),
        "leading OmiBackButton() on a pushed page",
    ),
    Rule(
        "raw-back-glyph",
        re.compile(r"\bIcons\.chevron_left(?:_rounded)?\b"),
        "leading OmiBackButton() on a pushed page",
        accept=_leading_context,
    ),
    Rule("page-route-builder", re.compile(r"\bPageRouteBuilder\s*[(<]"), "routeToPage / omiPageRoute"),
    Rule("raw-bottom-sheet", re.compile(r"\bshowModalBottomSheet\s*[(<]"), "showOmiSheet / OmiSheetScaffold"),
    Rule(
        "raw-dialog",
        re.compile(r"(?<![\w.])(?:Cupertino)?AlertDialog(?:\.adaptive)?\s*\("),
        "showOmiConfirm / showOmiAlert",
    ),
    Rule("raw-snackbar", re.compile(r"(?<![\w.])SnackBar\s*\("), "OmiFeedback.confirm/info/error/undo"),
    Rule("raw-clipboard", re.compile(r"\bClipboard\.setData\s*\("), "OmiClipboard.copy"),
    Rule(
        "date-pattern",
        re.compile(r"\b(?:DateFormat|dateTimeFormat)\s*\(\s*r?['\"]"),
        "OmiDateFormat (locale and 24-hour aware)",
    ),
    Rule("color-literal", re.compile(r"\bColor\s*\(\s*0x"), "OmiColors token"),
    Rule("font-size-literal", re.compile(r"\bfontSize\s*:\s*\d"), "OmiType style"),
    Rule("radius-literal", re.compile(r"\bBorderRadius\.circular\s*\(\s*\d"), "OmiRadius token"),
    Rule("raw-spinner", re.compile(r"(?<![\w.])CircularProgressIndicator(?:\.adaptive)?\s*\("), "OmiSpinner"),
    Rule("three-dot-ellipsis", re.compile(r"\.\.\."), "the ellipsis character … (or drop it)"),
    Rule(
        "hardcoded-text",
        re.compile(
            r"(?<![\w.])Text\s*\(\s*(?P<lit>r?'(?:[^'\\\n]|\\.)*'|r?\"(?:[^\"\\\n]|\\.)*\")",
        ),
        "context.l10n.<key> (scripts/l10n.py add)",
        accept=_letter_bearing_literal,
    ),
)

RULE_IDS: tuple[str, ...] = tuple(dict.fromkeys(rule.id for rule in RULES))


def is_contract_source(path: str) -> bool:
    if not path.startswith(APP_ROOT) or not path.endswith(".dart"):
        return False
    if path.startswith(EXCLUDED_PREFIXES) or path.endswith(EXCLUDED_SUFFIXES):
        return False
    return True


def _line_bounds(text: str, index: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return start, len(text) if end == -1 else end


def _in_comment(line: str, column: int) -> bool:
    stripped = line.lstrip()
    if stripped.startswith(("//", "*", "/*")):
        return True
    # A `//` before the match, outside any string literal, makes the rest of the line a comment.
    masked = STRING_LITERAL.sub(lambda m: " " * len(m.group(0)), line)
    comment = masked.find("//")
    return comment != -1 and comment < column


def _in_string(line: str, column: int) -> bool:
    return any(m.start() < column < m.end() - 1 for m in STRING_LITERAL.finditer(line))


def _allowed(line: str, rule_id: str) -> bool:
    match = ALLOW.search(line)
    if not match:
        return False
    return rule_id in {part.strip() for part in match.group(1).split(",")}


def find_hits(text: str) -> dict[str, list[int]]:
    """Map rule id -> 1-based line numbers of every counted hit in [text]."""
    hits: dict[str, list[int]] = {rule_id: [] for rule_id in RULE_IDS}
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            start, end = _line_bounds(text, match.start())
            line = text[start:end]
            column = match.start() - start
            if _in_comment(line, column):
                continue
            if rule.id == "three-dot-ellipsis":
                # Only an ellipsis a reader sees: inside a string literal, not the spread operator.
                if not _in_string(line, column):
                    continue
            elif rule.id != "hardcoded-text" and _in_string(line, column):
                continue
            if rule.accept is not None and not rule.accept(text, match):  # type: ignore[operator]
                continue
            if _allowed(line, rule.id):
                continue
            hits[rule.id].append(text.count("\n", 0, match.start()) + 1)
    return hits


def count_hits(text: str) -> dict[str, int]:
    return {rule_id: len(lines) for rule_id, lines in find_hits(text).items()}


def git_show(ref: str, path: str, root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return None


def fix_for(rule_id: str) -> str:
    return next(rule.fix for rule in RULES if rule.id == rule_id)


def compare(path: str, head_text: str, base_text: str | None) -> list[str]:
    """Regression lines for one file (empty when no rule's count rose)."""
    head_hits = find_hits(head_text)
    base_counts = count_hits(base_text) if base_text is not None else {rule_id: 0 for rule_id in RULE_IDS}
    regressions: list[str] = []
    for rule_id in RULE_IDS:
        head_count = len(head_hits[rule_id])
        if head_count > base_counts[rule_id]:
            lines = ", ".join(str(n) for n in head_hits[rule_id][:8])
            more = "…" if head_count > 8 else ""
            regressions.append(
                f"{path}: {rule_id} {base_counts[rule_id]} → {head_count} (lines {lines}{more}); use {fix_for(rule_id)}"
            )
    return regressions


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--changed-files", help="File listing changed paths (one per line).")
    parser.add_argument("--base", default=None, help="Git ref for the merge-base content.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--report", nargs="*", metavar="PATH", help="Print per-rule counts for these files and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()

    if args.report is not None:
        for path in args.report:
            text = (root / path).read_text(encoding="utf-8", errors="ignore")
            counts = {k: v for k, v in count_hits(text).items() if v}
            print(f"{path}: {counts or 'clean'}")
        return 0

    if not args.changed_files:
        print("FAIL: --changed-files is required (or use --report).")
        return 1
    changed = [
        line.strip()
        for line in Path(args.changed_files).read_text(encoding="utf-8").splitlines()
        if line.strip() and is_contract_source(line.strip())
    ]
    if not changed:
        print("OK: no app/lib Dart sources in changed files for INV-UI-3.")
        return 0
    if not args.base:
        print("FAIL: --base is required for the mobile UX contract ratchet.")
        return 1

    regressions: list[str] = []
    for path in changed:
        head_file = root / path
        if not head_file.is_file():
            continue
        head_text = head_file.read_text(encoding="utf-8", errors="ignore")
        regressions.extend(compare(path, head_text, git_show(args.base, path, root)))

    if regressions:
        print("FAIL: INV-UI-3 — hand-rolled UI patterns increased in changed files.")
        print("Use the shared primitive (app/docs/ux-contract.md), or end the line with")
        print("`// omi-ux-allow: <rule> -- <reason>`. See product/invariants/mobile-ux-contract.md")
        for line in regressions:
            print(f"  - {line}")
        return 1

    print(f"OK: INV-UI-3 — no hand-rolled UI increase across {len(changed)} changed app/lib file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
