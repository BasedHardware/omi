#!/usr/bin/env python3
"""INV-UI-2: no-increase ratchet on hand-rolled UX in the macOS desktop app.

The desktop app shipped ~11 different back buttons, 6 close buttons, 9 date formats, 4 delete
policies and about 50 hand-built primary buttons, because every page drew its own. The shared
components now exist (see `desktop/macos/docs/ux-contract.md`); this guard keeps new code on them.

For every changed Swift file under `desktop/macos/Desktop/Sources/`, it counts each rule's pattern in
the file at HEAD and at the merge base. A count that rises fails. Existing debt may stay; a file may
not grow more of it, and a new file starts at zero.

Deliberate exceptions carry a marker on the same line, which the guard does not count:

    // omi-ux-allow: <rule-id> -- <why the shared component cannot express this>

Comments are otherwise stripped before counting, so prose that names a banned pattern is not a
violation. String literals are kept, because the ellipsis rule is about copy.

Exit codes: 0 clean, 1 regression found, 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SOURCES_ROOT = "desktop/macos/Desktop/Sources/"
ALLOW_MARKER = "omi-ux-allow:"


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    remedy: str
    # Files that *are* the shared component for this rule, so they may spell the primitive.
    owners: tuple[str, ...] = ()
    # Match across line breaks (a modifier chain spans lines). The allow marker may sit on any line
    # of the match.
    multiline: bool = False


def _owners(*names: str) -> tuple[str, ...]:
    return tuple(SOURCES_ROOT + n for n in names)


THEME_DIR = SOURCES_ROOT + "Theme/"

RULES: tuple[Rule, ...] = (
    Rule(
        "hand-rolled-back",
        re.compile(r'Image\(systemName:\s*"chevron\.(?:left|up)"\)'),
        'Use `BackChip("<Destination>")` on the leading edge for any drill-in. A bare chevron is '
        "only a back control for people who already know it is one.",
        _owners("MainWindow/Components/NavigationControls.swift"),
    ),
    Rule(
        "hand-rolled-close",
        re.compile(r'Image\(systemName:\s*"xmark(?:\.circle(?:\.fill)?)?"\)'),
        "Use `DismissButton` (trailing edge, Esc, labeled) for anything that floats over the page.",
        _owners("MainWindow/Components/NavigationControls.swift"),
    ),
    Rule(
        "system-alert",
        re.compile(r"\.alert\("),
        "Use `.shellConfirmation(...)` for a confirmation (the system alert dims the whole transparent "
        "window onto the wallpaper — see ShellConfirmationDialog.swift), or `dismissableSheet` when "
        "the prompt needs a text field.",
    ),
    Rule(
        "raw-pasteboard",
        re.compile(r"NSPasteboard\.general\.setString\("),
        "Use `CopyButton` for a copy control, or `OmiToastCenter.shared.copy(_:confirming:)` from a menu "
        "item, so every copy confirms and none copies an empty string.",
        _owners("MainWindow/Components/OmiIconButton.swift"),
    ),
    Rule(
        "raw-cursor-push",
        re.compile(r"NSCursor\.pointingHand\.push\(\)"),
        "Use `.pointingHandOnHover()`. A push paired only with `onHover(false)` leaks the hand over the "
        "whole app when the hovered view leaves the hierarchy.",
        _owners("MainWindow/Components/PointingHandOnHover.swift"),
    ),
    Rule(
        "date-format-string",
        re.compile(r'\.dateFormat\s*=\s*"'),
        "Use a style from `OmiDateFormat` (time, dayHeader, timestamp, range, relative, offset, "
        "duration). Fixed format strings ignore the user's locale and 24-hour clock.",
        _owners("MainWindow/Components/OmiDateFormat.swift"),
    ),
    Rule(
        "raw-system-font",
        re.compile(r"\.font\(\.system\(size:"),
        "Use `.scaledFont(size: OmiType.<rung>)` — `.system(size:)` skips Omi's typeface and the "
        "user's text-size setting.",
        (THEME_DIR,),
    ),
    Rule(
        "literal-font-size",
        re.compile(r"scaledFont\(size:\s*\d"),
        "Use an `OmiType` rung (micro 10, caption 11, body 13, subheading 15, heading 20, title 28, "
        "display 40) instead of a literal size.",
        (THEME_DIR,),
    ),
    Rule(
        "literal-corner-radius",
        re.compile(r"(?:cornerRadius:\s*|RoundedRectangle\(cornerRadius:\s*)\d"),
        "Use an `OmiChrome` radius (card / control / chip) or a `PageGlass` radius.",
        (THEME_DIR,),
    ),
    Rule(
        "scaled-progress-view",
        # `ProgressView(…)` followed, through any chain of simple modifiers, by `.scaleEffect(`.
        re.compile(
            r"ProgressView\([^()\n]*\)"
            # Each argument list is a run of non-paren characters or one nested `(…)`; the two alternatives
            # never overlap, so the match has one parse and cannot backtrack exponentially (CodeQL py/redos).
            r"(?:\s*\.(?:progressViewStyle|tint|controlSize|frame|padding)\((?:[^()\n]|\([^()\n]*\))*\))*"
            r"\s*\.scaleEffect\("
        ),
        "Use `GlassLoadingState(label:)` for a page state, or `ProgressView().controlSize(.small)` for an "
        "inline spinner. `.scaleEffect` blurs the spinner and leaves its layout frame at the unscaled size.",
        multiline=True,
    ),
    Rule(
        "hand-rolled-more-menu",
        re.compile(r'PageQueryActionLabel\(\s*icon:\s*"ellipsis"'),
        "Use `PageMoreMenu(help:accessibilityIdentifier:)` for a page's More menu. A hand-built `Menu` "
        "label inherits the accent tint and renders a blue \"More\".",
        _owners("MainWindow/Components/PageQueryToolbar.swift"),
    ),
    Rule(
        "ascii-ellipsis",
        re.compile(
            r'(?:\b(?:Text|Button|Label|TextField|SecureField|Toggle|Menu|help|navigationTitle)\(\s*|'
            r'\b(?:title|placeholder|label|message|confirmTitle):\s*)"[^"\n]*\.\.\."'
        ),
        'Use the ellipsis character "…" in user-visible copy, and only when more input follows.',
    ),
)

RULE_BY_ID = {rule.id: rule for rule in RULES}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip_comments(text: str) -> str:
    """Blank comments while keeping line structure and string literals.

    A `//` inside a string literal (a URL) is preserved by only treating `//` that is not inside an
    open double quote as a comment start.
    """
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out_lines = []
    for line in text.splitlines():
        in_string = False
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "\\" and in_string:
                i += 2
                continue
            if ch == '"':
                in_string = not in_string
            elif not in_string and line.startswith("//", i):
                cut = i
                break
            i += 1
        out_lines.append(line if cut is None else line[:cut])
    return "\n".join(out_lines)


def is_owner(rule: Rule, path: str) -> bool:
    return any(path == owner or (owner.endswith("/") and path.startswith(owner)) for owner in rule.owners)


def count(rule: Rule, text: str) -> int:
    total = 0
    raw_lines = text.splitlines()
    stripped = strip_comments(text)
    if rule.multiline:
        allow = re.compile(rf"{ALLOW_MARKER}\s*{re.escape(rule.id)}\b")
        for match in rule.pattern.finditer(stripped):
            first = stripped.count("\n", 0, match.start())
            last = first + match.group(0).count("\n")
            if not any(allow.search(line) for line in raw_lines[first : last + 1]):
                total += 1
        return total
    stripped_lines = stripped.splitlines()
    for raw, stripped in zip(raw_lines, stripped_lines):
        if ALLOW_MARKER in raw and re.search(rf"{ALLOW_MARKER}\s*{re.escape(rule.id)}\b", raw):
            continue
        total += len(rule.pattern.findall(stripped))
    return total


def git_show(root: Path, ref: str, path: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "show", f"{ref}:{path}"], text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return None


def is_ux_source(path: str) -> bool:
    return path.startswith(SOURCES_ROOT) and path.endswith(".swift") and "/Generated/" not in path


def check(root: Path, base: str, paths: list[str]) -> list[str]:
    regressions: list[str] = []
    for path in paths:
        head_file = root / path
        if not head_file.is_file():
            continue
        head_text = head_file.read_text(encoding="utf-8", errors="ignore")
        base_text = git_show(root, base, path) or ""
        for rule in RULES:
            if is_owner(rule, path):
                continue
            before, after = count(rule, base_text), count(rule, head_text)
            if after > before:
                regressions.append(f"{path}: [{rule.id}] {before} → {after}\n      {rule.remedy}")
    return regressions


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--changed-files", required=True, help="File listing changed paths, one per line.")
    parser.add_argument("--base", required=True, help="Git ref for the merge base.")
    parser.add_argument("--root", default=".", help="Repository root.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    changed_list = Path(args.changed_files)
    if not changed_list.is_file():
        print(f"usage error: {changed_list} does not exist", file=sys.stderr)
        return 2
    paths = [
        line.strip()
        for line in changed_list.read_text(encoding="utf-8").splitlines()
        if line.strip() and is_ux_source(line.strip())
    ]
    if not paths:
        print("OK: INV-UI-2 — no desktop Swift sources changed.")
        return 0

    regressions = check(root, args.base, paths)
    if regressions:
        print("FAIL: INV-UI-2 — hand-rolled UX increased in changed desktop files.")
        print("Use the shared components in desktop/macos/docs/ux-contract.md, or mark a deliberate")
        print(f"exception on the line: // {ALLOW_MARKER} <rule-id> -- <reason>")
        for line in regressions:
            print(f"  - {line}")
        return 1

    print(f"OK: INV-UI-2 — no hand-rolled UX increase across {len(paths)} changed desktop file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
