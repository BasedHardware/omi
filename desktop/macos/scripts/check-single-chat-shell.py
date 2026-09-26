#!/usr/bin/env python3
"""Keep the desktop main window on exactly one chat shell, with no inert blocks.

The app used to mount one of two shells behind a server sample and a local
preference, and six of the journal's content-block kinds rendered as controls on
one of them and as nothing at all on the other. Both halves of that are gone
(#12598), and both are the kind of thing that grows back one symbol at a time —
a "just for now" preference, an `Optional` context, one `== nil` fork — without
any single diff looking like a second shell.

This is a **static tripwire**, not behavioral coverage. `OneChatShellRichBlockTests`
proves what the blocks actually do; this only proves the vocabulary that made a
second shell expressible has not come back.

Every banned symbol below is checked against production sources only
(`Desktop/Sources`). Tests may name a symbol in a string to assert its absence.
Comments and string literals are blanked before matching, so prose that names a
deleted type — including this file's own remedies quoted in a Swift comment — is
not a violation.

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

# (pattern, why it is banned and what to do instead, scan strings too)
#
# `scan_strings` is on for the two `@AppStorage` keys, whose only spelling in
# production *is* a string literal — masking strings would make them unfindable.
# Everything else is a Swift identifier, so a string that mentions it is prose or
# a test fixture, not a use.
BANNED: list[tuple[str, str, bool]] = [
    (
        r"\bChatFirstShellCapabilitySample\b",
        "the capability sample no longer selects a shell; use ChatFirstCapabilitySample, "
        "which only gates kernel features",
        False,
    ),
    (
        r"\bChatFirstShellVariant\b",
        "there is one shell, so there is no variant to resolve; the automation snapshot pins "
        "DesktopAutomationSnapshot.singleShellVariant",
        False,
    ),
    (
        r"\buseLegacyHomeDesign\b",
        "the legacy Home shell and its preference are deleted; every account gets ChatFirstShell",
        True,
    ),
    (
        r"\buseOldestHomeDesign\b",
        "the widgets-and-chat Home is deleted; every account gets ChatFirstShell",
        True,
    ),
    (
        r"\busesLegacyPresentation\b",
        "QueryShellHome has one presentation; the DashboardPage fork is deleted",
        False,
    ),
    (
        r"\brichBlockRenderingEnabled\b",
        "every Chat surface renders every content block; the flag that made six of them "
        "EmptyView on some surfaces is deleted",
        False,
    ),
    (
        r"chatFirstRichBlockContext\s*==\s*nil",
        "the content-block context is non-optional on every host; a nil fork means a surface "
        "that silently drops cards",
        False,
    ),
    (
        r"chatFirstRichBlockContext\s*!=\s*nil",
        "the content-block context is non-optional on every host; a nil fork means a surface "
        "that silently drops cards",
        False,
    ),
    (
        r"chatFirstRichBlockContext:\s*ChatFirstRichBlockContext\?",
        "declare it as a non-optional `ChatFirstRichBlockContext`; auxiliary surfaces build one "
        "with `ChatFirstRichBlockContext.auxiliary(chatProvider:)`",
        False,
    ),
    (
        r"\bDashboardPage\s*\(",
        "DashboardPage and its inline chat are deleted; the one chat destination is QueryShellHome",
        False,
    ),
]

COMPILED = [(re.compile(pattern), remedy, scan_strings) for pattern, remedy, scan_strings in BANNED]


def mask_comments_and_strings(text: str, *, keep_strings: bool = False) -> str:
    """Blank Swift comments and string literals, preserving offsets and newlines.

    A banned name written in prose or in a test fixture string is not a
    reintroduction of the thing. Blanking rather than deleting keeps every line
    number identical to the original file.
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

        if char in '#"' and not keep_strings:
            hashes = 0
            cursor = index
            while cursor < length and text[cursor] == "#":
                hashes += 1
                cursor += 1
            if cursor >= length or text[cursor] != '"':
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
                    break
                cursor += 1

            blank(index, cursor)
            index = cursor
            continue

        index += 1

    return "".join(out)


def check_source(source: str, *, path_label: str) -> list[str]:
    masked = mask_comments_and_strings(source)
    comments_only = mask_comments_and_strings(source, keep_strings=True)
    lines = source.splitlines()
    errors: list[str] = []
    for pattern, remedy, scan_strings in COMPILED:
        haystack = comments_only if scan_strings else masked
        for match in pattern.finditer(haystack):
            lineno = haystack.count("\n", 0, match.start()) + 1
            text = lines[lineno - 1].strip() if lineno <= len(lines) else ""
            errors.append(f"{path_label}:{lineno}: {text}\n  {remedy}")
    return errors


def find_violations(sources_dir: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(sources_dir.rglob("*.swift")):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file is a real failure
            print(f"check-single-chat-shell: cannot read {path}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        try:
            label = str(path.relative_to(Path.cwd()))
        except ValueError:
            label = str(path)
        errors.extend(check_source(source, path_label=label))
    return errors


def run_self_test() -> None:
    """Prove both directions on in-memory fixtures, without touching the tree."""
    clean = (
        "import SwiftUI\n\n"
        "struct ChatBubble: View {\n"
        "  let chatFirstRichBlockContext: ChatFirstRichBlockContext\n"
        "}\n"
        '// A comment may name useLegacyHomeDesign and DashboardPage( without failing.\n'
        'let hint = "richBlockRenderingEnabled"\n'
    )
    clean_errors = check_source(clean, path_label="fixture-clean.swift")
    if clean_errors:
        raise SystemExit(f"self-test false positive on clean fixture: {clean_errors}")

    for fixture, needle in (
        ('@AppStorage("useLegacyHomeDesign") private var flag = false\n', "useLegacyHomeDesign"),
        ("var context: ChatFirstRichBlockContext? = nil\nlet x = chatFirstRichBlockContext == nil\n",
         "chatFirstRichBlockContext"),
        ("let g = group(blocks, richBlockRenderingEnabled: true)\n", "richBlockRenderingEnabled"),
        ("var sample = ChatFirstShellCapabilitySample()\n", "ChatFirstShellCapabilitySample"),
        ("body = DashboardPage(viewModel: viewModel)\n", "DashboardPage"),
    ):
        errors = check_source(fixture, path_label="fixture-fail.swift")
        if not any(needle in error for error in errors):
            raise SystemExit(f"self-test missed {needle!r} fail mode; errors={errors!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=DEFAULT_SOURCES_DIR,
        help="root of the Swift sources to scan (default: desktop/macos/Desktop/Sources)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the in-memory fixtures for this checker, then exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_test()
        print("OK: single-chat-shell checker self-test passed.")
        return 0

    sources_dir: Path = args.sources_dir
    if not sources_dir.is_dir():
        print(f"check-single-chat-shell: sources dir not found: {sources_dir}", file=sys.stderr)
        return 2

    errors = find_violations(sources_dir)
    if not errors:
        print("ok: one chat shell, and every content block renders on every surface")
        return 0

    print("FAIL: a second chat shell (or an inert content block) is growing back")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
