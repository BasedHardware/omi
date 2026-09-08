#!/usr/bin/env python3
"""Author the failure-class retirement diff the advisory report already justifies.

`scripts/failure-class report` decides which classes are closure-eligible, but it
is deliberately non-mutating and has no event source of its own: without
`--events-file` it returns zero events and a `no_event_source` warning. Nothing
scheduled ever supplied that feed, so the lifecycle shipped complete and never
ran.

This script closes that gap and nothing else:

  1. Build the merged-PR event feed for the quiet period (`gh`, or a fixture).
  2. Refuse to proceed unless the feed provably spans the window. A truncated
     feed makes every class report "no classified instance", so the job would
     stay green forever while retiring nothing -- the same false-green failure
     as a check that executes no tests.
  3. Run `scripts/failure-class report` and apply the two-field retirement edit
     (`status: dormant` + `dormant_since`) for each closure-eligible class.
  4. Write PR-body evidence, and surface any class whose recurrence requires an
     explicit reopen.

It never merges and never decides. The reviewable diff is the whole output; a
maintainer merging it is the confirmation the lifecycle requires.

LIFECYCLE: permanent
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS_RELATIVE_PATH = Path(".github/failure-classes")
FAILURE_CLASS_CLI = REPO_ROOT / "scripts/failure-class"
EVENTS_SCHEMA_VERSION = 1
# Well above the ~750 PRs a 14-day window holds at current merge rate; the
# truncation guard below is what actually keeps this honest.
FETCH_LIMIT = 3000
DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[dh])$")


class RetirementError(RuntimeError):
    """A condition that must stop the run rather than produce a partial diff."""


def parse_duration(text: str) -> timedelta:
    match = DURATION_RE.match(text)
    if not match:
        raise RetirementError(f"--since must look like 14d or 24h, got {text!r}")
    value = int(match.group("value"))
    return timedelta(days=value) if match.group("unit") == "d" else timedelta(hours=value)


def parse_timestamp(text: str) -> datetime:
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_events(cutoff: datetime, runner=subprocess.run) -> dict[str, Any]:
    """Fetch merged-PR bodies for the quiet period via gh."""
    search = f"merged:>={cutoff.date().isoformat()}"
    completed = runner(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--search",
            search,
            "--limit",
            str(FETCH_LIMIT),
            "--json",
            "number,body,mergedAt",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RetirementError(f"gh pr list failed ({completed.returncode}): {completed.stderr.strip()}")
    try:
        raw = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RetirementError(f"gh pr list returned unparseable JSON: {exc}") from exc
    events = [
        {"number": item.get("number"), "body": item.get("body") or "", "merged_at": item["mergedAt"]}
        for item in raw
        if item.get("mergedAt")
    ]
    return {"schema_version": EVENTS_SCHEMA_VERSION, "events": events}


def assert_feed_spans_window(feed: dict[str, Any], cutoff: datetime) -> None:
    """Refuse a feed that cannot prove coverage of the quiet period.

    The search asks for everything merged since the cutoff, so a result set
    smaller than the fetch limit covers the window by construction. Hitting the
    limit means the oldest instances were silently dropped, which would report
    healthy classes as instance-free.
    """
    events = feed.get("events") or []
    if len(events) >= FETCH_LIMIT:
        raise RetirementError(
            f"event feed hit the {FETCH_LIMIT}-record fetch limit, so coverage of the window "
            f"since {cutoff.isoformat()} cannot be proven; raise FETCH_LIMIT or shorten --since"
        )
    if not events:
        raise RetirementError(
            f"event feed is empty for the window since {cutoff.isoformat()}; a repository with "
            "merges in the quiet period should never produce an empty feed"
        )


def run_report(events_path: Path, since: str, now: datetime, root: Path, runner=subprocess.run) -> dict[str, Any]:
    completed = runner(
        [
            sys.executable,
            str(FAILURE_CLASS_CLI),
            "report",
            "--since",
            since,
            "--events-file",
            str(events_path),
            "--now",
            now.isoformat().replace("+00:00", "Z"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RetirementError(
            f"failure-class report returned unparseable JSON (exit {completed.returncode}): "
            f"{exc}; stderr: {completed.stderr.strip()}"
        ) from exc
    errors = report.get("errors") or []
    warnings = report.get("warnings") or []
    if errors:
        raise RetirementError(f"failure-class report reported errors: {json.dumps(errors)}")
    if warnings:
        raise RetirementError(f"failure-class report reported warnings: {json.dumps(warnings)}")
    return report


STATUS_LINE_RE = re.compile(r'^(?P<indent>[ \t]*)"status": "open"(?P<comma>,?)[ \t]*$', re.MULTILINE)


def apply_retirement(definition_path: Path, dormant_since: datetime) -> None:
    """Rewrite only the status line, in place.

    A `json.loads` / `json.dumps` round trip reflows the hand-maintained inline
    arrays in these definitions, burying the two-field lifecycle change in
    unrelated formatting churn. The diff a maintainer reviews must be exactly
    the state transition, so edit the text surgically and re-parse to prove the
    result is still valid JSON with the intended fields.
    """
    original = definition_path.read_text(encoding="utf-8")
    timestamp = dormant_since.isoformat().replace("+00:00", "Z")

    match = STATUS_LINE_RE.search(original)
    if not match:
        raise RetirementError(f'{definition_path} has no `"status": "open"` line to retire')
    indent = match.group("indent")
    replacement = f'{indent}"status": "dormant",\n{indent}"dormant_since": "{timestamp}"{match.group("comma")}'
    updated = original[: match.start()] + replacement + original[match.end() :]

    data = json.loads(updated)
    if data.get("status") != "dormant" or data.get("dormant_since") != timestamp:
        raise RetirementError(f"{definition_path}: retirement edit did not produce the expected lifecycle fields")
    definition_path.write_text(updated, encoding="utf-8")


def render_evidence(report: dict[str, Any], eligible: list[dict[str, Any]], reopen: list[dict[str, Any]]) -> str:
    lines = [
        "Automated failure-class retirement, authored from the advisory recurrence report.",
        "",
        f"- report `as_of`: `{report.get('as_of')}`",
        f"- quiet period: `{report.get('since')}`",
        f"- merged-PR events considered: {report.get('events_considered')}",
        "",
        "## Classes retired in this diff",
        "",
    ]
    if eligible:
        lines.append("| class | last classified instance | merged at |")
        lines.append("|---|---|---|")
        for entry in eligible:
            instance = entry.get("last_reported_instance") or {}
            lines.append(f"| `{entry['id']}` | #{instance.get('number', '?')} | {instance.get('merged_at', '?')} |")
    else:
        lines.append("None.")
    lines += [
        "",
        "Each class above reported no classified recurrence during the quiet period.",
        "Merging this PR is the maintainer confirmation the lifecycle requires; recurrence",
        "after retirement requires an explicit reopen.",
        "",
    ]
    if reopen:
        lines += [
            "## Reopen required",
            "",
            "A dormant class was classified again. Reopening is judgment work, not this diff:",
            "",
        ]
        lines += [f"- `{entry['id']}`" for entry in reopen]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="14d", help="Quiet period, such as 14d or 24h (default: 14d).")
    parser.add_argument("--now", help="UTC ISO-8601 timestamp; defaults to now.")
    parser.add_argument("--events-file", type=Path, help="Use a local event feed instead of querying gh.")
    parser.add_argument("--feed-out", type=Path, help="Write the fetched feed here (default: a temp file).")
    parser.add_argument("--evidence-file", type=Path, help="Write PR-body evidence markdown here.")
    parser.add_argument("--apply", action="store_true", help="Write the retirement edits (default: report only).")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root holding the definitions.")
    args = parser.parse_args(argv)

    try:
        quiet_period = parse_duration(args.since)
        now = parse_timestamp(args.now) if args.now else datetime.now(timezone.utc)
        cutoff = now - quiet_period

        if args.events_file:
            feed = json.loads(args.events_file.read_text(encoding="utf-8"))
            events_path = args.events_file
        else:
            feed = fetch_events(cutoff)
            # Never default into the work tree: a stray feed file would land in
            # the retirement PR alongside the lifecycle change.
            events_path = args.feed_out or Path(tempfile.gettempdir()) / "failure-class-events.json"
            events_path.write_text(json.dumps(feed, indent=2) + "\n", encoding="utf-8")

        assert_feed_spans_window(feed, cutoff)
        report = run_report(events_path, args.since, now, args.root)

        classes = report.get("classes") or []
        eligible = [entry for entry in classes if entry.get("closure_eligible")]
        reopen = [entry for entry in classes if entry.get("reopen_required")]

        definitions_dir = args.root / DEFINITIONS_RELATIVE_PATH
        if args.apply:
            for entry in eligible:
                definition = definitions_dir / f"{entry['id']}.json"
                if not definition.exists():
                    raise RetirementError(f"closure-eligible class has no definition file: {definition}")
                apply_retirement(definition, now)

        if args.evidence_file:
            args.evidence_file.write_text(render_evidence(report, eligible, reopen), encoding="utf-8")

        summary = {
            "schema_version": EVENTS_SCHEMA_VERSION,
            "events_considered": report.get("events_considered"),
            "retired": [entry["id"] for entry in eligible],
            "reopen_required": [entry["id"] for entry in reopen],
            "applied": bool(args.apply),
        }
        print(json.dumps(summary, indent=2))
        # A retired class that was classified again is a recurrence the registry
        # must not absorb silently; fail the run so a human looks at it.
        return 1 if reopen else 0
    except RetirementError as exc:
        print(f"failure-class retirement: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
