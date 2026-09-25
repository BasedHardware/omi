#!/usr/bin/env python3
"""Fail when a failure class recurs without producing a reusable guard surface.

Root AGENTS.md: "If two or more recent fixes share the cause, add a reusable
guard surface in the same PR." Nothing enforced that. Between 2026-06-16 and
2026-07-24, FC-split-mutation-authority was declared on 30 first-parent
integration changes while its definition still listed `evidence_prs: [9365,
9597]` and named no guard artifact at all. Recurrence had become paperwork.

This check counts declarations of each class over a recent window and requires
that a class at or above the threshold names a `canonical_prevention_artifact`.

Determinism and hermeticity:
- Counts come from `git log --first-parent` in the checkout. No network.
- Integration changes are counted, not raw commits: one merged PR routinely
  carries a dozen `fix:` commits, so a raw-commit threshold would be noise.
- The change under review is counted once wherever the window is measured: its
  `--pr-body-file` declaration is added only when HEAD did not already carry it,
  so a PR run, that PR's main push, and a local pre-push run agree on the count.
- History-dependent checks must degrade safely. On a shallow clone, or when
  first-parent history does not reach back to the window start, this prints a
  loud SKIP and exits 0 rather than passing silently or failing spuriously.
- Classes already over threshold when this landed are grandfathered by an
  explicit allowlist up to each entry's `declarations_at_baseline`; a new
  declaration above that baseline fails until a guard artifact is recorded.
  The allowlist only shrinks: once a class gains an artifact, its entry must
  be removed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFINITIONS_RELATIVE_PATH = Path(".github/failure-classes")
ALLOWLIST_RELATIVE_PATH = Path(".github/scripts/failure_class_guard_ratchet_allowlist.json")
ALLOWLIST_SCHEMA_VERSION = 1
DEFAULT_WINDOW_DAYS = 90
DEFAULT_THRESHOLD = 3
DECLARATION_RE = re.compile(r"^[ \t]*Failure-Class:[ \t]*(FC-[a-z0-9-]+)[ \t]*$", re.MULTILINE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class GrandfatherEntry:
    reason: str
    declarations_at_baseline: int


class CheckError(Exception):
    """A deterministic input or repository error intended for CLI output."""


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CheckError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def declarations_in(text: str) -> set[str]:
    return set(DECLARATION_RE.findall(HTML_COMMENT_RE.sub("", text)))


def load_definitions(root: Path) -> dict[str, dict[str, Any]]:
    directory = root / DEFINITIONS_RELATIVE_PATH
    if not directory.is_dir():
        raise CheckError(f"missing {DEFINITIONS_RELATIVE_PATH}")
    definitions: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CheckError(f"invalid definition {path.name}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise CheckError(f"invalid definition {path.name}: missing string 'id'")
        definitions[data["id"]] = data
    return definitions


def load_allowlist(root: Path) -> dict[str, GrandfatherEntry]:
    """Return grandfathered class id -> entry metadata.

    A missing allowlist is not an error: the ratchet is simply unrelaxed.
    """
    path = root / ALLOWLIST_RELATIVE_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckError(f"invalid allowlist {ALLOWLIST_RELATIVE_PATH}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != ALLOWLIST_SCHEMA_VERSION:
        raise CheckError(f"{ALLOWLIST_RELATIVE_PATH} must be a schema_version {ALLOWLIST_SCHEMA_VERSION} object")
    entries = data.get("grandfathered")
    if not isinstance(entries, list):
        raise CheckError(f"{ALLOWLIST_RELATIVE_PATH} must contain a 'grandfathered' array")
    allowlist: dict[str, GrandfatherEntry] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CheckError(f"grandfathered[{index}] must be an object")
        class_id = entry.get("id")
        reason = entry.get("reason")
        baseline = entry.get("declarations_at_baseline")
        if not isinstance(class_id, str) or not isinstance(reason, str) or not reason.strip():
            raise CheckError(f"grandfathered[{index}] requires a string 'id' and a non-empty 'reason'")
        if not isinstance(baseline, int) or baseline < 0:
            raise CheckError(
                f"grandfathered[{index}] requires a non-negative integer 'declarations_at_baseline'"
            )
        if class_id in allowlist:
            raise CheckError(f"grandfathered contains duplicate id '{class_id}'")
        allowlist[class_id] = GrandfatherEntry(reason=reason, declarations_at_baseline=baseline)
    return allowlist


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CheckError(f"timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def history_reaches(root: Path, cutoff: datetime) -> bool:
    """True when the checkout's first-parent history predates the window start."""
    output = run_git(root, "log", "--first-parent", "--format=%cI", "--max-count=100000")
    dates = [line for line in output.splitlines() if line]
    if not dates:
        return False
    return parse_timestamp(dates[-1]) < cutoff


def declaration_counts(root: Path, cutoff: datetime) -> dict[str, int]:
    """Count first-parent integration changes declaring each class since cutoff.

    A class is counted once per integration change even if the merge message
    carries several declaring commit messages.
    """
    output = run_git(
        root,
        "log",
        "--first-parent",
        f"--since={cutoff.isoformat()}",
        f"--format={FIELD_SEPARATOR}%H{FIELD_SEPARATOR}%B{RECORD_SEPARATOR}",
    )
    counts: dict[str, int] = {}
    for record in output.split(RECORD_SEPARATOR):
        if FIELD_SEPARATOR not in record:
            continue
        _, _, message = record.partition(FIELD_SEPARATOR)
        _, _, message = message.partition(FIELD_SEPARATOR)
        for class_id in declarations_in(message):
            counts[class_id] = counts.get(class_id, 0) + 1
    return counts


