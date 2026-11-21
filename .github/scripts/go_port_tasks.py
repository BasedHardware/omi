"""Read GitHub PR file records from stdin and emit port task drafts as JSON."""

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
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


def escape_markdown(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~])", r"\\\1", value)


def _difference_report(report):
    compact = {
        "version": report["version"],
        "unexplained_differences": report["unexplained_differences"],
        "expected_differences": report["expected_differences"],
        "failed_cases": report["failed_cases"],
        "cases": [],
    }
    for case in report["cases"]:
        counts = Counter(
            (diff["path"], diff["kind"], diff.get("reason", ""))
            for diff in case["differences"]
        )
        differences = []
        for (path, kind, reason), count in sorted(counts.items()):
            entry = [path, kind, count]
            if reason:
                entry.append(reason)
            differences.append(entry)
        compact["cases"].append([case["name"], differences])
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) <= 50_000:
        return f"```json\n{raw.decode('utf-8')}\n```"
    encoded = base64.b85encode(zlib.compress(raw, level=9)).decode("ascii")
    case_counts = []
    for case in report["cases"]:
        count = sum(not diff.get("reason") for diff in case["differences"])
        case_counts.append(f"{case['name']}: {count}")
    return (
        "Value-free report compressed as zlib + base85 UTF-8 JSON. Counts by case: "
        + "; ".join(case_counts)
        + f". SHA-256 of the uncompressed JSON: `{hashlib.sha256(raw).hexdigest()}`.\n\n"
        + "Decode the payload with Python: `zlib.decompress(base64.b85decode(payload))`.\n\n"
        + "```text\n"
        + encoded
        + "\n```"
    )


def port_tasks(pr_number, families, paths, merge_sha, pr_title, report):
    source = f"https://github.com/BasedHardware/omi/pull/{pr_number}"
    if not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
        raise ValueError("merge SHA must be a full lowercase commit SHA")
    pr_title = " ".join(pr_title.split())
    if not pr_title:
        raise ValueError("PR title must be nonempty")
    tasks = []
    for family, python_paths in sorted(families.items()):
        matched = sorted(paths.intersection(python_paths))
        if not matched:
            continue
        behavior = escape_markdown(pr_title)
        files = ", ".join(f"`{path}`" for path in matched)
        marker = f"<!-- omi-go-port-task:{merge_sha}:{pr_number}:{family} -->"
        if report["unexplained_differences"]:
            task_type = "port"
            title = f"Port Python PR #{pr_number} to Go {family}"
            body = (
                f"Python PR [#{pr_number}]({source}) merged as `{merge_sha}` and changes behavior: {behavior}.\n\n"
                f"Mapped paths: {files}. Review the merged diff and port the changed behavior to the Go {family} "
                "family under `backend-go/`, or record why no Go change is needed.\n\n"
                f"Replay reported {report['unexplained_differences']} unexplained and "
                f"{report['expected_differences']} allowed differences across {len(report['cases'])} cases. "
                "The value-free report follows.\n\n"
                f"{_difference_report(report)}\n\n{marker}"
            )
        else:
            task_type = "corpus"
            title = f"Add Go replay corpus case for Python PR #{pr_number}: {pr_title}"
            title = title[:250]
            body = (
                f"Python PR [#{pr_number}]({source}) merged as `{merge_sha}` changes behavior: {behavior}.\n\n"
                f"Mapped paths: {files}. The replay oracle is green at this merge commit: "
                f"0 unexplained differences across {len(report['cases'])} cases. Add a synthetic replay corpus case "
                f"that exercises the named behavior ({behavior}) for the Go {family} family, and map it to the "
                f"relevant contract rule.\n\n{marker}"
            )
        tasks.append({
            "family": family,
            "task_type": task_type,
            "title": title,
            "body": body,
            "marker": marker,
            "matched_paths": matched,
        })
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, help="Merged BasedHardware/omi PR number")
    parser.add_argument("--pr-title", help="Merged PR title, used to name changed behavior")
    parser.add_argument("--merge-sha", help="Full merge commit SHA")
    parser.add_argument("--changed-files", type=int, help="Expected file count from the GitHub PR metadata")
    parser.add_argument("--oracle-report", action="append", help="Replay JSON report; repeat for each corpus")
    parser.add_argument("--scope-only", action="store_true", help="Print true if the input paths need Go checks")
    parser.add_argument("--mapped-only", action="store_true", help="Print matching port-map families and paths")
    args = parser.parse_args()
    if args.changed_files is not None and args.changed_files < 0:
        parser.error("--changed-files must be nonnegative")
    try:
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
        if not args.merge_sha or not args.pr_title or not args.oracle_report:
            parser.error("--pr-title, --merge-sha, and at least one --oracle-report are required")
        report = load_oracle_reports(args.oracle_report)
        tasks = port_tasks(args.pr, families, paths, args.merge_sha, args.pr_title, report)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    print(json.dumps(tasks, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
