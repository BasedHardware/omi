#!/usr/bin/env python3
"""P6: pipeline tuning names before/after numbers; new states name their exit.

This is a disclosure ratchet, not semantic analysis: indirect/formula tuning
can escape detection. Only changed code is evidence; unchanged diff context
can identify a state field but cannot introduce a knob or literal.

Body evidence must be visible rendered prose: comments, code, and link titles
are removed. It guards against omission by honest authors, not adversarial
Markdown; reviewers still read the rendered body.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

TRIGGERS = (
    "backend/config/batch_pipeline.py",
    "backend/utils/batch_pipeline/**",
    "backend/charts/batch-pipeline-worker/**",
    "backend/charts/pusher/**",
    "backend/utils/pusher_*.py",
)
KNOB = r"(?:max|min|limit|cap|concurrenc\w*|workers?|pool\w*|page_size|batch_size|drains?\w*|per_second|qps|throttle\w*|maxReplicas|minReplicas|targetBacklogPerWorker)\w*"
NUMBER = r"-?(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?"
ASSIGNMENT = re.compile(rf"(?<![`'\"])\b(?P<knob>{KNOB})\s*[:=]\s*(?P<value>{NUMBER})", re.I)
GETENV = re.compile(
    rf"(?<![`'\"])\bos\.getenv\(\s*['\"](?P<knob>\w*CONCURRENCY\w*)['\"]\s*,\s*['\"]?(?P<value>{NUMBER})", re.I
)
EXCLUDED = re.compile(r"_(?:ENABLED|PERCENT|UIDS|ALLOWLIST|URL)$", re.I)
LITERAL = re.compile(r"['\"]([a-z][a-z0-9_]{3,40})['\"]")
STATE_NAME = r"(?:\w+_)?(?:status|state|phase|disposition|outcome|reason)"
STATE_OPERATOR = r"(?:==|!=|<=|>=|<|>|(?<![=!<>])=(?!=))"
STATE_VALUE = re.compile(
    rf"(?:(?<!['\"])\b{STATE_NAME}\b\s*(?::|{STATE_OPERATOR})"
    rf"|['\"]{STATE_NAME}['\"]\s*(?::|\]\s*{STATE_OPERATOR}))\s*\(*\s*$", re.I
)
STATE_COMPARE = re.compile(rf"^\s*\)*\s*(?:==|!=|<=|>=|<|>)\s*\b{STATE_NAME}\b", re.I)
EXIT = re.compile(r"\b(?:exit\w*|terminal\w*|dead.letter\w*|re-?entr\w*|clear\w*|recover\w*)\b", re.I)
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)  # unclosed runs to the end
NON_CODE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`[^`]*`|#.*")


def triggered(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in TRIGGERS)


def diff_hunks(diff: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Keep files and hunks separate: proximity must never cross either boundary."""
    path = ""
    hunks: list[tuple[str, list[tuple[str, str]]]] = []
    lines: list[tuple[str, str]] | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, lines = "", None
        elif line.startswith("+++ "):
            if line[4:] != "/dev/null":
                path = line[4:].removeprefix("b/")
        elif line.startswith("--- ") and not path:
            path = line[4:].removeprefix("a/")
        elif line.startswith("@@ "):
            lines = []
            if triggered(path):
                hunks.append((path, lines))
        elif lines is not None and line[:1] in ("+", "-", " "):
            lines.append((line[0], line[1:]))
    return hunks


