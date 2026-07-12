#!/usr/bin/env python3
"""Report desktop Swift changes that do or do not have e2e flow coverage."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DESKTOP_SWIFT_ROOT = Path("desktop/macos/Desktop/Sources")
DEFAULT_FLOWS_DIR = Path("desktop/macos/e2e/flows")
GIT_ENV_DROP = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}


@dataclass(frozen=True)
class FlowCoverage:
    flow_path: Path
    flow_name: str
    covered_paths: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "changed_files",
        nargs="*",
        help="Changed files to check. If omitted, files come from git diff.",
    )
    parser.add_argument("--root", default=None, help="Repository root. Defaults to the git top-level.")
    parser.add_argument("--base", default=None, help="Git base ref when no paths are provided.")
    parser.add_argument("--staged", action="store_true", help="Use staged changes when no paths are provided.")
    parser.add_argument("--flows-dir", default=str(DEFAULT_FLOWS_DIR), help="Flow directory.")
    parser.add_argument("--strict", action="store_true", help="Fail when any changed Swift source file is uncovered.")
    return parser.parse_args()


def git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in GIT_ENV_DROP}


def repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=git_env(),
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parents[3]


def run_git(root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=git_env(),
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def default_base(root: Path) -> str | None:
    best: tuple[int, str] | None = None
    for candidate in ("upstream/main", "origin/main", "main"):
        result = subprocess.run(
            ["git", "merge-base", candidate, "HEAD"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=git_env(),
        )
        merge_base = result.stdout.strip()
        if result.returncode != 0 or not merge_base:
            continue
        distance_result = subprocess.run(
            ["git", "rev-list", "--count", f"{merge_base}..HEAD"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=git_env(),
        )
        if distance_result.returncode != 0:
            continue
        try:
            distance = int(distance_result.stdout.strip())
        except ValueError:
            continue
        if best is None or distance < best[0]:
            best = (distance, merge_base)
    return best[1] if best else None


def changed_files_from_git(root: Path, base: str | None, staged: bool) -> list[str]:
    if staged:
        return run_git(root, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    files: list[str] = []
    resolved_base = base or default_base(root)
    if resolved_base:
        files.extend(run_git(root, ["diff", "--name-only", "--diff-filter=ACMR", f"{resolved_base}...HEAD"]))
    else:
        files.extend(run_git(root, ["diff", "--name-only", "--diff-filter=ACMR", "HEAD"]))
    files.extend(run_git(root, ["diff", "--name-only", "--diff-filter=ACMR", "HEAD"]))
    files.extend(run_git(root, ["ls-files", "--others", "--exclude-standard", str(DESKTOP_SWIFT_ROOT)]))
    return sorted(dict.fromkeys(files))


def canonical_path(value: str | Path) -> str:
    text = Path(value).as_posix().lstrip("./")
    if text.startswith("desktop/Desktop/"):
        return "desktop/macos/" + text[len("desktop/") :]
    return text


def coverage_aliases(value: str | Path) -> set[str]:
    canonical = canonical_path(value)
    aliases = {canonical}
    if canonical.startswith("desktop/macos/"):
        aliases.add("desktop/" + canonical[len("desktop/macos/") :])
    return aliases


def is_desktop_swift_source(path: str) -> bool:
    canonical = canonical_path(path)
    if not (canonical.startswith(DESKTOP_SWIFT_ROOT.as_posix() + "/") and canonical.endswith(".swift")):
        return False
    # Generated sources (e.g. Sources/Generated/OmiApi.generated.swift) are
    # produced from the OpenAPI contract, not hand-written, so they cannot be
    # covered by an e2e flow — exclude them from the coverage ratchet. Changing
    # a shared backend enum forces these to regenerate, which must not require a
    # user-flow covers: entry.
    if "/Generated/" in canonical or canonical.endswith(".generated.swift"):
        return False
    return True


def read_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        data: dict[str, object] = {}
        covers: list[str] = []
        in_covers = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("name:"):
                data["name"] = stripped.split(":", 1)[1].strip().strip("'\"")
                in_covers = False
                continue
            if stripped == "covers:":
                in_covers = True
                continue
            if in_covers and stripped.startswith("- "):
                covers.append(stripped[2:].strip().strip("'\""))
                continue
            if not raw_line.startswith((" ", "\t")):
                in_covers = False
        if covers:
            data["covers"] = covers
        return data
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def load_flows(root: Path, flows_dir: Path) -> list[FlowCoverage]:
    directory = flows_dir if flows_dir.is_absolute() else root / flows_dir
    flows: list[FlowCoverage] = []
    for path in sorted(directory.glob("*.yaml")):
        data = read_yaml(path)
        covers = data.get("covers") or []
        if not isinstance(covers, list):
            covers = []
        covered_paths = tuple(str(item) for item in covers if isinstance(item, str))
        flow_name = str(data.get("name") or path.stem)
        flows.append(FlowCoverage(path, flow_name, covered_paths))
    return flows


def flow_matches(flows: Iterable[FlowCoverage], changed_file: str) -> list[FlowCoverage]:
    changed_aliases = coverage_aliases(changed_file)
    matches: list[FlowCoverage] = []
    for flow in flows:
        covered_aliases: set[str] = set()
        for item in flow.covered_paths:
            covered_aliases.update(coverage_aliases(item))
        if changed_aliases & covered_aliases:
            matches.append(flow)
    return matches


def harness_command(root: Path, flow: FlowCoverage) -> str:
    data = read_yaml(flow.flow_path)
    tier = data.get("tier", 2)
    if tier == "manual":
        try:
            rel = flow.flow_path.relative_to(root / "desktop/macos").as_posix()
        except ValueError:
            rel = flow.flow_path.as_posix()
        return (
            f"cd desktop/macos && python3 scripts/omi-harness run {rel} "
            f"--lane bridge --port <automation-port>"
        )
    return (
        "cd desktop/macos && ./scripts/desktop-core-harness.sh "
        f"--tier {tier} --bundle omi-core-e2e --port <automation-port> --keep-stack"
    )


def print_report(root: Path, flows: list[FlowCoverage], changed: list[str], strict: bool) -> int:
    desktop_swift = sorted(dict.fromkeys(canonical_path(path) for path in changed if is_desktop_swift_source(path)))
    print("Desktop e2e flow coverage check")
    if not desktop_swift:
        print("No changed desktop Swift source files found.")
        return 0

    covered: list[tuple[str, list[FlowCoverage]]] = []
    uncovered: list[str] = []
    for path in desktop_swift:
        matches = flow_matches(flows, path)
        if matches:
            covered.append((path, matches))
        else:
            uncovered.append(path)

    print(f"Changed desktop Swift files: {len(desktop_swift)}")
    print(f"Covered: {len(covered)}")
    for path, matches in covered:
        names = ", ".join(f"{flow.flow_name} ({flow.flow_path.name})" for flow in matches)
        print(f"  COVERED   {path} -> {names}")

    print(f"Uncovered: {len(uncovered)}")
    for path in uncovered:
        print(f"  UNCOVERED {path}")

    recommended: list[str] = []
    seen: set[Path] = set()
    for _, matches in covered:
        for flow in matches:
            if flow.flow_path not in seen:
                seen.add(flow.flow_path)
                recommended.append(harness_command(root, flow))

    if recommended:
        print("Recommended harness commands:")
        for command in recommended:
            print(f"  {command}")
    else:
        print("Recommended harness commands: add or update a flow covers: entry, then run the relevant flow.")

    if uncovered and strict:
        print(
            "FAIL: uncovered changed desktop Swift files found. Add e2e/flows/*.yaml covers: entries "
            "or rerun without --strict.",
            file=sys.stderr,
        )
        return 1
    if uncovered:
        print("NOTE: uncovered files are advisory unless --strict is passed.")
    return 0


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    changed = args.changed_files or changed_files_from_git(root, args.base, args.staged)
    flows = load_flows(root, Path(args.flows_dir))
    return print_report(root, flows, changed, args.strict)


if __name__ == "__main__":
    sys.exit(main())
