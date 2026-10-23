#!/usr/bin/env python3
"""Read this run's completed jobs and publish a bounded nightly failure receipt.

Only GitHub read APIs are used. Raw logs stay in memory; artifacts contain test
identifiers, job names, source SHAs and links, never whole log extracts.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


WORKFLOW = "main_nightly_full.yml"
BAD = {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}


def gh(*args, json_result=False):
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=90)
    return json.loads(result.stdout) if json_result else result.stdout


def api_pages(endpoint, key):
    pages = gh("api", "--paginate", "--slurp", endpoint, json_result=True)
    return [row for page in pages for row in page[key]]


def failing_tests(log):
    """Extract runner failure records, avoiding arbitrary assertion payloads."""
    found = set()
    for line in log.splitlines():
        line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
        line = re.sub(r"^\d{4}-\d\d-\d\dT\S+\s+", "", line)
        patterns = (
            r"\bFAILED\s+([^\s]+\.py::[^\s]+)",
            r"Test Case ['\"](.+?)['\"] failed",
            r"(?:^|\s)([^\n]+?)\s+\[E\](?:\s|$)",
            r"❌\s+(.+?)(?:\s+\(failed\))?$",
            r"^\s*(?:FAIL|FAILURE)\s+([^\n]+\.(?:test|spec)\.[jt]sx?(?:\s+>.*)?)",
            r"^\s*●\s+(.+?\s+›\s+.+)$",
            r"^\s*(\S+\s+>\s+.+?)\s+FAILED\b",
            r"^\s*not ok\s+\d+\s+-\s+(.+)$",
            r"^\s*(?:FAIL|ERROR):\s+(.+)$",
            r"^\s*--- FAIL:\s+(\S+)",
            r"✘\s+Test\s+(.+?)\s+(?:failed|recorded an issue)\b",
            r"^\s*\d+\)\s+(\[[^\]]+\]\s+›.+)$",
            r"^\s*test\s+(\S+)\s+\.\.\.\s+FAILED",
            r"^\s*\d+\s*-\s*(\S+)\s+\(Failed\)",
        )
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                name = match.group(1).strip()
                # Flutter prefixes include progress counts; keep file + test name.
                name = re.sub(r"^.*?\+\d+(?:\s+~\d+)?\s+-\d+:\s*", "", name)
                found.add(re.sub(r"[\x00-\x1f\x7f]", "", name)[:600])
    return sorted(found)


def last_green(repo, run_id, main_sha):
    runs = api_pages(
        f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?status=success&per_page=100", "workflow_runs"
    )
    previous = [r for r in runs if r["id"] < run_id and r["event"] in ("schedule", "workflow_dispatch")]
    for run in sorted(previous, key=lambda r: r["id"], reverse=True):
        # An expired or malformed receipt is not a baseline; an older verified
        # green still bounds the bisect range, so keep looking.
        try:
            with tempfile.TemporaryDirectory() as directory:
                gh("run", "download", str(run["id"]), "--repo", repo, "--name", "nightly-main-report", "--dir", directory)
                receipt = json.loads((Path(directory) / "report.json").read_text())
            valid = (receipt["run_id"] == run["id"] and not receipt["failures"]
                     and re.fullmatch(r"[0-9a-f]{40}", receipt["main_sha"]))
        except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            continue
        # Lead ruling 9cb025: workflow branch is not the tested source. A
        # successful branch dispatch is a baseline only on the tested main
        # lineage. An older run may have been rerun against newer main code;
        # that newer SHA cannot be the lower bound of this run's bisect range.
        status = gh("api", f"repos/{repo}/compare/{receipt['main_sha']}...{main_sha}", "--jq", ".status").strip()
        if status in ("ahead", "identical"):
            return receipt["main_sha"]
        if status not in ("behind", "diverged"):
            raise ValueError("Cannot verify last-green source ancestry")
    return None


def collect(repo, run_id, main_sha, jobs):
    failures = []
    for job in jobs:
        if job["conclusion"] not in BAD:
            continue
        names = []
        try:
            # Colored test logs are captured and sanitized, never printed raw.
            names = failing_tests(gh("api", "--allow-escape-sequences", f"repos/{repo}/actions/jobs/{job['id']}/logs"))
        except subprocess.SubprocessError:
            pass
        if not names:
            names = ["job failure (test name unavailable): " + ", ".join(
                step["name"] for step in job.get("steps", []) if step.get("conclusion") in BAD
            )]
        failures.extend({"job": job["name"], "test": name} for name in names)
    try:
        green = last_green(repo, run_id, main_sha)
    except (subprocess.SubprocessError, ValueError):
        # The failure names matter more than the bisect bound; always write the receipt.
        green = None
    return {"schema_version": 1, "run_id": run_id, "main_sha": main_sha,
            "last_green_sha": green, "failures": failures}


def summary(report):
    # HTML escaping also prevents a test identifier from becoming executable Markdown.
    import html

    lines = ["## Unfiltered main nightly", "", f"Main SHA: `{report['main_sha']}`",
             f"Last green nightly SHA: `{report['last_green_sha'] or 'none (first successful nightly not recorded)'}`", ""]
    if report["failures"]:
        lines += ["| Job | Failing test or infrastructure step |", "|---|---|"]
        for row in report["failures"]:
            lines.append("| " + " | ".join(html.escape(row[k]).replace("|", "&#124;").replace("\n", " ")
                                              for k in ("job", "test")) + " |")
    else:
        lines.append("All selected jobs passed.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--needs-json", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.main_sha):
        parser.error("main SHA must be a full commit ID")
    jobs = api_pages(f"repos/{args.repo}/actions/runs/{args.run_id}/jobs?filter=latest&per_page=100", "jobs")
    report = collect(args.repo, args.run_id, args.main_sha, jobs)
    report["run_attempt"] = int(os.environ["GITHUB_RUN_ATTEMPT"])
    # Catch workflow startup, skipped calls and graph failures with no job log.
    for name, result in json.loads(args.needs_json).items():
        if result["result"] != "success" and not any(row["job"].startswith(name + " /") for row in report["failures"]):
            report["failures"].append({"job": name, "test": f"workflow result: {result['result']}"})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out / "last-green-sha.txt").write_text((report["last_green_sha"] or "none") + "\n")
    rendered = summary(report)
    (args.out / "summary.md").write_text(rendered)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as handle:
        handle.write(rendered)
    return int(bool(report["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
