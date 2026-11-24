#!/usr/bin/env python3
"""Bounded wait for the required UI author approval status on a changelog PR head.

``desktop_auto_release.yml`` admin-merges its changelog-sync PR. The
``UI author approval`` ruleset check is posted asynchronously by
``ui-author-approval.yml`` on ``pull_request_target``, so the merge used to race
the status and fail on every hourly run after 2026-11-12 (SCA-3426). On #25884
the status reached ``success`` 16m43s after PR creation.

This helper replaces that race with a bounded wait on the exact head SHA. It
never merges and never tags: it only reports whether the exact head is approved,
records the authoritative ``refs/heads/main`` SHA at that moment, and fails
closed with the PR, head and reason on timeout, a rejected approval, an
unreadable status, or a changed head. The caller must still bind its merge to
the same SHA (``gh pr merge --match-head-commit``) and compare every fresh base
read to the recorded SHA.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
STATUS_CONTEXT = "UI author approval"
# github-actions[bot] is the account that posts the status from
# ui-author-approval.yml. The ruleset pins the GitHub Actions integration, but
# the admin merge bypasses the ruleset, so the wait verifies the creator itself.
GITHUB_ACTIONS_BOT_ID = 41898282
GITHUB_ACTIONS_BOT_LOGIN = "github-actions[bot]"
EVIDENCE_SCHEMA = "desktop-changelog-approval-wait/v1"

# #25884: PR created 2026-11-20T17:14:43Z, status success 17:31:26Z = 1003s.
# The delay is dominated by runner queue latency for the resolve/guard jobs, so
# the cap keeps ~8 minutes of headroom above the observed value.
DEFAULT_TIMEOUT_SECONDS = 1500
DEFAULT_POLL_SECONDS = 15
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_MAX_CONSECUTIVE_READ_ERRORS = 5

OUTCOME_APPROVED = "approved"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_REJECTED = "approval-rejected"
OUTCOME_UNREADABLE = "status-unreadable"
OUTCOME_HEAD_CHANGED = "head-changed"
OUTCOME_PR_NOT_OPEN = "pr-not-open"
OUTCOME_BASE_CHANGED = "base-changed"
OUTCOME_UNTRUSTED = "status-untrusted"
OUTCOME_BASE_UNREADABLE = "base-unreadable"

# The authoritative base is the branch ref, never the PR's baseRefOid: GitHub
# reported baseRefOid 0a0abbffc54c while refs/heads/main was 8e9537e2e2bd.
DEFAULT_BASE_REF = "refs/heads/main"

SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s*)\S+"),
    re.compile(r"(?i)(bearer\s*)\S+"),
    re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)\b"),
    re.compile(r"(?i)((?:access_)?token=)[^&\s]+"),
)

_monotonic: Callable[[], float] = time.monotonic
_sleep: Callable[[float], None] = time.sleep


class TransientReadError(RuntimeError):
    """A bounded, credential-safe GitHub read failure."""


@dataclass(frozen=True)
class PullRequestSnapshot:
    number: int
    url: str
    state: str
    head_sha: str
    base_ref: str


@dataclass(frozen=True)
class StatusSnapshot:
    state: str
    description: str
    creator_id: int | None
    creator_login: str | None
    created_at: str


def sanitize_api_diagnostic(value: str) -> str:
    """Retain actionable API context without echoing credentials."""
    sanitized = " ".join(value.split())
    for pattern in SECRET_PATTERNS:
        replacement = r"\1<redacted>" if pattern.groups else "<redacted>"
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized[:1000] or "no diagnostic text returned"


def gh_json(args: list[str], *, request_timeout_seconds: int) -> object:
    """Call the authenticated GitHub CLI without exposing input to a shell."""
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=request_timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise TransientReadError(
            f"GitHub API request timed out after {request_timeout_seconds}s"
        ) from error
    if result.returncode:
        detail = sanitize_api_diagnostic(result.stderr or result.stdout)
        raise TransientReadError(f"GitHub API request failed (exit {result.returncode}): {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = sanitize_api_diagnostic(result.stdout)
        raise TransientReadError(f"GitHub API returned invalid JSON: {detail}") from error


def fetch_pull_request(
    repository: str, pr_number: int, *, request_timeout_seconds: int
) -> PullRequestSnapshot:
    payload = gh_json(
        ["api", f"repos/{repository}/pulls/{pr_number}"],
        request_timeout_seconds=request_timeout_seconds,
    )
    if not isinstance(payload, dict):
        raise TransientReadError("GitHub API returned an unexpected pull request payload")
    head = payload.get("head") or {}
    base = payload.get("base") or {}
    return PullRequestSnapshot(
        number=int(payload.get("number") or pr_number),
        url=str(payload.get("html_url") or ""),
        state=str(payload.get("state") or ""),
        head_sha=str(head.get("sha") or ""),
        base_ref=str(base.get("ref") or ""),
    )


def fetch_status(
    repository: str, head_sha: str, context: str, *, request_timeout_seconds: int
) -> StatusSnapshot | None:
    """Return the newest status for ``context`` on ``head_sha``, or None if unposted."""
    payload = gh_json(
        ["api", f"repos/{repository}/commits/{head_sha}/statuses?per_page=100"],
        request_timeout_seconds=request_timeout_seconds,
    )
    if not isinstance(payload, list):
        raise TransientReadError("GitHub API returned an unexpected commit status payload")
    for entry in payload:  # newest first
        if not isinstance(entry, dict) or entry.get("context") != context:
            continue
        creator = entry.get("creator") or {}
        return StatusSnapshot(
            state=str(entry.get("state") or ""),
            description=str(entry.get("description") or ""),
            creator_id=creator.get("id"),
            creator_login=creator.get("login"),
            created_at=str(entry.get("created_at") or ""),
        )
    return None


def is_trusted_creator(status: StatusSnapshot) -> bool:
    return status.creator_id == GITHUB_ACTIONS_BOT_ID or status.creator_login == GITHUB_ACTIONS_BOT_LOGIN


def fetch_base_sha(repository: str, base_ref: str, *, request_timeout_seconds: int) -> str:
    """Read the authoritative branch ref SHA (``refs/heads/main``), not baseRefOid."""
    api_ref = base_ref[len("refs/"):] if base_ref.startswith("refs/") else base_ref
    payload = gh_json(
        ["api", f"repos/{repository}/git/ref/{api_ref}"],
        request_timeout_seconds=request_timeout_seconds,
    )
    if not isinstance(payload, dict):
        raise TransientReadError("GitHub API returned an unexpected base ref payload")
    sha = str((payload.get("object") or {}).get("sha") or "")
    if not SHA_RE.fullmatch(sha):
        raise TransientReadError(f"base ref {base_ref} returned an unexpected SHA: {sha!r}")
    return sha


def _evidence(
    *,
    repository: str,
    pr_number: int,
    pr_url: str,
    expected_head_sha: str,
    observed_head_sha: str,
    context: str,
    base_ref: str,
    base_sha: str,
    outcome: str,
    reason: str,
    waited_seconds: float,
    timeout_seconds: int,
    poll_seconds: int,
    attempts: int,
    history: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA,
        "repository": repository,
        "pull_request": {"number": pr_number, "url": pr_url},
        "expected_head_sha": expected_head_sha,
        "observed_head_sha": observed_head_sha,
        "context": context,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "approved": outcome == OUTCOME_APPROVED,
        "outcome": outcome,
        "reason": reason,
        "waited_seconds": round(waited_seconds, 3),
        "timeout_seconds": timeout_seconds,
        "poll_seconds": poll_seconds,
        "attempts": attempts,
        "status_history": history,
    }


def wait_for_approval(
    *,
    repository: str,
    pr_number: int,
    expected_head_sha: str,
    context: str = STATUS_CONTEXT,
    base_ref: str = DEFAULT_BASE_REF,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    max_consecutive_read_errors: int = DEFAULT_MAX_CONSECUTIVE_READ_ERRORS,
    fetch_pr: Callable[[], PullRequestSnapshot],
    fetch_status: Callable[[], StatusSnapshot | None],
    fetch_base_sha: Callable[[], str],
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Poll until the exact head is approved, or fail closed with evidence."""
    if not SHA_RE.fullmatch(expected_head_sha):
        raise ValueError("expected head must be a 40-character lowercase SHA")
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if poll_seconds <= 0:
        raise ValueError("poll interval must be positive")
    if max_consecutive_read_errors <= 0:
        raise ValueError("max consecutive read errors must be positive")

    clock = clock or _monotonic
    sleep = sleep or _sleep
    log = log or (lambda message: print(message, flush=True))

    started = clock()
    deadline = started + timeout_seconds
    attempts = 0
    consecutive_errors = 0
    base_errors = 0
    history: list[dict[str, object]] = []
    pr_url = ""
    observed_head = ""
    captured_base = ""

    def finish(outcome: str, reason: str) -> dict[str, object]:
        evidence = _evidence(
            repository=repository,
            pr_number=pr_number,
            pr_url=pr_url,
            expected_head_sha=expected_head_sha,
            observed_head_sha=observed_head,
            context=context,
            base_ref=base_ref,
            base_sha=captured_base,
            outcome=outcome,
            reason=reason,
            waited_seconds=clock() - started,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            attempts=attempts,
            history=history,
        )
        log(f"changelog approval wait: outcome={outcome} pr={pr_url or pr_number} "
            f"head={observed_head or expected_head_sha} base={captured_base or '<unread>'} "
            f"reason={reason}")
        return evidence

    def read_failed(what: str, error: Exception) -> dict[str, object] | None:
        nonlocal consecutive_errors
        consecutive_errors += 1
        if consecutive_errors >= max_consecutive_read_errors:
            return finish(
                OUTCOME_UNREADABLE,
                f"could not read the {what} after {consecutive_errors} consecutive attempts: {error}",
            )
        return None

    while True:
        attempts += 1

        try:
            pr = fetch_pr()
        except TransientReadError as error:
            failed = read_failed("pull request", error)
            if failed is not None:
                return failed
            if clock() >= deadline:
                return finish(OUTCOME_TIMEOUT, f"timed out reading the pull request: {error}")
            sleep(min(poll_seconds, max(0.0, deadline - clock())))
            continue

        pr_url = pr.url or pr_url
        observed_head = pr.head_sha or observed_head

        if pr.state != "open":
            return finish(
                OUTCOME_PR_NOT_OPEN,
                f"pull request state is {pr.state!r}, expected 'open'; refusing to merge or tag",
            )
        if pr.base_ref != "main":
            return finish(
                OUTCOME_BASE_CHANGED,
                f"pull request base is {pr.base_ref!r}, expected 'main'",
            )
        if pr.head_sha != expected_head_sha:
            return finish(
                OUTCOME_HEAD_CHANGED,
                f"pull request head is {pr.head_sha or '<unknown>'}, expected {expected_head_sha}",
            )

        try:
            status = fetch_status()
        except TransientReadError as error:
            failed = read_failed("commit status", error)
            if failed is not None:
                return failed
            if clock() >= deadline:
                return finish(OUTCOME_TIMEOUT, f"timed out reading the commit status: {error}")
            sleep(min(poll_seconds, max(0.0, deadline - clock())))
            continue
        # Only a fully successful observation clears the read-error budget.
        consecutive_errors = 0

        if status is None:
            entry = {"at_seconds": round(clock() - started, 3), "state": None,
                     "description": "status not posted yet"}
        else:
            if not is_trusted_creator(status):
                return finish(
                    OUTCOME_UNTRUSTED,
                    f"status {context!r} was posted by creator id={status.creator_id} "
                    f"login={status.creator_login!r}, not GitHub Actions",
                )
            entry = {"at_seconds": round(clock() - started, 3), "state": status.state,
                     "description": status.description, "created_at": status.created_at}
            if status.state == "success":
                if not history or history[-1].get("state") != "success":
                    history.append(entry)
                # Record the authoritative base ref at the moment approval
                # succeeds; the merge step compares every fresh read to it.
                try:
                    base_sha = fetch_base_sha()
                    base_errors = 0
                except TransientReadError as error:
                    base_errors += 1
                    if base_errors >= max_consecutive_read_errors:
                        return finish(
                            OUTCOME_UNREADABLE,
                            f"could not read the base ref after {base_errors} consecutive attempts: {error}",
                        )
                    if clock() >= deadline:
                        return finish(OUTCOME_TIMEOUT, f"timed out reading the base ref: {error}")
                    sleep(min(poll_seconds, max(0.0, deadline - clock())))
                    continue
                if not SHA_RE.fullmatch(base_sha):
                    return finish(
                        OUTCOME_BASE_UNREADABLE,
                        f"base ref {base_ref} returned {base_sha!r}, expected a 40-character SHA",
                    )
                captured_base = base_sha
                return finish(
                    OUTCOME_APPROVED,
                    f"status {context!r} is success on the exact head; "
                    f"base {base_ref} is {base_sha}",
                )
            if status.state in ("failure", "error"):
                history.append(entry)
                return finish(
                    OUTCOME_REJECTED,
                    f"status {context!r} is {status.state!r}: {status.description or 'no description'}",
                )
        if not history or history[-1].get("state") != entry.get("state") \
                or history[-1].get("description") != entry.get("description"):
            history.append(entry)

        if clock() >= deadline:
            last = history[-1] if history else {}
            return finish(
                OUTCOME_TIMEOUT,
                f"status {context!r} did not reach success within {timeout_seconds}s "
                f"(last state={last.get('state')!r}, description={last.get('description')!r})",
            )
        sleep(min(poll_seconds, max(0.0, deadline - clock())))


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="owner/repo")
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--context", default=STATUS_CONTEXT)
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--request-timeout-seconds", type=int, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument(
        "--max-consecutive-read-errors", type=int, default=DEFAULT_MAX_CONSECUTIVE_READ_ERRORS
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)

    if not SHA_RE.fullmatch(args.expected_head_sha):
        parser.error("--expected-head-sha must be a 40-character lowercase SHA")

    evidence = wait_for_approval(
        repository=args.repository,
        pr_number=args.pr_number,
        expected_head_sha=args.expected_head_sha,
        context=args.context,
        base_ref=args.base_ref,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        max_consecutive_read_errors=args.max_consecutive_read_errors,
        fetch_pr=lambda: fetch_pull_request(
            args.repository, args.pr_number,
            request_timeout_seconds=args.request_timeout_seconds,
        ),
        fetch_status=lambda: fetch_status(
            args.repository, args.expected_head_sha, args.context,
            request_timeout_seconds=args.request_timeout_seconds,
        ),
        fetch_base_sha=lambda: fetch_base_sha(
            args.repository, args.base_ref,
            request_timeout_seconds=args.request_timeout_seconds,
        ),
    )
    try:
        write_evidence(args.evidence, evidence)
    except OSError as error:
        print(
            "CHANGELOG_APPROVAL_WAIT_FAILED "
            f"pr={evidence['pull_request']['url'] or args.pr_number} "
            f"head={evidence['expected_head_sha']} "
            f"reason=evidence-unwritable: {error}",
            file=sys.stderr,
        )
        return 1

    if args.github_output:
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as handle:
                handle.write(f"approved={'true' if evidence['approved'] else 'false'}\n")
                handle.write(f"outcome={evidence['outcome']}\n")
                handle.write(f"pr_url={evidence['pull_request']['url']}\n")
                handle.write(f"head_sha={evidence['expected_head_sha']}\n")
                handle.write(f"base_ref={evidence['base_ref']}\n")
                handle.write(f"base_sha={evidence['base_sha']}\n")

    if evidence["approved"]:
        print(
            "CHANGELOG_APPROVAL_WAIT_OK "
            f"pr={evidence['pull_request']['url']} head={evidence['expected_head_sha']} "
            f"base={evidence['base_sha']} waited={evidence['waited_seconds']}s"
        )
        return 0

    print(
        "CHANGELOG_APPROVAL_WAIT_FAILED "
        f"pr={evidence['pull_request']['url'] or args.pr_number} "
        f"head={evidence['observed_head_sha'] or args.expected_head_sha} "
        f"reason={evidence['outcome']}: {evidence['reason']}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
