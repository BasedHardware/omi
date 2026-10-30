#!/usr/bin/env python3
"""Bounded weekly GitHub Actions PR-job sample and budget alert.

At most 24 workflow-list calls, 144 job-list calls, and two issue calls.
Only GITHUB_TOKEN is read; no personal token or historical backfill is used.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TITLE = "Weekly CI budget audit"
MAX_WORKFLOWS = 20
DAYS = 7
MAX_CALLS = 282


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Github:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token
        self.calls = 0

    def request(self, method: str, path: str, body: dict | None = None):
        self.calls += 1
        if self.calls > MAX_CALLS:
            raise RuntimeError(f"GitHub API call cap {MAX_CALLS} exceeded")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            "https://api.github.com" + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)


def summarize(budget: dict, samples: list[dict], now: datetime) -> dict:
    durations = defaultdict(list)
    signals = defaultdict(list)
    for item in samples:
        workflow = item["workflow"]
        run = item["run"]
        jobs = item["jobs"]
        completed = []
        for job in jobs:
            if job.get("conclusion") in (None, "skipped") or not job.get("started_at") or not job.get("completed_at"):
                continue
            minutes = (timestamp(job["completed_at"]) - timestamp(job["started_at"])).total_seconds() / 60
            if minutes <= 0:
                continue
            completed.append(job)
            for key, entry in budget["jobs"].items():
                pattern = "^" + ".+?".join(re.escape(part) for part in re.split(r"\$\{\{.*?\}\}", entry["display_name"])) + "$"
                if key.startswith(workflow + "/") and re.match(pattern, job["name"]):
                    durations[key].append(minutes)
                    break
        if (run.get("head_repository") or {}).get("full_name") != item["repository"] or not completed:
            continue
        first_failure = [job for job in completed if job["conclusion"] in ("failure", "timed_out")]
        finish = min(timestamp(job["completed_at"]) for job in first_failure) if first_failure else max(timestamp(job["completed_at"]) for job in completed)
        signals[run["head_sha"]].append(((finish - timestamp(run["created_at"])).total_seconds() / 60, bool(first_failure)))
    rows = {}
    problems = []
    projected = {"linux": 0.0, "macos": 0.0}
    for key, entry in budget["jobs"].items():
        workflow = key.split("/", 1)[0]
        if "pull_request" not in budget["workflows"][workflow]["triggers"] or entry["expected_runs_per_day"] == 0:
            continue
        values = durations[key]
        minimum = 1 if entry["expected_runs_per_day"] < 10 else 3
        rows[key] = {
            "count": len(values),
            "p50_minutes": statistics.median(values) if values else None,
            "mean_minutes": statistics.mean(values) if values else None,
            "budget_p50_minutes": entry["budget_p50_minutes"],
            "owner": entry["owner"],
        }
        for runner, count in entry["runner_counts"].items():
            if runner in projected:
                projected[runner] += (rows[key]["p50_minutes"] or entry["budget_p50_minutes"]) * count * entry["expected_runs_per_day"]
        if len(values) < minimum:
            problems.append(f"{key}: under-sampled ({len(values)} < {minimum})")
        elif rows[key]["p50_minutes"] > entry["budget_p50_minutes"]:
            problems.append(f"{key}: p50 {rows[key]['p50_minutes']:.1f} > {entry['budget_p50_minutes']} min")
    per_commit = {sha: (min(value for value, failed in values if failed) if any(failed for _, failed in values) else max(value for value, _ in values)) for sha, values in signals.items()}
    cap = budget["caps"]["internal_time_to_signal_minutes"]
    for runner in projected:
        limit = budget["caps"][f"pr_{runner}_minutes_per_day"]
        if projected[runner] > limit:
            problems.append(f"projected PR {runner} minutes/day {projected[runner]:.1f} > {limit}")
    if len(per_commit) < 3:
        problems.append(f"internal time-to-signal: under-sampled ({len(per_commit)} < 3)")
    elif statistics.median(per_commit.values()) > cap:
        problems.append(f"internal time-to-signal p50 {statistics.median(per_commit.values()):.1f} > {cap} min")
    return {
        "generated_at": now.isoformat(),
        "sampled_runs": len(samples),
        "jobs": rows,
        "internal_time_to_signal_p50_minutes": statistics.median(per_commit.values()) if per_commit else None,
        "internal_commit_count": len(per_commit),
        "projected_pr_minutes_per_day": projected,
        "problems": problems,
    }


def markdown(report: dict) -> str:
    lines = ["# Weekly CI budget audit", "", f"Sampled runs: {report['sampled_runs']}; internal commits: {report['internal_commit_count']}", "", "| Job | Owner | Count | p50 | Mean | Budget p50 |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for key, row in sorted(report["jobs"].items()):
        lines.append(f"| {key} | {row['owner']} | {row['count']} | {row['p50_minutes']} | {row['mean_minutes']} | {row['budget_p50_minutes']} |")
    lines += ["", f"Projected PR minutes/day: Linux {report['projected_pr_minutes_per_day']['linux']:.1f}, macOS {report['projected_pr_minutes_per_day']['macos']:.1f}.", f"Internal time-to-signal p50: {report['internal_time_to_signal_p50_minutes']} minutes."]
    lines += ["", "## Problems", ""] + ([f"- {problem}" for problem in report["problems"]] or ["None."])
    return "\n".join(lines) + "\n"


def collect(api: Github, budget: dict, now: datetime) -> list[dict]:
    eligible = [name for name, wf in budget["workflows"].items() if "pull_request" in wf["triggers"]]
    if len(eligible) > MAX_WORKFLOWS:
        raise RuntimeError(f"{len(eligible)} PR workflows exceeds bounded sample capacity {MAX_WORKFLOWS}")
    result = []
    for workflow in eligible:
        for offset in range(1, DAYS + 1):
            day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
            query = urllib.parse.urlencode({"event": "pull_request", "status": "completed", "created": day, "per_page": 1})
            page = api.request("GET", f"/repos/{api.repo}/actions/workflows/{workflow}/runs?{query}")
            for run in page.get("workflow_runs", [])[:1]:
                jobs = api.request("GET", f"/repos/{api.repo}/actions/runs/{run['id']}/jobs?per_page=100")
                if jobs.get("total_count", 0) > 100:
                    raise RuntimeError(f"run {run['id']} exceeds 100-job sample limit")
                if not jobs.get("jobs") or all(job.get("conclusion") == "skipped" for job in jobs["jobs"]):
                    continue
                result.append({"workflow": workflow, "repository": api.repo, "run": run, "jobs": jobs["jobs"]})
    return result


def upsert_issue(api: Github, report: dict, body: str) -> None:
    if not report["problems"]:
        return
    query = urllib.parse.urlencode({"q": f'repo:{api.repo} is:issue is:open in:title "{TITLE}"', "per_page": 20})
    matches = api.request("GET", f"/search/issues?{query}").get("items", [])
    issue = next((item for item in matches if item["title"] == TITLE), None)
    path = f"/repos/{api.repo}/issues" + (f"/{issue['number']}" if issue else "")
    api.request("PATCH" if issue else "POST", path, {"title": TITLE, "body": body})


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    api = Github(repo, os.environ["GITHUB_TOKEN"])
    budget = json.loads(Path(".github/ci-budget.yaml").read_text())
    now = datetime.now(timezone.utc)
    report = summarize(budget, collect(api, budget, now), now)
    out = Path(os.environ.get("CI_BUDGET_REPORT_DIR", "ci-budget-report"))
    out.mkdir(parents=True, exist_ok=True)
    body = markdown(report)
    (out / "report.md").write_text(body)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    upsert_issue(api, report, body)
    report["api_calls"] = api.calls
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"CI budget sample: {report['sampled_runs']} runs, {api.calls} API calls, {len(report['problems'])} problems")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, urllib.error.URLError) as exc:
        print(f"CI budget audit failed: {exc}", file=sys.stderr)
        sys.exit(1)
