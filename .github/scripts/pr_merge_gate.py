#!/usr/bin/env python3
"""Publish one fail-closed merge verdict for the exact live PR head.

This controller runs only from the trusted default branch under
``pull_request_target`` or ``workflow_run``. It observes GitHub Actions
metadata; it never checks out, downloads, imports, or executes
pull-request-controlled content.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Callable, Iterable


STATUS_CONTEXT = "Omi Merge Gate"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PASSING_CONCLUSIONS = {"success"}
FAILING_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "startup_failure",
    "timed_out",
}
INCOMPLETE_STATUSES = {"expected", "pending", "queued", "in_progress", "requested", "waiting"}
MAX_PR_FILES = 3000


@dataclass(frozen=True)
class WorkflowSpec:
    path: str
    classification: str
    reason: str
    paths: tuple[str, ...] = ()
    authoritative_job: str | None = None
    selector_job: str | None = None
    event_selector_jobs: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorkflowSpec":
        event_jobs = raw.get("event_selector_jobs", {})
        if not isinstance(event_jobs, dict):
            raise ValueError(f"{raw.get('path', '<unknown>')}: event_selector_jobs must be an object")
        return cls(
            path=str(raw.get("path", "")),
            classification=str(raw.get("classification", "")),
            reason=str(raw.get("reason", "")),
            paths=tuple(str(item) for item in raw.get("paths", [])),
            authoritative_job=raw.get("authoritative_job"),
            selector_job=raw.get("selector_job"),
            event_selector_jobs=tuple(sorted((str(action), str(job)) for action, job in event_jobs.items())),
        )


@dataclass(frozen=True)
class Evaluation:
    state: str
    description: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventContext:
    pr_number: int
    action: str
    not_before: str
    expected_head_sha: str
    trigger_run_id: int = 0


def load_manifest(path: Path) -> tuple[WorkflowSpec, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("workflows"), list):
        raise ValueError("merge-gate manifest must have version 1 and a workflows list")
    specs = tuple(WorkflowSpec.from_dict(item) for item in raw["workflows"])
    paths = [spec.path for spec in specs]
    if any(not path.startswith(".github/workflows/") for path in paths):
        raise ValueError("every merge-gate workflow path must be under .github/workflows")
    if len(paths) != len(set(paths)):
        raise ValueError("merge-gate workflow paths must be unique")
    for spec in specs:
        if spec.classification not in {"required", "advisory", "ignored"}:
            raise ValueError(f"{spec.path}: invalid classification {spec.classification!r}")
        if not spec.reason:
            raise ValueError(f"{spec.path}: reason is required")
        if spec.classification != "required" and (
            spec.paths or spec.authoritative_job or spec.selector_job or spec.event_selector_jobs
        ):
            raise ValueError(f"{spec.path}: non-required workflows cannot carry gate selectors")
        if spec.authoritative_job and spec.selector_job:
            raise ValueError(f"{spec.path}: authoritative_job and selector_job are mutually exclusive")
    return specs


def trigger_matches(pattern: str, path: str) -> bool:
    """Match the GitHub path-filter subset used by this repository."""
    if pattern.endswith("/**") and path.startswith(pattern[:-3].rstrip("/") + "/"):
        return True
    if fnmatch.fnmatchcase(path, pattern) or PurePath(path).match(pattern):
        return True
    if "/**/" in pattern and fnmatch.fnmatchcase(path, pattern.replace("/**/", "/")):
        return True
    return False


def applies(spec: WorkflowSpec, changed_files: Iterable[str]) -> bool:
    return not spec.paths or any(trigger_matches(pattern, path) for pattern in spec.paths for path in changed_files)


def normalized_workflow_path(path: str) -> str:
    return path.split("@", 1)[0]


def _run_key(run: dict[str, Any]) -> tuple[str, int, int]:
    return (str(run.get("created_at", "")), int(run.get("id", 0)), int(run.get("run_attempt", 0)))


def _job_key(job: dict[str, Any]) -> tuple[str, int]:
    return (str(job.get("started_at", "")), int(job.get("id", 0)))


def _result_for(conclusion: Any, status: Any, label: str) -> Evaluation:
    normalized_status = str(status or "").lower()
    normalized_conclusion = str(conclusion or "").lower()
    if normalized_status != "completed" or not normalized_conclusion:
        if normalized_status in INCOMPLETE_STATUSES or not normalized_conclusion:
            return Evaluation("pending", f"Waiting for {label}", (label,))
        return Evaluation("error", f"Unknown status for {label}: {normalized_status or '<empty>'}", (label,))
    if normalized_conclusion in PASSING_CONCLUSIONS:
        return Evaluation("success", f"{label} passed")
    if normalized_conclusion in FAILING_CONCLUSIONS:
        return Evaluation("failure", f"{label} concluded {normalized_conclusion}", (label,))
    return Evaluation("error", f"Unknown conclusion for {label}: {normalized_conclusion}", (label,))


def _latest_run_with_job(
    runs: list[dict[str, Any]],
    jobs_by_run: dict[int, list[dict[str, Any]]],
    job_name: str,
    *,
    not_before: str = "",
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    eligible = [run for run in runs if str(run.get("created_at", "")) >= not_before]
    for run in sorted(eligible, key=_run_key, reverse=True):
        matches = [job for job in jobs_by_run.get(int(run["id"]), []) if job.get("name") == job_name]
        if matches:
            return run, max(matches, key=_job_key)
    return None


def evaluate(
    specs: Iterable[WorkflowSpec],
    changed_files: Iterable[str],
    runs: Iterable[dict[str, Any]],
    jobs_by_run: dict[int, list[dict[str, Any]]],
    *,
    event_action: str = "",
    event_not_before: str = "",
) -> Evaluation:
    """Return a pure aggregate verdict over already-fetched exact-head data."""
    changed = tuple(changed_files)
    runs_by_path: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        if run.get("event") != "pull_request":
            continue
        runs_by_path.setdefault(normalized_workflow_path(str(run.get("path", ""))), []).append(run)

    failures: list[str] = []
    errors: list[str] = []
    pending: list[str] = []
    applicable_count = 0

    def collect(result: Evaluation) -> None:
        if result.state == "failure":
            failures.extend(result.blockers)
        elif result.state == "error":
            errors.extend(result.blockers)
        elif result.state == "pending":
            pending.extend(result.blockers)

    for spec in specs:
        if spec.classification != "required" or not applies(spec, changed):
            continue
        applicable_count += 1
        candidates = runs_by_path.get(spec.path, [])
        label = Path(spec.path).name
        if not candidates:
            pending.append(label)
            continue

        if spec.authoritative_job:
            latest = max(candidates, key=_run_key)
            jobs = [job for job in jobs_by_run.get(int(latest["id"]), []) if job.get("name") == spec.authoritative_job]
            if not jobs:
                if latest.get("status") == "completed":
                    errors.append(f"{label}:{spec.authoritative_job} missing")
                else:
                    pending.append(f"{label}:{spec.authoritative_job}")
            else:
                job = max(jobs, key=_job_key)
                collect(_result_for(job.get("conclusion"), job.get("status"), f"{label}:{spec.authoritative_job}"))
        elif spec.selector_job:
            selected = _latest_run_with_job(candidates, jobs_by_run, spec.selector_job)
            if selected is None:
                if any(run.get("status") != "completed" for run in candidates):
                    pending.append(f"{label}:{spec.selector_job}")
                else:
                    errors.append(f"{label}:{spec.selector_job} lane missing")
            else:
                run, _job = selected
                collect(_result_for(run.get("conclusion"), run.get("status"), f"{label}:{spec.selector_job} lane"))
        else:
            latest = max(candidates, key=_run_key)
            collect(_result_for(latest.get("conclusion"), latest.get("status"), label))

        for action, selector_job in spec.event_selector_jobs:
            if action != event_action and event_action != "reconcile":
                continue
            selected = _latest_run_with_job(
                candidates,
                jobs_by_run,
                selector_job,
                not_before=event_not_before if action == event_action else "",
            )
            if selected is None:
                if event_action == "reconcile":
                    # A reconciliation may have been triggered by a code lane on
                    # a SHA that has never had this metadata lane. There is no
                    # metadata evidence to require in that case.
                    continue
                current_event_runs = [run for run in candidates if str(run.get("created_at", "")) >= event_not_before]
                if any(run.get("status") != "completed" for run in current_event_runs):
                    pending.append(f"{label}:{selector_job}")
                else:
                    errors.append(f"{label}:{selector_job} lane missing")
            else:
                run, _job = selected
                collect(_result_for(run.get("conclusion"), run.get("status"), f"{label}:{selector_job} lane"))

    if failures:
        first = ", ".join(failures[:3])
        return Evaluation("failure", f"Required CI failed: {first}"[:140], tuple(failures))
    if errors:
        first = ", ".join(errors[:3])
        return Evaluation("error", f"Merge-gate evidence error: {first}"[:140], tuple(errors))
    if pending:
        first = ", ".join(pending[:3])
        return Evaluation("pending", f"Waiting for required CI: {first}"[:140], tuple(pending))
    return Evaluation("success", f"All {applicable_count} applicable CI workflows passed")


class GitHubClient:
    def __init__(self, repository: str, token: str) -> None:
        if not REPOSITORY_RE.fullmatch(repository):
            raise ValueError(f"invalid repository: {repository!r}")
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self.repository = repository
        self.token = token
        self.api_root = f"https://api.github.com/repos/{repository}"

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.api_root}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "omi-exact-head-merge-gate",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {detail}") from exc

    def paged(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        separator = "&" if "?" in path else "?"
        collected: list[dict[str, Any]] = []
        for page in range(1, 101):
            payload = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            items = payload[key] if key else payload
            if not isinstance(items, list):
                raise RuntimeError(f"GitHub API pagination returned a non-list for {path}")
            collected.extend(items)
            if len(items) < 100:
                return collected
        raise RuntimeError(f"GitHub API pagination exceeded 10,000 records for {path}")

    def pull_request(self, number: int) -> dict[str, Any]:
        return self.request("GET", f"/pulls/{number}")

    def changed_files(self, number: int) -> list[str]:
        files = self.paged(f"/pulls/{number}/files")
        if len(files) >= MAX_PR_FILES:
            raise RuntimeError(
                "GitHub's pull-request files API is capped at 3,000 files; "
                "cannot prove path-filter completeness, so the merge gate fails closed"
            )
        return [str(item["filename"]) for item in files]

    def pull_requests_for_commit(self, sha: str) -> list[dict[str, Any]]:
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f"invalid commit SHA: {sha!r}")
        return self.paged(f"/commits/{sha}/pulls")

    def workflow_runs(self, sha: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"event": "pull_request", "head_sha": sha})
        return self.paged(f"/actions/runs?{query}", "workflow_runs")

    def jobs(self, run_id: int) -> list[dict[str, Any]]:
        return self.paged(f"/actions/runs/{run_id}/jobs?filter=latest", "jobs")

    def post_status(self, sha: str, state: str, description: str, target_url: str) -> None:
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f"invalid target SHA: {sha!r}")
        self.request(
            "POST",
            f"/statuses/{sha}",
            {"state": state, "context": STATUS_CONTEXT, "description": description[:140], "target_url": target_url},
        )


def _head_sha(pr: dict[str, Any]) -> str:
    sha = str(pr.get("head", {}).get("sha", ""))
    if not SHA_RE.fullmatch(sha):
        raise RuntimeError(f"pull request returned invalid head SHA: {sha!r}")
    return sha


def resolve_event_context(client: GitHubClient, payload: dict[str, Any]) -> EventContext | None:
    """Resolve a trusted PR event or workflow-run event to one exact open PR."""
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        number = int(pull_request.get("number") or payload.get("number") or 0)
        if number <= 0:
            raise RuntimeError("pull_request event did not contain a valid PR number")
        return EventContext(
            number,
            str(payload.get("action", "")),
            str(pull_request.get("updated_at", "")),
            _head_sha(pull_request),
        )

    workflow_run = payload.get("workflow_run")
    if not isinstance(workflow_run, dict) or workflow_run.get("event") != "pull_request":
        raise RuntimeError("event payload is neither a PR event nor a PR workflow-run event")
    sha = str(workflow_run.get("head_sha", ""))
    if not SHA_RE.fullmatch(sha):
        raise RuntimeError(f"workflow_run event returned invalid head SHA: {sha!r}")
    associated = client.pull_requests_for_commit(sha)
    exact = [
        pr
        for pr in associated
        if str(pr.get("head", {}).get("sha", "")) == sha
        and str(pr.get("base", {}).get("ref", "")) == "main"
        and str(pr.get("base", {}).get("repo", {}).get("full_name", client.repository)) == client.repository
    ]
    open_exact = [pr for pr in exact if pr.get("state") == "open"]
    if len(open_exact) == 1:
        number = int(open_exact[0].get("number", 0))
        if number <= 0:
            raise RuntimeError("associated open PR did not contain a valid number")
        return EventContext(number, "reconcile", "", sha, int(workflow_run.get("id", 0)))
    if not open_exact and exact:
        # The PR merged or closed before its workflow-run event arrived. A
        # reopened PR gets a fresh pull_request_target event, so no status is
        # needed on the now-closed PR.
        return None
    raise RuntimeError(f"workflow run {workflow_run.get('id')} maps to {len(open_exact)} exact open PRs")


def _job_run_ids(
    specs: Iterable[WorkflowSpec], changed_files: Iterable[str], runs: Iterable[dict[str, Any]]
) -> set[int]:
    applicable_paths = {
        spec.path
        for spec in specs
        if spec.classification == "required"
        and applies(spec, changed_files)
        and (spec.authoritative_job or spec.selector_job or spec.event_selector_jobs)
    }
    return {
        int(run["id"])
        for run in runs
        if run.get("event") == "pull_request" and normalized_workflow_path(str(run.get("path", ""))) in applicable_paths
    }


def publish_if_current(
    client: GitHubClient, pr_number: int, target_sha: str, result: Evaluation, target_url: str
) -> bool:
    """Publish only to the SHA this controller originally evaluated."""
    if _head_sha(client.pull_request(pr_number)) != target_sha:
        print(f"PR head changed; refusing to publish {result.state} for superseded {target_sha}")
        return False
    client.post_status(target_sha, result.state, result.description, target_url)
    return True


def run_gate(
    client: GitHubClient,
    specs: tuple[WorkflowSpec, ...],
    pr_number: int,
    event_action: str,
    event_not_before: str,
    target_url: str,
    timeout_seconds: int,
    poll_seconds: int,
    *,
    expected_head_sha: str = "",
    trigger_run_id: int = 0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Evaluation:
    target_sha = _head_sha(client.pull_request(pr_number))
    if expected_head_sha:
        if not SHA_RE.fullmatch(expected_head_sha):
            raise ValueError(f"invalid expected head SHA: {expected_head_sha!r}")
        if expected_head_sha != target_sha:
            return Evaluation("pending", f"Ignoring superseded workflow evidence for {expected_head_sha[:12]}")
    changed = client.changed_files(pr_number)
    client.post_status(target_sha, "pending", "Waiting for exact-head required CI", target_url)
    deadline = monotonic() + timeout_seconds
    completed_job_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}

    while True:
        if _head_sha(client.pull_request(pr_number)) != target_sha:
            return Evaluation("pending", f"Superseded by a newer PR head than {target_sha[:12]}")
        runs = client.workflow_runs(target_sha)
        by_id = {int(run["id"]): run for run in runs}
        jobs_by_run: dict[int, list[dict[str, Any]]] = {}
        for run_id in _job_run_ids(specs, changed, runs):
            run = by_id[run_id]
            cache_key = (run_id, int(run.get("run_attempt", 0)))
            if run.get("status") == "completed" and cache_key in completed_job_cache:
                jobs_by_run[run_id] = completed_job_cache[cache_key]
                continue
            jobs_by_run[run_id] = client.jobs(run_id)
            if run.get("status") == "completed":
                completed_job_cache[cache_key] = jobs_by_run[run_id]
        trigger_run = by_id.get(trigger_run_id) if trigger_run_id else None
        if trigger_run_id and (trigger_run is None or trigger_run.get("status") != "completed"):
            result = Evaluation("pending", "Waiting for the workflow that triggered reconciliation")
        else:
            result = evaluate(
                specs,
                changed,
                runs,
                jobs_by_run,
                event_action=event_action,
                event_not_before=event_not_before,
            )
        if result.state != "pending":
            publish_if_current(client, pr_number, target_sha, result, target_url)
            return result
        if monotonic() >= deadline:
            timed_out = Evaluation("error", f"Timed out: {result.description}"[:140], result.blockers)
            publish_if_current(client, pr_number, target_sha, timed_out, target_url)
            return timed_out
        sleep(poll_seconds)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument("--event-file", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--event-action", default="")
    parser.add_argument("--event-not-before", default="")
    parser.add_argument("--expected-head-sha", default="")
    parser.add_argument("--trigger-run-id", type=int, default=0)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    parser.add_argument("--poll-seconds", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.event_file and args.pr_number <= 0:
        raise SystemExit("--pr-number must be positive")
    if args.timeout_seconds <= 0 or args.poll_seconds <= 0:
        raise SystemExit("poll and timeout values must be positive")
    client = GitHubClient(args.repository, os.environ.get("GITHUB_TOKEN", ""))
    if args.event_file:
        payload = json.loads(args.event_file.read_text(encoding="utf-8"))
        try:
            context = resolve_event_context(client, payload)
        except RuntimeError as exc:
            workflow_run = payload.get("workflow_run", {})
            sha = str(workflow_run.get("head_sha", "")) if isinstance(workflow_run, dict) else ""
            if SHA_RE.fullmatch(sha):
                client.post_status(sha, "error", f"Merge-gate event resolution failed: {exc}", args.target_url)
            raise
        if context is None:
            print(json.dumps({"state": "closed", "description": "Associated PR is no longer open"}))
            return 0
        pr_number = context.pr_number
        event_action = context.action
        event_not_before = context.not_before
        expected_head_sha = context.expected_head_sha
        trigger_run_id = context.trigger_run_id
    else:
        pr_number = args.pr_number
        event_action = args.event_action
        event_not_before = args.event_not_before
        expected_head_sha = args.expected_head_sha
        trigger_run_id = args.trigger_run_id
    if pr_number <= 0:
        raise RuntimeError("resolved PR number must be positive")
    result = run_gate(
        client,
        load_manifest(args.manifest),
        pr_number,
        event_action,
        event_not_before,
        args.target_url,
        args.timeout_seconds,
        args.poll_seconds,
        expected_head_sha=expected_head_sha,
        trigger_run_id=trigger_run_id,
    )
    print(json.dumps({"state": result.state, "description": result.description, "blockers": result.blockers}))
    return 0 if result.state in {"success", "pending"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
