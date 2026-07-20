#!/usr/bin/env python3
"""Maintain the observable, deduplicated desktop-qualification handoff state.

This state is deliberately operational metadata, not qualification evidence and
not promotion authority. The trusted qualification workflow is the only place
that can claim a dispatch key and run the expensive qualification work.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import fail, parse_metadata, update_metadata  # noqa: E402

KEY_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,160}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
STATES = frozenset({"pending", "queued", "running", "failed", "qualified", "dispatch_failed"})


def _string(value: str, label: str, *, pattern: re.Pattern[str] | None = None, limit: int = 0) -> str:
    result = value.strip()
    if not result or "\n" in result or "\r" in result:
        fail(f"{label} must be a non-empty single-line value")
    if limit and len(result) > limit:
        fail(f"{label} must be at most {limit} characters")
    if pattern is not None and not pattern.fullmatch(result):
        fail(f"{label} has an invalid format")
    return result


def _attempt(value: int) -> str:
    if value < 0 or value > 99:
        fail("dispatch attempt must be between 0 and 99")
    return str(value)


def _values(
    *,
    state: str,
    key: str,
    attempt: int,
    updated_at: str,
    diagnostic: str,
    run_id: str = "",
    run_url: str = "",
) -> dict[str, str]:
    if state not in STATES:
        fail(f"unknown qualification dispatch state: {state}")
    values = {
        "qualificationDispatchState": state,
        "qualificationDispatchKey": _string(key, "dispatch key", pattern=KEY_RE),
        "qualificationDispatchAttempt": _attempt(attempt),
        "qualificationDispatchUpdatedAt": _string(updated_at, "updated_at", pattern=TIMESTAMP_RE),
        "qualificationDispatchDiagnostic": _string(diagnostic, "diagnostic", limit=240),
    }
    if run_id:
        values["qualificationDispatchRunId"] = _string(run_id, "run ID", pattern=re.compile(r"^\d+$"))
    if run_url:
        values["qualificationDispatchRunUrl"] = _string(run_url, "run URL", limit=240)
    return values


def _metadata(body: str) -> dict[str, str]:
    return parse_metadata(body)


def _current_attempt(metadata: dict[str, str]) -> int:
    value = metadata.get("qualificationDispatchAttempt", "0")
    if not value.isdigit():
        fail("existing qualification dispatch attempt is invalid")
    return int(value)


def claim(
    body: str,
    *,
    key: str,
    updated_at: str,
    run_id: str,
    run_url: str,
    allow_retry: bool,
) -> tuple[str, bool, bool, str]:
    """Claim one qualification run inside the authoritative workflow serialiser."""
    metadata = _metadata(body)
    current_state = metadata.get("qualificationDispatchState", "")
    current_key = metadata.get("qualificationDispatchKey", "")
    if current_state and current_state not in STATES:
        fail(f"unknown existing qualification dispatch state: {current_state}")
    if bool(current_state) != bool(current_key):
        fail("existing qualification dispatch claim is incomplete")
    reclaimed_orphaned_claim = False
    if current_state == "running":
        # Every caller is inside the workflow's non-cancelling, per-release
        # concurrency group. Reaching this claim means the previous runner has
        # stopped, so its lingering running record is orphaned and may be
        # reclaimed immediately without introducing a second active runner.
        reclaimed_orphaned_claim = True
    elif current_key == key and current_state == "qualified":
        return body, False, True, "dispatch key already qualified"
    elif current_key == key and current_state == "failed":
        return body, False, False, "dispatch key already failed"
    elif current_key == key and current_state in {"pending", "queued", "dispatch_failed"}:
        # Older candidates may retain this observational state. The runner's
        # concurrency gate is authoritative, so it can claim them once.
        pass
    elif current_state in {"pending", "queued"}:
        return body, False, False, f"candidate already {current_state} under another dispatch key"
    elif current_state == "qualified":
        return body, False, True, "candidate already has completed qualification"
    elif current_state in {"failed", "dispatch_failed"} and not allow_retry:
        return body, False, False, "candidate has a terminal dispatch result; supply an explicit retry nonce"
    attempt = _current_attempt(metadata) + 1
    values = _values(
        state="running",
        key=key,
        attempt=attempt,
        updated_at=updated_at,
        diagnostic=(
            "trusted qualification runner reclaimed an orphaned dispatch claim"
            if reclaimed_orphaned_claim
            else "trusted qualification runner claimed this dispatch key"
        ),
        run_id=run_id,
        run_url=run_url,
    )
    return update_metadata(body, values), True, False, "reclaimed orphaned claim" if reclaimed_orphaned_claim else "claimed"


def complete(body: str, *, key: str, updated_at: str, passed: bool) -> str:
    """Write the terminal runner state without editing factual qualification keys."""
    metadata = _metadata(body)
    if (
        metadata.get("qualificationDispatchKey", "") != key
        or metadata.get("qualificationDispatchState", "") != "running"
    ):
        fail("only the active trusted dispatch key may complete qualification")
    return update_metadata(
        body,
        _values(
            state="qualified" if passed else "failed",
            key=key,
            attempt=_current_attempt(metadata),
            updated_at=updated_at,
            diagnostic=(
                "trusted qualification completed; factual evidence is recorded separately"
                if passed
                else "trusted qualification failed; candidate remains non-live"
            ),
            run_id=metadata.get("qualificationDispatchRunId", ""),
            run_url=metadata.get("qualificationDispatchRunUrl", ""),
        ),
    )


def _write(path: Path, body: str, payload: dict[str, object]) -> None:
    path.write_text(body, encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("claim", "complete"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--input", required=True, type=Path)
        sub.add_argument("--output", required=True, type=Path)
        sub.add_argument("--key", required=True)
        sub.add_argument("--updated-at", required=True)
    claim_parser = subparsers.choices["claim"]
    claim_parser.add_argument("--run-id", required=True)
    claim_parser.add_argument("--run-url", required=True)
    claim_parser.add_argument("--allow-retry", action="store_true")
    complete_parser = subparsers.choices["complete"]
    complete_parser.add_argument("--passed", required=True, choices=("true", "false"))
    args = parser.parse_args()
    body = args.input.read_text(encoding="utf-8")
    if args.command == "claim":
        result, should_run, should_promote, reason = claim(
            body,
            key=args.key,
            updated_at=args.updated_at,
            run_id=args.run_id,
            run_url=args.run_url,
            allow_retry=args.allow_retry,
        )
        _write(args.output, result, {"reason": reason, "should_promote": should_promote, "should_run": should_run})
    else:
        result = complete(body, key=args.key, updated_at=args.updated_at, passed=args.passed == "true")
        _write(args.output, result, {"changed": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
