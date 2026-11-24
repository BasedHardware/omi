"""Read GitHub PR file records from stdin and emit port task drafts as JSON."""

import argparse
import base64
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import zlib

import yaml


PORT_MAP = Path(__file__).resolve().parents[2] / "backend-go/docs/port-map.yaml"
GO_CHECK_PATHS = (
    ".github/scripts/go_port_tasks.py",
    ".github/scripts/test_go_port_tasks.py",
    ".github/workflows/backend-go-checks.yml",
    "backend-go/docs/port-map.yaml",
)
GO_CHECK_PREFIXES = ("backend-go/", "backend/testing/finalization_replay/")


# Use the replay oracle's reviewed normalization for volatile fixture document IDs.
_verify_spec = importlib.util.spec_from_file_location(
    "replay_verify", PORT_MAP.parents[1] / "tools/replay/verify.py"
)
_replay_verify = importlib.util.module_from_spec(_verify_spec)
_verify_spec.loader.exec_module(_replay_verify)


def load_port_map(path):
    families = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(families, dict) or not families:
        raise ValueError("port map must be a nonempty mapping from families to Python paths")
    for family, paths in families.items():
        if not isinstance(family, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", family):
            raise ValueError(f"invalid family name: {family!r}")
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"{family} must list at least one Python path")
        if any(not isinstance(p, str) or not re.fullmatch(r"backend/(?:[\w-]+/)*[\w-]+\.py", p) for p in paths):
            raise ValueError(f"{family} must list exact repository-relative backend Python paths")
    return families


def changed_paths(files, expected_count=None):
    if not isinstance(files, list):
        raise ValueError("expected a JSON array of GitHub PR file records")
    if expected_count is not None and len(files) != expected_count:
        raise ValueError(f"expected {expected_count} PR files, received {len(files)}")
    paths = set()
    filenames = set()
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("each PR file record must be an object")
        for field in ("filename", "previous_filename"):
            if field == "previous_filename" and field not in file:
                continue
            path = file.get(field)
            if not isinstance(path, str) or not path:
                raise ValueError(f"{field} must be a nonempty string")
            paths.add(path)
        filenames.add(file["filename"])
    if expected_count is not None and len(filenames) != expected_count:
        raise ValueError(f"expected {expected_count} distinct PR filenames, received {len(filenames)}")
    return paths


def needs_go_check(paths, families):
    mapped_paths = {item for family_paths in families.values() for item in family_paths}
    return any(
        path in mapped_paths
        or path in GO_CHECK_PATHS
        or path.startswith(GO_CHECK_PREFIXES)
        for path in paths
    )


def matching_families(families, paths):
    return {
        family: sorted(paths.intersection(python_paths))
        for family, python_paths in sorted(families.items())
        if paths.intersection(python_paths)
    }


def load_oracle_reports(report_paths):
    cases = []
    unexplained = 0
    expected = 0
    failed = 0
    for report_path in report_paths:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("version") != 1:
            raise ValueError(f"{report_path} must be a version-1 replay report")
        report_cases = report.get("cases")
        if not isinstance(report_cases, list) or not report_cases:
            raise ValueError(f"{report_path} must contain replay cases")
        report_unexplained = report.get("unexplained_differences")
        report_expected = report.get("expected_differences")
        report_failed = report.get("failed_cases")
        if any(type(value) is not int or value < 0 for value in (report_unexplained, report_expected, report_failed)):
            raise ValueError(f"{report_path} has invalid replay counts")
        observed_unexplained = 0
        observed_expected = 0
        for case in report_cases:
            if not isinstance(case, dict) or not isinstance(case.get("name"), str):
                raise ValueError(f"{report_path} has an invalid replay case")
            differences = case.get("differences")
            if not isinstance(differences, list):
                raise ValueError(f"{report_path} case {case['name']!r} has invalid differences")
            clean_differences = []
            for diff in differences:
                if not isinstance(diff, dict) or not isinstance(diff.get("path"), str) or not isinstance(diff.get("kind"), str):
                    raise ValueError(f"{report_path} case {case['name']!r} has an invalid difference")
                item = {"path": diff["path"], "kind": diff["kind"]}
                reason = diff.get("reason", "")
                if reason:
                    if not isinstance(reason, str):
                        raise ValueError(f"{report_path} case {case['name']!r} has an invalid allowance reason")
                    item["reason"] = reason
                    observed_expected += 1
                else:
                    observed_unexplained += 1
                clean_differences.append(item)
            cases.append({"name": case["name"], "differences": clean_differences})
        if observed_unexplained != report_unexplained or observed_expected != report_expected:
            raise ValueError(f"{report_path} replay counts do not match its differences")
        unexplained += report_unexplained
        expected += report_expected
        failed += report_failed
    if not cases:
        raise ValueError("at least one oracle report is required")
    names = [case["name"] for case in cases]
    if len(names) != len(set(names)):
        raise ValueError("oracle reports contain duplicate case names")
    if failed:
        raise ValueError(f"oracle reported {failed} failed cases; no task can be classified")
    return {
        "version": 1,
        "unexplained_differences": unexplained,
        "expected_differences": expected,
        "failed_cases": failed,
        "cases": cases,
    }


