#!/usr/bin/env python3
"""Decide whether to retry the newest desktop Beta candidate qualification.

The retry only recovers a *transient* failed/cancelled qualification of the
newest valid immutable published candidate. It never trusts a caller claim: the
candidate identity, qualification run set, and conclusion are all re-derived
from server-provided JSON (a GitHub release view and the qualification workflow
run list). On schedule the workflow supplies no tag at all.

Safety properties enforced here:
- tag-bound and exact-SHA: only the exact newest tag at its exact SHA is retried;
- newest valid candidate only: a published, non-draft, non-prerelease candidate
  carrying the canonical three assets and an isLive:false candidate body;
- bounded candidate age and bounded attempts;
- never retry an in-progress or already-successful run;
- bounded attempts keep a deterministic product failure from looping forever.
  (We do not classify transient vs deterministic from logs: a failed
  qualification step can be either, and the attempt bound is the safe loop guard.
  Mis-classifying a transient failure as deterministic would strand the newest
  candidate; bounded retries cannot.)
- promotion stays a separate completed-success authority: this only re-dispatches
  qualification, never the promote endpoint.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QUALIFICATION_WORKFLOW = ".github/workflows/desktop_qualify_beta.yml"
# The three immutable assets Codemagic attaches to every canonical candidate.
CANONICAL_ASSETS = ("Omi.zip", "omi.dmg", "desktop-smoke-result.json")
# A terminal qualification conclusion a transient retry may recover. "neutral"
# and "skipped" are excluded: they are operator/policy outcomes, not transient.
RETRYABLE_CONCLUSIONS = frozenset({"failure", "cancelled", "timed_out", "startup_failure"})
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_AGE_HOURS = 24
TRUE_VALUES = {"true", "1", "yes"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_metadata(body: str) -> dict[str, str]:
    """Read the KEY_VALUE block Codemagic writes into the release body.

    Mirrors desktop_release_metadata.parse_metadata but denies (returns {})
    instead of exiting when the block is absent: a retry decision is never a
    hard failure, only a "no" with a reason.
    """
    result: dict[str, str] = {}
    if "KEY_VALUE_START" not in body or "KEY_VALUE_END" not in body:
        return result
    block = body.split("KEY_VALUE_START", 1)[1].split("KEY_VALUE_END", 1)[0]
    for line in block.strip().splitlines():
        line = line.strip()
        if line.startswith("<!--"):
            line = line[4:].strip()
        if line.endswith("-->"):
            line = line[:-3].strip()
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _valid_candidate(release: Any, release_tag: str) -> tuple[bool, str]:
    """Validate the newest published candidate carries the canonical assets."""
    if not isinstance(release, dict) or not release:
        return False, "no published GitHub release for the newest tag"
    if release.get("tagName") != release_tag:
        return False, "release tag does not match the newest candidate tag"
    if release.get("isDraft") or release.get("isPrerelease"):
        return False, "newest candidate is a draft or prerelease"
    if not release.get("publishedAt"):
        return False, "newest candidate is not published"
    metadata = _parse_metadata(release.get("body") or "")
    if metadata.get("channel") != "candidate":
        return False, "newest candidate is not channel: candidate"
    if metadata.get("isLive", "").lower() not in {"false", "0", "no"}:
        return False, "newest candidate is not isLive: false"
    asset_names = {a.get("name") for a in release.get("assets", []) if isinstance(a, dict)}
    missing = [name for name in CANONICAL_ASSETS if name not in asset_names]
    if missing:
        return False, f"newest candidate is missing canonical assets: {', '.join(missing)}"
    return True, "newest candidate carries the canonical three assets"


def _candidate_age_hours(release: Any) -> int | None:
    published = release.get("publishedAt") if isinstance(release, dict) else None
    if not isinstance(published, str) or not published:
        return None
    try:
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - published_at).total_seconds() // 3600))


def _runs_for_tag(runs: Any, release_tag: str, tag_sha: str) -> list[dict[str, Any]]:
    """Select qualification runs bound to the exact candidate tag and SHA."""
    selected: list[dict[str, Any]] = []
    if not isinstance(runs, list):
        return selected
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("path") != QUALIFICATION_WORKFLOW:
            continue
        if run.get("event") != "workflow_dispatch":
            continue
        if run.get("head_branch") != release_tag:
            continue
        if tag_sha and run.get("head_sha") != tag_sha:
            continue
        selected.append(run)
    return selected


def _newest(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not runs:
        return None
    return max(runs, key=lambda r: r.get("updated_at") or r.get("created_at") or "")


def _count_terminal(selected: list[dict[str, Any]]) -> int:
    return sum(
        1
        for r in selected
        if r.get("status") == "completed" and r.get("conclusion") in RETRYABLE_CONCLUSIONS
    )


def _decision(
    *,
    release_tag: str,
    should_retry: bool,
    reason: str,
    attempts: int,
    newest: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "should_retry": should_retry,
        "release_tag": release_tag,
        "reason": reason,
        "attempts_so_far": attempts,
        "newest_run_status": newest.get("status") if newest else None,
        "newest_run_conclusion": newest.get("conclusion") if newest else None,
        "newest_run_id": newest.get("id") if newest else None,
    }


def decide(
    release: Any,
    runs: Any,
    *,
    release_tag: str,
    tag_sha: str,
    max_attempts: int,
    max_age_hours: int,
) -> dict[str, Any]:
    valid, candidate_reason = _valid_candidate(release, release_tag)
    selected = _runs_for_tag(runs, release_tag, tag_sha) if valid else []
    attempts = _count_terminal(selected)

    if not valid:
        return _decision(
            release_tag=release_tag, should_retry=False, reason=candidate_reason, attempts=attempts, newest=None
        )

    age = _candidate_age_hours(release)
    if age is not None and age > max_age_hours:
        return _decision(
            release_tag=release_tag,
            should_retry=False,
            reason=f"candidate age {age}h exceeds {max_age_hours}h bound",
            attempts=attempts,
            newest=_newest(selected),
        )

    newest = _newest(selected)
    if newest is None:
        return _decision(
            release_tag=release_tag,
            should_retry=False,
            reason="no prior qualification attempt; not retrying an unattempted candidate",
            attempts=attempts,
            newest=None,
        )

    status = newest.get("status")
    conclusion = newest.get("conclusion")
    if status != "completed":
        return _decision(
            release_tag=release_tag,
            should_retry=False,
            reason=f"qualification is {status}; never retry an in-progress run",
            attempts=attempts,
            newest=newest,
        )
    if conclusion == "success":
        return _decision(
            release_tag=release_tag,
            should_retry=False,
            reason="qualification already succeeded; promotion is a separate completed-success authority",
            attempts=attempts,
            newest=newest,
        )
    if attempts >= max_attempts:
        return _decision(
            release_tag=release_tag,
            should_retry=False,
            reason=(
                f"{attempts} failed attempts reached the {max_attempts} bound; "
                "deterministic or persistent failure, not retrying"
            ),
            attempts=attempts,
            newest=newest,
        )
    if conclusion not in RETRYABLE_CONCLUSIONS:
        return _decision(
            release_tag=release_tag,
            should_retry=False,
            reason=f"conclusion {conclusion!r} is not a transient retryable state",
            attempts=attempts,
            newest=newest,
        )

    return _decision(
        release_tag=release_tag,
        should_retry=True,
        reason=f"retrying transient {conclusion} qualification (attempt {attempts + 1} of {max_attempts})",
        attempts=attempts,
        newest=newest,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["decide"])
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--tag-sha", required=True)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    decision = decide(
        _load(args.release_json),
        _load(args.runs_json),
        release_tag=args.release_tag,
        tag_sha=args.tag_sha,
        max_attempts=args.max_attempts,
        max_age_hours=args.max_age_hours,
    )
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(decision["reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
