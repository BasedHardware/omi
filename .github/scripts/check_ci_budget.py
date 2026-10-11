#!/usr/bin/env python3
"""Offline GitHub Actions inventory and reviewed runner-minute budget gate.

The inventory is JSON (a YAML subset) so refreshes have deterministic diffs.
Only workflow-derived fields are regenerated; the remaining fields are owned by
reviewers. Run with --refresh after editing workflows, then edit new/raised
budgets and their rationale before committing.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

INVENTORY = Path(".github/ci-budget.yaml")
DEFAULT_BUDGET = 5
PR_EVENTS = {"pull_request", "pull_request_target", "merge_group"}


def normalized(value):
    return json.loads(json.dumps(value, sort_keys=True))


def runner_class(runs_on, uses) -> str:
    if uses:
        return "reusable"
    value = json.dumps(runs_on).lower()
    if "macos" in value or "xcode" in value:
        return "macos"
    if "windows" in value:
        return "windows"
    if "ubuntu" in value or "linux" in value:
        return "linux"
    return "dynamic"


def matrix_size(strategy) -> int:
    if not isinstance(strategy, dict):
        return 1
    matrix = strategy.get("matrix", {})
    if not isinstance(matrix, dict):
        return 1
    result = 1
    dimensions = 0
    for key, values in matrix.items():
        if key not in ("include", "exclude") and isinstance(values, list):
            result *= len(values)
            dimensions += 1
    if isinstance(matrix.get("include"), list):
        result = (result if dimensions else 0) + len(matrix["include"])
    if isinstance(matrix.get("exclude"), list):
        result = max(0, result - len(matrix["exclude"]))
    return result


def runner_counts(runs_on, strategy, runner, size) -> dict:
    matrix = (strategy or {}).get("matrix", {})
    if runner == "dynamic" and isinstance(matrix, dict) and isinstance(matrix.get("include"), list):
        counts = defaultdict(int)
        for row in matrix["include"]:
            if not isinstance(row, dict):
                return {"dynamic": size}
            possible = [value for value in row.values() if isinstance(value, str) and ("ubuntu" in value or "macos" in value or "windows" in value)]
            if len(possible) != 1:
                return {"dynamic": size}
            counts[runner_class(possible[0], None)] += 1
        return dict(counts)
    return {runner: size}


def inventory(root: Path) -> dict:
    workflows = {}
    jobs = {}
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        doc = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: expected mapping")
        name = path.name
        trigger = doc.get("on", {})
        if isinstance(trigger, str):
            trigger = {trigger: None}
        if isinstance(trigger, list):
            trigger = {item: None for item in trigger}
        if not isinstance(trigger, dict):
            raise ValueError(f"{path}: invalid trigger")
        workflows[name] = {"name": doc.get("name", name), "triggers": normalized(trigger)}
        for job_id, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                raise ValueError(f"{path}: invalid job {job_id}")
            key = f"{name}/{job_id}"
            runner = runner_class(job.get("runs-on"), job.get("uses"))
            size = matrix_size(job.get("strategy"))
            jobs[key] = {
                "display_name": job.get("name", job_id),
                "runner": runner,
                "runner_counts": runner_counts(job.get("runs-on"), job.get("strategy"), runner, size),
                "runs_on": normalized(job.get("runs-on")),
                "reusable": job.get("uses"),
                "if": job.get("if"),
                "needs": normalized(job.get("needs", [])),
                "matrix": normalized((job.get("strategy") or {}).get("matrix", {})),
                "matrix_size": size,
            }
    return {"workflows": workflows, "jobs": jobs}


def sample(dayruns: Path, dayjobs: Path) -> tuple[dict, dict]:
    run_workflows = {}
    counts = defaultdict(int)
    durations = defaultdict(list)
    with dayruns.open() as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) >= 2:
                run_workflows[row[0]] = row[1]
    with dayjobs.open() as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) < 5 or row[2] == "skipped":
                continue
            try:
                start = datetime.fromisoformat(row[3].replace("Z", "+00:00"))
                end = datetime.fromisoformat(row[4].replace("Z", "+00:00"))
            except ValueError:
                continue
            if end > start:
                durations[(run_workflows.get(row[0]), row[1])].append((end - start).total_seconds() / 60)
                counts[(run_workflows.get(row[0]), row[1])] += 1
    return counts, durations


def observed(values: dict, workflow: str, display_name: str) -> list:
    """Match concrete matrix job names to their expression-bearing YAML name."""
    pattern = re.compile("^" + ".+?".join(re.escape(part) for part in re.split(r"\$\{\{.*?\}\}", display_name)) + "$")
    return [item for (wf, name), group in values.items() if wf == workflow and pattern.match(name) for item in (group if isinstance(group, list) else [group])]


def refresh(root: Path, sample_paths: tuple[Path, Path] | None = None, reseed: bool = False) -> dict:
    path = root / INVENTORY
    prior = json.loads(path.read_text()) if path.exists() else {}
    data = inventory(root)
    old_jobs = prior.get("jobs", {})
    old_workflows = prior.get("workflows", {})
    counts, durations = sample(*sample_paths) if sample_paths else ({}, {})
    for name, wf in data["workflows"].items():
        wf["owner"] = old_workflows.get(name, {}).get("owner", "CI maintainers")
        wf["rationale"] = old_workflows.get(name, {}).get("rationale", "Initial workflow inventory")
    for key, job in data["jobs"].items():
        old = old_jobs.get(key, {})
        workflow = key.split("/", 1)[0]
        wf_name = data["workflows"][workflow]["name"]
        minutes = observed(durations, wf_name, job["display_name"])
        executions = sum(observed(counts, wf_name, job["display_name"]))
        seeded = max(1, math.ceil(statistics.median(minutes) * 1.25)) if minutes else DEFAULT_BUDGET
        job["budget_p50_minutes"] = seeded if reseed else old.get("budget_p50_minutes", seeded)
        pr = bool(PR_EVENTS.intersection(data["workflows"][workflow]["triggers"]))
        expected = math.ceil(executions / max(1, job["matrix_size"])) if executions else (1 if pr else 0)
        job["expected_runs_per_day"] = expected if reseed else old.get("expected_runs_per_day", expected)
        job["expected_runs_class"] = old.get("expected_runs_class", "sampled-pr-day" if executions else ("unsampled-pr-sentinel" if pr else "non-pr"))
        job["owner"] = old.get("owner", "CI maintainers")
        job["rationale"] = old.get("rationale", "2026-09-26 PR sample p50 x 1.25, rounded up" if minutes else "Unobserved in one-day PR sample; conservative 5-minute placeholder")
    data["schema"] = 1
    data["seed"] = prior.get("seed", "2026-09-26 one-day PR sample; refresh and re-seed after lane/ci-diet merges")
    data["caps"] = prior.get("caps", {"pr_linux_minutes_per_day": 16000, "pr_macos_minutes_per_day": 2500, "internal_time_to_signal_minutes": 45})
    data["caps_rationale"] = prior.get("caps_rationale", "Seeded above 2026-09-26 per-job p50 x 1.25: 14,385 Linux, 2,146 macOS minutes/day and 37 minutes critical path")
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def load_base(root: Path, base: str) -> dict | None:
    verified = subprocess.run(["git", "rev-parse", "--verify", f"{base}^{{commit}}"], cwd=root, capture_output=True, text=True)
    if verified.returncode:
        raise ValueError(f"cannot resolve CI budget comparison base {base!r}")
    result = subprocess.run(["git", "show", f"{base}:{INVENTORY}"], cwd=root, capture_output=True, text=True)
    if result.returncode:
        return None
    return json.loads(result.stdout)


def trigger_widened(before: dict, after: dict) -> bool:
    """A conservative semantic comparison of GitHub event filters."""
    if set(after) - set(before):
        return True
    for event in set(before) & set(after):
        old = before[event] if isinstance(before[event], dict) else {}
        new = after[event] if isinstance(after[event], dict) else {}
        for field in ("branches", "paths", "types"):
            old_values = old.get(field)
            new_values = new.get(field)
            old_set = set(old_values if isinstance(old_values, list) else [old_values]) if old_values is not None else None
            new_set = set(new_values if isinstance(new_values, list) else [new_values]) if new_values is not None else None
            if old_set is not None and (new_set is None or not new_set <= old_set):
                return True
        for field in ("branches-ignore", "paths-ignore"):
            old_values = old.get(field)
            new_values = new.get(field)
            old_set = set(old_values if isinstance(old_values, list) else [old_values]) if old_values is not None else set()
            new_set = set(new_values if isinstance(new_values, list) else [new_values]) if new_values is not None else set()
            if not old_set <= new_set:
                return True
        if any(field not in ("branches", "paths", "types", "branches-ignore", "paths-ignore") and old.get(field) != new.get(field) for field in set(old) | set(new)):
            return True
    return False


def totals(data: dict) -> tuple[dict, float]:
    daily = {"linux": 0, "macos": 0}
    signal = {}
    for key, job in data["jobs"].items():
        workflow = key.split("/", 1)[0]
        triggers = data["workflows"][workflow]["triggers"]
        if PR_EVENTS.intersection(triggers):
            for runner, count in job["runner_counts"].items():
                if runner in daily:
                    daily[runner] += job["budget_p50_minutes"] * count * job["expected_runs_per_day"]

    def path_minutes(key: str, visiting: set[str]) -> float:
        if key in signal:
            return signal[key]
        if key in visiting:
            raise ValueError(f"cyclic needs graph at {key}")
        job = data["jobs"][key]
        workflow = key.split("/", 1)[0]
        needs = job["needs"]
        if isinstance(needs, str):
            needs = [needs]
        parents = [f"{workflow}/{need}" for need in needs if f"{workflow}/{need}" in data["jobs"]]
        parent = max((path_minutes(parent, visiting | {key}) for parent in parents), default=0)
        signal[key] = parent + job["budget_p50_minutes"] * job["matrix_size"]
        return signal[key]

    pr_keys = [key for key in data["jobs"] if PR_EVENTS.intersection(data["workflows"][key.split("/", 1)[0]]["triggers"])]
    return daily, max((path_minutes(key, set()) for key in pr_keys), default=0)


def validate(root: Path, base: dict | None = None) -> list[str]:
    path = root / INVENTORY
    if not path.exists():
        return [f"{INVENTORY}: missing; run check_ci_budget.py --refresh"]
    data = json.loads(path.read_text())
    actual = inventory(root)
    errors = []
    for section in ("workflows", "jobs"):
        if set(data.get(section, {})) != set(actual[section]):
            errors.append(f"{section}: inventory IDs differ from workflows; run --refresh")
        for key, generated in actual[section].items():
            row = data.get(section, {}).get(key, {})
            for field, value in generated.items():
                if row.get(field) != value:
                    errors.append(f"{key}: stale {field}; run --refresh")
            if not row.get("owner") or not row.get("rationale"):
                errors.append(f"{key}: owner and rationale are required")
    for key, job in data.get("jobs", {}).items():
        if not isinstance(job.get("budget_p50_minutes"), (int, float)) or job["budget_p50_minutes"] <= 0:
            errors.append(f"{key}: positive p50 budget required")
        if not isinstance(job.get("expected_runs_per_day"), (int, float)) or job["expected_runs_per_day"] < 0:
            errors.append(f"{key}: nonnegative expected runs/day required")
        if not job.get("expected_runs_class"):
            errors.append(f"{key}: expected runs/day class required")
        workflow = key.split("/", 1)[0]
        if PR_EVENTS.intersection(actual["workflows"].get(workflow, {}).get("triggers", {})) and job.get("expected_runs_per_day", 0) == 0:
            errors.append(f"{key}: PR job needs nonzero expected runs/day")
        if "dynamic" in job.get("runner_counts", {}):
            errors.append(f"{key}: dynamic runner cannot be budgeted; resolve the matrix runner classes")
    if errors:
        return errors
    daily, signal = totals(data)
    caps = data["caps"]
    for runner in ("linux", "macos"):
        if daily[runner] > caps[f"pr_{runner}_minutes_per_day"]:
            errors.append(f"PR {runner} budget {daily[runner]} exceeds cap {caps[f'pr_{runner}_minutes_per_day']}")
    if signal > caps["internal_time_to_signal_minutes"]:
        errors.append(f"internal time-to-signal budget {signal} exceeds cap {caps['internal_time_to_signal_minutes']}")
    if base:
        if data["caps"] != base.get("caps") and data["caps_rationale"] == base.get("caps_rationale"):
            errors.append("caps: change requires updated rationale")
        for section in ("workflows", "jobs"):
            for key, row in data[section].items():
                previous = base.get(section, {}).get(key)
                if previous is None:
                    # New entries have no earlier rationale to compare, but must
                    # explicitly replace the refresh placeholder.
                    if row["rationale"].startswith(("Initial workflow", "Unobserved in one-day", "2026-09-26 PR sample")):
                        errors.append(f"{key}: new entry needs reviewed rationale")
                    continue
                generated = actual[section][key]
                changed = any(previous.get(field) != row.get(field) for field in generated)
                raised = section == "jobs" and (row["budget_p50_minutes"] > previous["budget_p50_minutes"] or row["expected_runs_per_day"] > previous["expected_runs_per_day"])
                if changed or raised:
                    if row["rationale"] == previous.get("rationale"):
                        errors.append(f"{key}: structural or budget change needs rationale change")
                    if section == "jobs" and changed and row["budget_p50_minutes"] == previous["budget_p50_minutes"] and row["expected_runs_per_day"] == previous["expected_runs_per_day"]:
                        # Pure narrowing is allowed without a number change.
                        widening = row["matrix_size"] > previous.get("matrix_size", 1) or row["runner"] != previous.get("runner") or row["if"] != previous.get("if") or row["runs_on"] != previous.get("runs_on")
                        if widening:
                            errors.append(f"{key}: expanded job needs explicit budget or expected-runs change")
        for workflow, row in data["workflows"].items():
            previous = base.get("workflows", {}).get(workflow)
            if previous and trigger_widened(previous.get("triggers", {}), row["triggers"]):
                for key, job in data["jobs"].items():
                    if key.startswith(workflow + "/") and key in base.get("jobs", {}):
                        before = base["jobs"][key]
                        if job["budget_p50_minutes"] == before["budget_p50_minutes"] and job["expected_runs_per_day"] == before["expected_runs_per_day"]:
                            errors.append(f"{key}: trigger change needs explicit budget or expected-runs change")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--seed-dayruns", type=Path)
    parser.add_argument("--seed-dayjobs", type=Path)
    parser.add_argument("--reseed", action="store_true", help="replace sampled runtime and frequency numbers after CI diet merges")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.refresh:
        if args.reseed and not (args.seed_dayruns and args.seed_dayjobs):
            parser.error("--reseed requires --seed-dayruns and --seed-dayjobs")
        paths = (args.seed_dayruns, args.seed_dayjobs) if args.seed_dayruns and args.seed_dayjobs else None
        refresh(root, paths, args.reseed)
        print(f"Refreshed {INVENTORY}")
        return 0
    try:
        errors = validate(root, load_base(root, args.base))
    except ValueError as exc:
        print(f"CI budget check failed: {exc}")
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print("CI budget check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