def unexplained_delta(parent, merge):
    def identities(report):
        return Counter(
            (case["name"], _replay_verify.stable_path(diff["path"]), diff["kind"])
            for case in report["cases"]
            for diff in case["differences"]
            if not diff.get("reason")
        )

    before, after = identities(parent), identities(merge)
    return {"added": sorted((after - before).elements()), "removed": sorted((before - after).elements())}


def escape_markdown(value):
    escaped = re.sub(r"([\\`*_{}\[\]()#+.!|>~])", r"\\\1", value)
    return escaped.replace("&", "&amp;").replace("<", "&lt;").replace("@", "&#64;")


def _difference_report(delta):
    raw = json.dumps(delta, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    if len(raw) <= 50_000 and b"```" not in raw:
        return f"```json\n{raw.decode('ascii')}\n```"
    encoded = base64.b85encode(zlib.compress(raw, level=9)).decode("ascii")
    return (
        "Value-free delta compressed as zlib + base85 JSON. "
        f"SHA-256 of the uncompressed JSON: `{hashlib.sha256(raw).hexdigest()}`.\n\n"
        "Decode the payload with Python: `zlib.decompress(base64.b85decode(payload))`.\n\n"
        f"```text\n{encoded}\n```"
    )


def port_tasks(pr_number, families, paths, merge_sha, pr_title, delta, parent_sha):
    for sha in (merge_sha, parent_sha):
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("merge and parent SHAs must be full lowercase commit SHAs")
    pr_title = " ".join(pr_title.split())
    if not pr_title:
        raise ValueError("PR title must be nonempty")
    matches = matching_families(families, paths)
    if not matches:
        return []

    source = f"https://github.com/BasedHardware/omi/pull/{pr_number}"
    behavior = escape_markdown(pr_title)
    context = (
        f"Python PR [#{pr_number}]({source}) merged as `{merge_sha}`. "
        f"Changed behavior: {behavior}.\n\n"
    )
    if delta["added"] or delta["removed"]:
        files = "\n".join(
            f"- Go {family}: " + ", ".join(f"`{path}`" for path in matched)
            for family, matched in matches.items()
        )
        marker = f"<!-- omi-go-port-delta:{merge_sha}:{pr_number} -->"
        body = (
            f"{context}Affected families and mapped paths:\n{files}\n\n"
            f"Replay against first parent `{parent_sha}` found "
            f"{len(delta['added'])} added and {len(delta['removed'])} removed unexplained differences. "
            "Review the merged diff and port the affected behavior or record why no Go change is needed. "
            "Each delta entry lists the replay case, JSON Pointer path, and difference kind.\n\n"
            f"{_difference_report(delta)}\n\n{marker}"
        )
        return [{"task_type": "port", "pr": pr_number, "title": f"Port Python PR #{pr_number} to Go",
                 "body": body, "marker": marker}]

    tasks = []
    for family, matched in matches.items():
        files = ", ".join(f"`{path}`" for path in matched)
        marker = f"<!-- omi-go-corpus-pr:{merge_sha}:{pr_number}:{family} -->"
        tasks.append({
            "family": family,
            "task_type": "corpus",
            "pr": pr_number,
            "title": f"Add Go replay corpus cases for {family}",
            "body": (
                f"{context}Mapped paths: {files}. The unexplained replay differences are unchanged "
                f"from first parent `{parent_sha}`. Add a synthetic case for the changed behavior "
                f"and map it to the relevant Go {family} contract rule.\n\n{marker}"
            ),
            "marker": marker,
            "matched_paths": matched,
        })
    return tasks


def corpus_issue_marker(family):
    return f"<!-- omi-go-corpus:{family} -->"


def github_api(endpoint, *, payload=None, method="POST"):
    argv = ["gh", "api"]
    if payload is None:
        argv += ["--paginate", "--slurp"]
    else:
        argv += ["--method", method, "--input", "-"]
    result = subprocess.run(
        [*argv, endpoint], input=None if payload is None else json.dumps(payload),
        stdout=subprocess.PIPE, text=True, check=True,
    )
    data = json.loads(result.stdout)
    if payload is None:
        return [record for page in data for record in page]
    return data


def publish_tasks(tasks, repo, summary, *, issue_limit=5, api=github_api):
    endpoint = f"repos/{repo}/issues"
    issues = [
        issue for issue in api(f"{endpoint}?state=all&labels=task&per_page=100")
        if "pull_request" not in issue
    ]
    rolling = {}
    for family in sorted({task["family"] for task in tasks if task["task_type"] == "corpus"}):
        marker = corpus_issue_marker(family)
        matches = [issue for issue in issues if marker in (issue.get("body") or "")]
        if len(matches) != 1:
            raise ValueError(f"expected one provisioned task issue with marker {marker}, got {len(matches)}")
        rolling[family] = matches[0]

    comment_markers = {}
    created = 0
    skipped = []
    for task in tasks:
        marker = task["marker"]
        if task["task_type"] == "port":
            if any(marker in (issue.get("body") or "") for issue in issues):
                continue
            if created >= issue_limit:
                skipped.append(f"- PR #{task['pr']}: {task['title']}")
                continue
            issue = api(endpoint, payload={"title": task["title"], "body": task["body"], "labels": ["task"]})
            issues.append(issue)
            print(f"Opened {issue['html_url']}")
            created += 1
            continue

        issue = rolling[task["family"]]
        issue_endpoint = f"{endpoint}/{issue['number']}"
        if issue_endpoint not in comment_markers:
            comments = api(f"{issue_endpoint}/comments?per_page=100")
            comment_markers[issue_endpoint] = {
                line for comment in comments for line in (comment.get("body") or "").splitlines()
                if line.startswith("<!-- omi-go-corpus-pr:")
            }
        markers = comment_markers[issue_endpoint]
        if marker in markers:
            continue
        if issue["state"] == "closed":
            api(issue_endpoint, method="PATCH", payload={"state": "open"})
            issue["state"] = "open"
        comment = api(f"{issue_endpoint}/comments", payload={"body": task["body"]})
        markers.add(marker)
        print(f"Posted {comment['html_url']}")

    with summary.open("a", encoding="utf-8") as output:
        output.write(f"## Go replay follow-ups\n\nOpened {created} of at most {issue_limit} new issues.\n")
        if skipped:
            output.write("\nIssue cap reached. Rerun this job to process these deferred follow-ups.\n\n")
            output.write("\n".join(skipped) + "\n")
    return skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, help="Merged BasedHardware/omi PR number")
    parser.add_argument("--pr-title", help="Merged PR title, used to name changed behavior")
    parser.add_argument("--merge-sha", help="Full merge commit SHA")
    parser.add_argument("--changed-files", type=int, help="Expected file count from the GitHub PR metadata")
    parser.add_argument("--oracle-report", action="append", help="Replay JSON report; repeat for each corpus")
    parser.add_argument("--scope-only", action="store_true", help="Print true if the input paths need Go checks")
    parser.add_argument("--mapped-only", action="store_true", help="Print matching port-map families and paths")
    parser.add_argument("--parent-sha", help="Full first-parent SHA")
    parser.add_argument("--parent-report", action="append", help="First-parent report; repeat for each corpus")
    parser.add_argument("--publish", metavar="REPO", help="Publish classified task drafts from stdin")
    parser.add_argument("--summary", type=Path, help="GitHub Actions job summary path")
    args = parser.parse_args()
    if args.changed_files is not None and args.changed_files < 0:
        parser.error("--changed-files must be nonnegative")
    try:
        if args.publish:
            if args.summary is None:
                parser.error("--publish requires --summary")
            publish_tasks(json.load(sys.stdin), args.publish, args.summary)
            return
        families = load_port_map(PORT_MAP)
        paths = changed_paths(json.load(sys.stdin), args.changed_files)
        if args.scope_only:
            print("true" if needs_go_check(paths, families) else "false")
            return
        if args.mapped_only:
            print(json.dumps(matching_families(families, paths), separators=(",", ":")))
            return
        if args.pr is None or args.pr < 1:
            parser.error("--pr must be positive")
        if not all((args.merge_sha, args.pr_title, args.oracle_report, args.parent_sha, args.parent_report)):
            parser.error("--pr-title, --merge-sha, --oracle-report, --parent-sha, and --parent-report are required")
        parent = load_oracle_reports(args.parent_report)
        report = load_oracle_reports(args.oracle_report)
        delta = unexplained_delta(parent, report)
        tasks = port_tasks(args.pr, families, paths, args.merge_sha, args.pr_title, delta, args.parent_sha)
    except (OSError, ValueError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    print(json.dumps(tasks, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
