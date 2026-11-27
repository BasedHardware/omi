"""Publish the registry checker's deadline warnings to one GitHub issue."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

TITLE = "Feature flag deadlines approaching"
MARKER = "<!-- omi-feature-flag-deadline-tracker -->"
DATE = r"\d{4}-\d{2}-\d{2}"
DUE_SOON = re.compile(
    rf"FLAG_DUE_SOON key=(.+?) owner=(.+) kind=(review|ramp) due=({DATE}) breaks=({DATE})"
)


def code_span(value: str) -> str:
    delimiter = "`" * (max((len(run) for run in re.findall(r"`+", value)), default=0) + 1)
    return f"{delimiter} {value} {delimiter}"


def render_deadlines(output: str, registry_url: str) -> tuple[str, bool]:
    rows = []
    for line in output.splitlines():
        if not line.startswith("FLAG_DUE_SOON "):
            continue
        match = DUE_SOON.fullmatch(line)
        if not match:
            raise ValueError(f"Invalid deadline warning: {line}")
        key, owner, kind, due, breaks = match.groups()
        rows.append(f"- {code_span(key)} ({kind}) — owner {code_span(owner)}, due {due}, fails main {breaks} UTC.")

    lines = [MARKER, f"[Feature flag registry]({registry_url})", ""]
    if rows:
        lines.extend(["Owners, please ramp, retire, or add one extension where eligible.", "", *rows])
    else:
        lines.append("No feature flag deadlines are in the warning window.")
    return "\n".join(lines) + "\n", bool(rows)


def github_api(endpoint: str, *args: str, payload: dict[str, str] | None = None) -> str:
    command = ["gh", "api", endpoint, *args]
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    return result.stdout


def sync_issue(repo: str, body: str, has_deadlines: bool) -> None:
    endpoint = f"repos/{repo}/issues"
    # Include closed issues and avoid the search index so consecutive runs see the same issue.
    pages = json.loads(github_api(
        f"{endpoint}?state=all&creator=github-actions%5Bbot%5D&per_page=100",
        "--paginate",
        "--slurp",
    ))
    issue = next(
        (
            issue
            for page in pages
            for issue in page
            if "pull_request" not in issue and (issue["body"] or "").startswith(MARKER)
        ),
        None,
    )
    if issue is None:
        if has_deadlines:
            github_api(endpoint, "--method", "POST", payload={"title": TITLE, "body": body})
        return

    payload = {"body": body}
    if has_deadlines and issue["state"] == "closed":
        payload["state"] = "open"
    if issue["body"] != body or "state" in payload:
        github_api(f"{endpoint}/{issue['number']}", "--method", "PATCH", payload=payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check_output", type=Path)
    parser.add_argument("repo")
    parser.add_argument("check_status", type=int)
    args = parser.parse_args()
    output = args.check_output.read_text(encoding="utf-8")
    # Schema errors can stop the checker before it emits any deadline information.
    if not any(re.fullmatch(r"FLAG_OVERDUE_COUNT n=\d+", line) for line in output.splitlines()):
        parser.exit(1, "The registry checker did not complete its deadline scan.\n")
    registry_url = f"https://github.com/{args.repo}/blob/main/backend/docs/feature-flag-registry.md"
    body, has_deadlines = render_deadlines(output, registry_url)
    if has_deadlines or args.check_status == 0:
        sync_issue(args.repo, body, has_deadlines)
    return args.check_status


if __name__ == "__main__":
    raise SystemExit(main())