def read_pr_body(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def head_declarations(root: Path) -> set[str]:
    """Classes HEAD's own message already contributed to `declaration_counts`.

    `--pr-body-file` stands in for the change under review, which is why its
    declaration is added to the window. On a main push, and on a local run over
    a feature branch, that change is HEAD: `declaration_counts` walks from HEAD
    and counted it already, so adding the body on top counts one integration
    change twice. On a `pull_request` run the checkout is the merge ref, whose
    message declares nothing, and the body stays the only evidence of the
    pending change.
    """
    return declarations_in(run_git(root, "log", "--max-count=1", "--format=%B", "HEAD"))


def evaluate(
    definitions: dict[str, dict[str, Any]],
    allowlist: dict[str, GrandfatherEntry],
    counts: dict[str, int],
    threshold: int,
) -> list[str]:
    """Return failure messages; an empty list means the ratchet holds."""
    failures: list[str] = []
    for class_id, count in sorted(counts.items()):
        definition = definitions.get(class_id)
        if definition is None:
            # An unknown id in history is the failure-class CLI's problem, not
            # this ratchet's; it must not fail a PR that never touched it.
            continue
        if count < threshold:
            continue
        if definition.get("canonical_prevention_artifact"):
            continue
        if class_id in allowlist:
            entry = allowlist[class_id]
            if count > entry.declarations_at_baseline:
                failures.append(
                    f"{class_id}: {count} declarations in the window (baseline "
                    f"{entry.declarations_at_baseline}) with no 'canonical_prevention_artifact'. "
                    f"A grandfathered class must not recur without recording its guard surface in "
                    f"{DEFINITIONS_RELATIVE_PATH / (class_id + '.json')}, then removing its entry from "
                    f"{ALLOWLIST_RELATIVE_PATH}."
                )
                continue
            print(f"  GRANDFATHERED {class_id}: {count} declaration(s) — {entry.reason}")
            continue
        failures.append(
            f"{class_id}: {count} declarations in the window (threshold {threshold}) with no "
            f"'canonical_prevention_artifact'. Add the reusable guard surface and record its path in "
            f"{DEFINITIONS_RELATIVE_PATH / (class_id + '.json')}, or grandfather it explicitly in "
            f"{ALLOWLIST_RELATIVE_PATH}."
        )

    for class_id, entry in sorted(allowlist.items()):
        definition = definitions.get(class_id)
        if definition is None:
            failures.append(
                f"{class_id}: grandfathered in {ALLOWLIST_RELATIVE_PATH} but no such definition exists; "
                f"remove the entry."
            )
        elif definition.get("canonical_prevention_artifact"):
            failures.append(
                f"{class_id}: now records a 'canonical_prevention_artifact', so its grandfather entry in "
                f"{ALLOWLIST_RELATIVE_PATH} must be removed. The allowlist only shrinks. ({entry.reason})"
            )
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="Repository root (default: git toplevel of cwd).")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--pr-body-file",
        type=Path,
        default=None,
        help=(
            "PR body under review; its declaration counts toward the window so the declaring PR fails first, "
            "unless HEAD already declared it and was counted from history."
        ),
    )
    parser.add_argument("--now", default=None, help="UTC ISO-8601 timestamp; makes the window deterministic in tests.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = (args.root or Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())).resolve()
        if args.window_days <= 0 or args.threshold <= 0:
            raise CheckError("--window-days and --threshold must be positive")
        now = parse_timestamp(args.now) if args.now else datetime.now(timezone.utc)
        cutoff = now - timedelta(days=args.window_days)

        if run_git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
            print(
                "SKIP failure-class guard ratchet: shallow clone cannot establish the "
                f"{args.window_days}-day declaration window. Re-run with full history "
                "(actions/checkout fetch-depth: 0) to enforce it.",
                flush=True,
            )
            return 0
        if not history_reaches(root, cutoff):
            print(
                "SKIP failure-class guard ratchet: first-parent history does not reach back to "
                f"{cutoff.date().isoformat()}, so the {args.window_days}-day window is not measurable here.",
                flush=True,
            )
            return 0

        definitions = load_definitions(root)
        allowlist = load_allowlist(root)
        counts = declaration_counts(root, cutoff)
        already_counted = head_declarations(root)
        for class_id in declarations_in(read_pr_body(args.pr_body_file)):
            if class_id in already_counted:
                continue
            counts[class_id] = counts.get(class_id, 0) + 1
    except (CheckError, ValueError) as exc:
        print(f"FAIL: failure-class guard ratchet could not run: {exc}", file=sys.stderr)
        return 2

    print(
        f"Failure-class guard ratchet: window={args.window_days}d since={cutoff.date().isoformat()} "
        f"threshold={args.threshold} classes_declared={len(counts)}"
    )
    failures = evaluate(definitions, allowlist, counts, args.threshold)
    if failures:
        print("FAIL: a recurring failure class has no reusable guard surface.", file=sys.stderr)
        for message in failures:
            print(f"- {message}", file=sys.stderr)
        return 1
    print("OK: every class at or above the threshold names a guard artifact or is explicitly grandfathered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