def code(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith(("#", "//", "/*", "* ", '"""', "'''"))


def state_literals(line: str, prefix: str = "") -> set[str]:
    """Require a direct state assignment/comparison, never mere word proximity."""
    values: set[str] = set()
    text = prefix + line
    for match in NON_CODE.finditer(text):
        literal = LITERAL.fullmatch(match.group())
        if match.start() < len(prefix) or not literal:
            continue
        # Mask strings/comments except quoted state keys in dicts/subscripts.
        before = NON_CODE.sub(
            lambda item: item.group() if re.fullmatch(rf"['\"]{STATE_NAME}['\"]", item.group(), re.I)
            else re.sub(r"[^\n]", " ", item.group()), text[:match.start()]
        )
        if STATE_VALUE.search(before) or STATE_COMPARE.search(text[match.end():]):
            values.add(literal.group(1))
    return values


def detect(diff: str, exists_at_base: Callable[[str], bool]) -> tuple[set[str], set[str], set[str]]:
    """Return changed knobs, new states, and knobs without a removed numeric value."""
    numeric: dict[tuple[str, str, str], set[str]] = {}
    candidates: set[str] = set()
    for path, lines in diff_hunks(diff):
        for sign, line in lines:
            if sign in ("+", "-") and code(line):
                non_code = [match.span() for match in NON_CODE.finditer(line)]
                for pattern in (ASSIGNMENT, GETENV):
                    for match in pattern.finditer(line):
                        if not EXCLUDED.search(match["knob"]) and not any(
                            start <= match.start() < end for start, end in non_code
                        ):
                            key = (path, match["knob"], match["value"].replace("_", ""))
                            numeric.setdefault(key, set()).add(sign)
        # Carry only new-side syntax for direct assignments split across lines.
        added_side = [(sign, line) for sign, line in lines if sign != "-"]
        for i, (sign, line) in enumerate(added_side):
            if sign != "+" or not code(line):
                continue
            prefix = "\n".join(text for _, text in added_side[max(0, i - 3) : i]) + "\n"
            candidates.update(state_literals(line, prefix))
    # #24738 only added client/source-metadata arguments beside max_count=4096.
    # The same knob/value on both sides is not tuning (including moved lines).
    knobs = {key[1] for key, signs in numeric.items() if len(signs) == 1}
    prior_knobs = {key[1] for key, signs in numeric.items() if "-" in signs}
    return knobs, {literal for literal in candidates if not exists_at_base(literal)}, knobs - prior_knobs


def prose(body: str) -> str:
    """Remove HTML comments (including unclosed ones), fenced and indented code
    blocks (including unclosed fences and ones inside blockquotes), and code spans."""
    lines: list[str] = []
    fence = ""
    indented = False  # inside an indented code block
    opens_code = True  # previous line was blank, a heading, or start of body
    for line in HTML_COMMENT.sub("", body).splitlines(keepends=True):
        # Judge code blocks on the text inside any blockquote markers.
        text = re.sub(r"^(?: {0,3}> ?)+", "", line.rstrip("\r\n"))
        lead = re.match(r"[ \t]*", text).group(0)
        cols = 0
        for char in lead:
            cols = cols + 4 - cols % 4 if char == "\t" else cols + 1
        if fence:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*", text):
                fence = ""
            lines.append("\n")
            continue
        if text.strip() and cols >= 4 and (opens_code or indented):
            # An indented code block follows a blank line or heading; strip it whole.
            indented, opens_code = True, False
            lines.append("\n")
            continue
        indented = False
        opens_code = not text.strip() or re.match(r" {0,3}#{1,6}(?:[ \t]|$)", text) is not None
        if match := re.match(r"^ {0,3}(`{3,}|~{3,})", text):
            fence = match.group(1)
            lines.append("\n")
        else:
            lines.append(line)
    text = re.sub(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)", " ", "".join(lines), flags=re.S)
    # Link titles only show on hover: keep [text](url), drop "title".
    return re.sub(r"(\]\(\s*(?:<[^<>]*>|[^\s()<>]*(?:\([^\s()]*\)[^\s()<>]*)*))\s+(?:\"[^\"]*\"|'[^']*'|\([^()]*\))\s*\)", r"\1)", text)


def sections(body: str) -> list[str]:
    # Any Markdown heading starts a section; don't combine unrelated before and
    # after claims. HTML template examples cannot satisfy the contract.
    return re.split(r"(?m)(?=^(?: {0,3}> ?)* {0,3}#{1,6}[ \t]+)", body)


def token(name: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I) is not None


def numbers_disclosed(part: str, knobs: set[str], new_knobs: set[str]) -> bool:
    named = {knob for knob in knobs if token(knob, part)}
    if not named:
        return False
    if (
        re.search(r"\bbefore\b.{0,120}\d", part, re.I | re.S)
        and re.search(r"\bafter\b.{0,120}\d", part, re.I | re.S)
    ):
        return True
    for knob in named:
        for match in re.finditer(rf"(?<!\w){re.escape(knob)}(?!\w)", part, re.I):
            nearby = part[max(0, match.start() - 120):match.end() + 120]
            if re.search(rf"\bfrom\b.{{0,120}}{NUMBER}.{{0,120}}\bto\b.{{0,120}}{NUMBER}", nearby, re.I | re.S):
                return True
            if re.search(rf"{NUMBER}\s*(?:->|→)\s*{NUMBER}", nearby):
                return True
            if knob in new_knobs and re.search(rf"\b(?:new\s*:\s*|initial\s+){NUMBER}", nearby, re.I):
                return True
    return False


def validate(knobs: set[str], states: set[str], body: str, new_knobs: set[str] | None = None) -> tuple[list[str], list[str]]:
    cleaned = prose(body)
    parts = sections(cleaned)
    errors: list[str] = []
    notices: list[str] = []
    for field, needed in (("Numbers-waived", knobs), ("State-exit-waived", states)):
        waiver = re.search(rf"(?m)^{field}:[ \t]*(\S[^\r\n]*)$", cleaned)
        if needed and waiver:
            notices.append(f"{field}: {waiver.group(1)}")
            if field == "Numbers-waived":
                knobs = set()
            else:
                states = set()
    if knobs and not any(numbers_disclosed(part, knobs, new_knobs or set()) for part in parts):
        errors.append(
            f"Tuning ({', '.join(sorted(knobs))}) requires before and after numbers in one section "
            "naming at least one knob (before/after, from/to, or an arrow); a new knob may use new: or initial; "
            "or Numbers-waived: <reason>."
        )
    for state in sorted(states):
        if not (token(state, cleaned) and EXIT.search(cleaned)):
            errors.append(f"New state '{state}' must name its exit/terminal/recovery path, or State-exit-waived: <reason>.")
    return errors, notices


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def existing_literals(root: Path, base: str, literals: set[str]) -> set[str]:
    # Search the entire merge-base tree, not just pipeline paths. grep's exit 1
    # means absent; a missing ref/object or any other error must fail closed.
    if not literals:
        return set()
    patterns = [arg for literal in sorted(literals) for arg in ("-e", literal)]
    # One tree scan per PR. Only the fixed-string matches are returned; --text
    # keeps the anywhere-at-base rule even for a match inside a binary blob.
    result = subprocess.run(
        ["git", "grep", "--text", "-h", "-o", "-F", *patterns, base, "--"],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep at {base}: {result.stderr.strip()}")
    matches = set(result.stdout.splitlines())
    # grep can emit only the longer of overlapping patterns. A shorter literal
    # contained in that match is also present at base.
    return {literal for literal in literals if any(literal in match for match in matches)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body-file", type=Path, default=os.getenv("OMI_PR_BODY_FILE"))
    parser.add_argument("--run-tests", action="store_true", help="Run the hermetic regression suite before checking (manifest entry).")
    args = parser.parse_args()
    try:
        if args.run_tests:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("test_check_batch_tuning_disclosure.py"))])
            if result.returncode:
                return result.returncode
        base = git(args.root, "merge-base", args.base, args.head).strip()
        diff = git(args.root, "diff", "--no-ext-diff", "--no-renames", "--unified=3", base, args.head, "--", *TRIGGERS)
        knobs, candidates, new_knobs = detect(diff, lambda _: False)
        states = candidates - existing_literals(args.root, base, candidates)
        body = args.pr_body_file.read_text(encoding="utf-8") if args.pr_body_file else ""
        errors, notices = validate(knobs, states, body, new_knobs)
    except (OSError, RuntimeError) as exc:
        print(f"FAIL: batch-pipeline-tuning-disclosure: {exc}", file=sys.stderr)
        return 2
    for notice in notices:
        print(notice)
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        print("Rerun scripts/pr-preflight with --pr-body-file <draft.md> or OMI_PR_BODY_FILE.", file=sys.stderr)
        return 1
    print(f"OK: batch-pipeline-tuning-disclosure ({len(knobs)} knobs, {len(states)} new states).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
