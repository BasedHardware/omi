#!/usr/bin/env python3
"""P6: pipeline tuning names before/after numbers; new states name their exit.

This is a disclosure ratchet, not semantic analysis: indirect/formula tuning
can escape detection. Only changed code is evidence; unchanged diff context
can identify a state field but cannot introduce a knob or literal.
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
ASSIGNMENT = re.compile(rf"(?<![`'\"])\b(?P<knob>{KNOB})\s*[:=]\s*[-\d.]", re.I)
GETENV = re.compile(
    r"(?<![`'\"])\bos\.getenv\(\s*['\"](?P<knob>\w*CONCURRENCY\w*)['\"]\s*,\s*['\"]?[-\d.]", re.I
)
EXCLUDED = re.compile(r"_(?:ENABLED|PERCENT|UIDS|ALLOWLIST|URL)$", re.I)
LITERAL = re.compile(r"['\"]([a-z][a-z0-9_]{3,40})['\"]")
STATE_CONTEXT = re.compile(r"\b(?:\w+_)?(?:status|state|phase|disposition|outcome|reason)\b", re.I)
EXIT = re.compile(r"\b(?:exit\w*|terminal\w*|dead.letter\w*|re-?entr\w*|clear\w*|recover\w*)\b", re.I)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
FIELD_VALUE = re.compile(r"(?P<field>[a-zA-Z_]\w*)['\"]?\]?\s*(?::|(?<![=!<>])=(?!=))\s*$")
FIELD_LOOKUP = re.compile(r"(?:\.(?:get|pop|setdefault)\(|[\w)\]]\[)\s*$")


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


def state_literals(line: str) -> set[str]:
    """Ignore field names/lookups and values explicitly assigned to other fields.

    The historical sweep found registration_origin next to state updates: a
    new metadata key is not a lifecycle value merely because it is nearby.
    """
    values: set[str] = set()
    for match in LITERAL.finditer(line):
        before, after = line[: match.start()], line[match.end() :]
        field = FIELD_VALUE.search(before)
        if after.lstrip().startswith(":") or FIELD_LOOKUP.search(before):
            continue
        if field and not STATE_CONTEXT.fullmatch(field["field"]):
            continue
        values.add(match.group(1))
    return values


def detect(diff: str, exists_at_base: Callable[[str], bool]) -> tuple[set[str], set[str]]:
    knobs: set[str] = set()
    candidates: set[str] = set()
    for _, lines in diff_hunks(diff):
        for sign, line in lines:
            if sign in ("+", "-") and code(line):
                for pattern in (ASSIGNMENT, GETENV):
                    knobs.update(m["knob"] for m in pattern.finditer(line) if not EXCLUDED.search(m["knob"]))
        # Count distance in the new file, excluding removed lines entirely.
        added_side = [(sign, line) for sign, line in lines if sign != "-"]
        for i, (sign, line) in enumerate(added_side):
            if sign != "+" or not code(line):
                continue
            nearby = added_side[max(0, i - 3) : i + 4]
            if any(code(text) and STATE_CONTEXT.search(text) for _, text in nearby):
                candidates.update(state_literals(line))
    return knobs, {literal for literal in candidates if not exists_at_base(literal)}


def sections(body: str) -> list[str]:
    # Any Markdown heading starts a section; don't combine unrelated before and
    # after claims. HTML template examples cannot satisfy the contract.
    return re.split(r"(?m)(?=^ {0,3}#{1,6}[ \t]+)", HTML_COMMENT.sub("", body))


def token(name: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I) is not None


def validate(knobs: set[str], states: set[str], body: str) -> tuple[list[str], list[str]]:
    parts = sections(body)
    cleaned = HTML_COMMENT.sub("", body)
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
    if knobs and not any(
        re.search(r"\bbefore\b.{0,120}\d", part, re.I | re.S)
        and re.search(r"\bafter\b.{0,120}\d", part, re.I | re.S)
        and any(token(knob, part) for knob in knobs)
        for part in parts
    ):
        errors.append(
            f"Tuning ({', '.join(sorted(knobs))}) requires before and after numbers in one section "
            "naming at least one knob, or Numbers-waived: <reason>."
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
        knobs, candidates = detect(diff, lambda _: False)
        states = candidates - existing_literals(args.root, base, candidates)
        body = args.pr_body_file.read_text(encoding="utf-8") if args.pr_body_file else ""
        errors, notices = validate(knobs, states, body)
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
