#!/usr/bin/env python3
"""Fail-closed admission for an exact desktop Beta qualification candidate.

The dispatcher is allowed to request qualification more than once: this check
is the authority that rejects a duplicate only after GitHub has serialized the
workflow and returned the complete exact-candidate run set.  It deliberately
allows a new bounded attempt after an older failed/cancelled run, but never
after an active or successful exact-candidate run.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


QUALIFICATION_WORKFLOW = ".github/workflows/desktop_qualify_beta.yml"
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_EXACT_CANDIDATE_ATTEMPTS = 3
# Attempt-specific job history is authoritative for a rerun. Keep retrieval
# explicitly bounded so hostile/malformed run metadata cannot create unbounded
# GitHub API work before the trusted runner is reached.
MAX_RUN_ATTEMPTS_TO_INSPECT = 10
MAX_ATTEMPT_AUTHORITIES_TO_INSPECT = 30
# GitHub's REST workflow-run state machine. Nonterminal runs have no
# conclusion; completed runs must carry one of these exact REST conclusions.
NONTERMINAL_STATUSES = frozenset({"queued", "in_progress"})
TERMINAL_CONCLUSIONS = frozenset(
    {"action_required", "cancelled", "failure", "neutral", "skipped", "stale", "success", "timed_out"}
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _positive_id(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase 40-character commit SHA")
    return value


def candidate_sha(ref: Any, release_tag: str, annotated_tag: Any | None) -> str:
    """Resolve a lightweight or one-level annotated tag from GitHub API JSON."""
    if not TAG_RE.fullmatch(release_tag):
        raise ValueError("release tag is not an exact macOS candidate tag")
    if not isinstance(ref, dict) or ref.get("ref") != f"refs/tags/{release_tag}":
        raise ValueError("GitHub tag ref is malformed or does not bind the requested tag")
    target = ref.get("object")
    if not isinstance(target, dict):
        raise ValueError("GitHub tag ref is missing its object")
    kind = target.get("type")
    object_sha = _sha(target.get("sha"), "GitHub tag ref object SHA")
    if kind == "commit":
        return object_sha
    if kind != "tag":
        raise ValueError("GitHub tag ref must point to a commit or annotated tag")
    if not isinstance(annotated_tag, dict) or annotated_tag.get("sha") != object_sha:
        raise ValueError("annotated GitHub tag response does not bind the requested tag object")
    nested = annotated_tag.get("object")
    if not isinstance(nested, dict) or nested.get("type") != "commit":
        raise ValueError("annotated GitHub tag must peel directly to a commit")
    return _sha(nested.get("sha"), "annotated GitHub tag commit SHA")


def _workflow_runs(runs_response: Any) -> list[dict[str, Any]]:
    """Normalize every `gh api --paginate --slurp` page, or fail closed.

    The API includes a total_count on every page. Requiring the concatenated
    page length to match it rejects a partial page set, including an accidental
    regression back to the first 100 records only.
    """
    pages = [runs_response] if isinstance(runs_response, dict) else runs_response
    if not isinstance(pages, list) or not pages:
        raise ValueError("GitHub workflow-runs response is malformed")
    total_count: int | None = None
    all_runs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
            raise ValueError(f"GitHub workflow-runs page {page_index} is malformed")
        page_total = page.get("total_count")
        if not isinstance(page_total, int) or isinstance(page_total, bool) or page_total < 0:
            raise ValueError(f"GitHub workflow-runs page {page_index} total_count is malformed")
        if total_count is None:
            total_count = page_total
        elif page_total != total_count:
            raise ValueError("GitHub workflow-runs pagination total_count changed during retrieval")
        for run_index, run in enumerate(page["workflow_runs"]):
            absolute_index = len(all_runs)
            if not isinstance(run, dict):
                raise ValueError(f"GitHub workflow-runs response contains non-object entry {absolute_index}")
            run_id = _positive_id(run.get("id"), f"workflow run {absolute_index} id")
            if run_id in seen_ids:
                raise ValueError(f"GitHub workflow-runs response contains duplicate run id {run_id}")
            seen_ids.add(run_id)
            run_attempt = _positive_id(run.get("run_attempt"), f"workflow run {absolute_index} run_attempt")
            if run_attempt > MAX_RUN_ATTEMPTS_TO_INSPECT:
                raise ValueError(f"workflow run {absolute_index} run_attempt exceeds the bounded admission limit")
            _validate_workflow_run_state(run, absolute_index)
            all_runs.append(run)
    if total_count != len(all_runs):
        raise ValueError("GitHub workflow-runs pagination is incomplete")
    return all_runs


def _validate_workflow_run_state(run: dict[str, Any], index: int) -> None:
    """Reject incomplete or impossible GitHub workflow-run states before use."""
    status = run.get("status")
    conclusion = run.get("conclusion")
    if not isinstance(status, str):
        raise ValueError(f"workflow run {index} has unknown status")
    if status in NONTERMINAL_STATUSES:
        if conclusion is not None:
            raise ValueError(f"workflow run {index} nonterminal status must have null conclusion")
        return
    if status == "completed":
        if not isinstance(conclusion, str) or conclusion not in TERMINAL_CONCLUSIONS:
            raise ValueError(f"workflow run {index} completed status has invalid conclusion")
        return
    raise ValueError(f"workflow run {index} has unknown status")


def _exact_runs(runs: list[dict[str, Any]], release_tag: str, source_sha: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ValueError(f"GitHub workflow-runs response contains non-object entry {index}")
        # These are core fields on every actions workflow-run response. Reject
        # malformed data instead of treating it as evidence that no run exists.
        _positive_id(run.get("id"), f"workflow run {index} id")
        for field in ("path", "event", "head_branch", "head_sha", "status"):
            if not isinstance(run.get(field), str):
                raise ValueError(f"workflow run {index} {field} is malformed")
        if (
            run["path"] == QUALIFICATION_WORKFLOW
            and run["event"] == "workflow_dispatch"
            and run["head_branch"] == release_tag
            and run["head_sha"] == source_sha
        ):
            selected.append(run)
    return selected


def _qualification_attempts(prior_runs: list[dict[str, Any]], jobs_by_run: dict[int, dict[int, Any]]) -> int:
    """Count started trusted jobs across immutable GitHub run attempts."""
    expected = {(run["id"], attempt) for run in prior_runs for attempt in range(1, run["run_attempt"] + 1)}
    if len(expected) > MAX_ATTEMPT_AUTHORITIES_TO_INSPECT:
        raise ValueError("exact candidate run attempts exceed the bounded admission limit")
    actual: set[tuple[int, int]] = set()
    for run_id, attempt_responses in jobs_by_run.items():
        _positive_id(run_id, "workflow run id in attempt job authority")
        if not isinstance(attempt_responses, dict):
            raise ValueError(f"workflow run {run_id} attempt job authority is malformed")
        for attempt in attempt_responses:
            _positive_id(attempt, f"workflow run {run_id} attempt in job authority")
            actual.add((run_id, attempt))
    if actual != expected:
        missing = sorted(expected.difference(actual))
        extra = sorted(actual.difference(expected))
        raise ValueError(f"GitHub attempt job authority is incomplete or inconsistent (missing={missing}, extra={extra})")
    return sum(
        _qualify_job_started(jobs_by_run[run_id][attempt], run_id, attempt)
        for run_id, attempt in sorted(expected)
    )


def _qualify_job_started(jobs_response: Any, run_id: int, attempt: int) -> bool:
    pages = [jobs_response] if isinstance(jobs_response, dict) else jobs_response
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"workflow run {run_id} attempt {attempt} jobs response is malformed")
    total_count: int | None = None
    jobs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict) or not isinstance(page.get("jobs"), list):
            raise ValueError(f"workflow run {run_id} attempt {attempt} jobs page {page_index} is malformed")
        page_total = page.get("total_count")
        if not isinstance(page_total, int) or isinstance(page_total, bool) or page_total < 0:
            raise ValueError(f"workflow run {run_id} attempt {attempt} jobs page {page_index} total_count is malformed")
        if total_count is None:
            total_count = page_total
        elif page_total != total_count:
            raise ValueError(f"workflow run {run_id} attempt {attempt} jobs pagination total_count changed during retrieval")
        for job in page["jobs"]:
            if not isinstance(job, dict):
                raise ValueError(f"workflow run {run_id} attempt {attempt} jobs response contains a non-object entry")
            job_id = _positive_id(job.get("id"), f"workflow run {run_id} attempt {attempt} job id")
            if job_id in seen_ids:
                raise ValueError(f"workflow run {run_id} attempt {attempt} jobs response contains duplicate job id {job_id}")
            seen_ids.add(job_id)
            jobs.append(job)
    if total_count != len(jobs):
        raise ValueError(f"workflow run {run_id} attempt {attempt} jobs pagination is incomplete")
    qualify_jobs = [job for job in jobs if job.get("name") == "qualify"]
    if len(qualify_jobs) > 1:
        raise ValueError(f"workflow run {run_id} attempt {attempt} has multiple qualify jobs")
    if not qualify_jobs:
        # A cancelled workflow can be discarded by global concurrency before
        # it creates the trusted qualification job. It is not an attempt.
        return False
    qualify = qualify_jobs[0]
    if qualify.get("status") != "completed":
        raise ValueError(f"workflow run {run_id} attempt {attempt} qualify job did not complete")
    conclusion = qualify.get("conclusion")
    if not isinstance(conclusion, str) or conclusion not in TERMINAL_CONCLUSIONS:
        raise ValueError(f"workflow run {run_id} attempt {attempt} qualify job has invalid conclusion")
    if conclusion == "skipped":
        return False
    started_at = qualify.get("started_at")
    if started_at is None and conclusion == "cancelled":
        return False
    if not isinstance(started_at, str) or not started_at:
        raise ValueError(f"workflow run {run_id} attempt {attempt} qualify job did not prove it started")
    return True


def decide(
    ref: Any,
    runs_response: Any,
    *,
    release_tag: str,
    jobs_by_run: dict[int, dict[int, Any]],
    current_run_id: int | None = None,
    annotated_tag: Any | None = None,
) -> dict[str, Any]:
    """Return an admission decision or raise for malformed GitHub API data."""
    source_sha = candidate_sha(ref, release_tag, annotated_tag)
    runs = _workflow_runs(runs_response)
    if current_run_id is not None:
        current_run_id = _positive_id(current_run_id, "current workflow run id")
        current_runs = [run for run in runs if run["id"] == current_run_id]
        if len(current_runs) != 1:
            raise ValueError("current workflow run must appear exactly once in the GitHub run response")
        current = current_runs[0]
        if not (
            current.get("path") == QUALIFICATION_WORKFLOW
            and current.get("event") == "workflow_dispatch"
            and current.get("head_branch") == release_tag
            and current.get("head_sha") == source_sha
        ):
            raise ValueError("current workflow run does not bind the requested immutable candidate")
        if current["run_attempt"] != 1:
            raise ValueError("workflow reruns are not admitted; dispatch a fresh immutable workflow run")
    prior_runs = [run for run in _exact_runs(runs, release_tag, source_sha) if run["id"] != current_run_id]
    active = next((run for run in prior_runs if run["status"] != "completed"), None)
    if active is not None:
        return {
            "admitted": False,
            "release_tag": release_tag,
            "source_sha": source_sha,
            "reason": f"exact candidate already has active qualification run {active['id']}",
        }
    successful = next((run for run in prior_runs if run["conclusion"] == "success"), None)
    if successful is not None:
        return {
            "admitted": False,
            "release_tag": release_tag,
            "source_sha": source_sha,
            "reason": f"exact candidate already succeeded in qualification run {successful['id']}",
        }
    attempts = _qualification_attempts(prior_runs, jobs_by_run)
    if attempts >= MAX_EXACT_CANDIDATE_ATTEMPTS:
        return {
            "admitted": False,
            "release_tag": release_tag,
            "source_sha": source_sha,
            "reason": (
                f"exact candidate has reached the {MAX_EXACT_CANDIDATE_ATTEMPTS}-attempt qualification bound"
            ),
        }
    return {
        "admitted": True,
        "release_tag": release_tag,
        "source_sha": source_sha,
        "reason": "no active or successful prior exact-candidate qualification run",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-json", type=Path, required=True)
    parser.add_argument("--annotated-tag-json", type=Path)
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--current-run-id", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-admitted", action="store_true")
    args = parser.parse_args()

    jobs_by_run: dict[int, dict[int, Any]] = {}
    for run_directory in args.jobs_dir.iterdir():
        try:
            if not run_directory.is_dir():
                raise ValueError("attempt authority entry is not a directory")
            run_id = _positive_id(int(run_directory.name), "workflow run id from jobs directory")
        except ValueError as exc:
            raise ValueError(f"jobs directory has invalid run entry {run_directory.name!r}") from exc
        attempts: dict[int, Any] = {}
        for path in run_directory.iterdir():
            try:
                if not path.is_file() or path.suffix != ".json":
                    raise ValueError("attempt authority entry is not a JSON file")
                attempt = _positive_id(int(path.stem), "workflow run attempt from jobs filename")
            except ValueError as exc:
                raise ValueError(f"jobs directory has invalid attempt entry {path.name!r}") from exc
            if attempt in attempts:
                raise ValueError(f"jobs directory has duplicate authority for workflow run {run_id} attempt {attempt}")
            attempts[attempt] = _load(path)
        jobs_by_run[run_id] = attempts
    decision = decide(
        _load(args.ref_json),
        _load(args.runs_json),
        release_tag=args.release_tag,
        jobs_by_run=jobs_by_run,
        current_run_id=args.current_run_id,
        annotated_tag=_load(args.annotated_tag_json) if args.annotated_tag_json else None,
    )
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(decision["reason"])
    return 0 if decision["admitted"] or not args.require_admitted else 1


if __name__ == "__main__":
    raise SystemExit(main())
