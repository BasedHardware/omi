#!/usr/bin/env python3
"""Enforce architecture maps for oversized source packages.

Existing mapless packages are grandfathered at their committed source-file
count. They emit warnings until documented. A new oversized package, or growth
past a grandfathered count, fails with guidance to add a package-root map.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ISSUE_URL = "https://github.com/BasedHardware/omi/issues/9446"
DEFAULT_THRESHOLD = 12
MAP_NAMES = ("ARCHITECTURE.md", "README.md")
SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".dart",
    ".h",
    ".hpp",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".py",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
SKIP_SUFFIXES = (".gen.dart", ".g.dart", ".lock", ".min.js")
SKIP_PARTS = {".git", ".next", ".venv", "__pycache__", "build", "dist", "node_modules", "target"}


@dataclass(frozen=True)
class Finding:
    package: str
    source_count: int
    baseline_count: int | None
    level: str
    message: str


def source_file(path: Path) -> bool:
    if path.suffix not in SOURCE_EXTENSIONS:
        return False
    if path.name.endswith(SKIP_SUFFIXES):
        return False
    return not any(part in SKIP_PARTS for part in path.parts)


def package_roots(repo_root: Path) -> list[Path]:
    """Return intentionally non-overlapping package roots covered by the ratchet."""

    backend_utils = repo_root / "backend" / "utils"
    packages = sorted(path for path in backend_utils.iterdir() if path.is_dir()) if backend_utils.is_dir() else []
    agent_source = repo_root / "desktop" / "macos" / "agent" / "src"
    if agent_source.is_dir():
        packages.append(agent_source)
    return packages


def source_count(package_root: Path) -> int:
    return sum(1 for path in package_root.rglob("*") if path.is_file() and source_file(path))


def has_architecture_map(package_root: Path) -> bool:
    return any((package_root / name).is_file() for name in MAP_NAMES)


def load_baseline(path: Path) -> dict[str, int]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read package architecture baseline {path}: {exc}") from exc
    return parse_baseline(raw, label=str(path))


def parse_baseline(raw: str, *, label: str) -> dict[str, int]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot parse package architecture baseline {label}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("packages"), dict):
        raise ValueError(f"invalid package architecture baseline schema: {label}")
    baseline: dict[str, int] = {}
    for raw_package, raw_count in payload["packages"].items():
        if not isinstance(raw_package, str) or isinstance(raw_count, bool) or not isinstance(raw_count, int):
            raise ValueError(f"invalid package architecture baseline entry: {raw_package!r}: {raw_count!r}")
        baseline[raw_package] = raw_count
    return baseline


def load_baseline_at_ref(repo_root: Path, ref: str) -> dict[str, int] | None:
    """Load the trusted baseline from a PR base; None means first-time bootstrap."""

    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if verify.returncode:
        raise ValueError(f"cannot resolve package architecture baseline ref {ref}: {verify.stderr.strip()}")
    baseline_path = ".github/scripts/package_architecture_baseline.json"
    result = subprocess.run(
        ["git", "show", f"{ref}:{baseline_path}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        return None
    return parse_baseline(result.stdout, label=f"{ref}:{baseline_path}")


def baseline_change_findings(current: Mapping[str, int], previous: Mapping[str, int] | None) -> list[Finding]:
    """Reject self-grandfathering while allowing baseline shrinkage and removal."""

    if previous is None:
        return []
    findings: list[Finding] = []
    for package, current_count in sorted(current.items()):
        previous_count = previous.get(package)
        if previous_count is not None and current_count <= previous_count:
            continue
        if previous_count is None:
            message = (
                f"{package} was added to the architecture-map baseline at {current_count}. New oversized packages "
                f"must add ARCHITECTURE.md or README.md instead of grandfathering themselves. See {ISSUE_URL}"
            )
        else:
            message = (
                f"{package}'s architecture-map baseline increased from {previous_count} to {current_count}. "
                f"Add ARCHITECTURE.md or README.md instead of raising the baseline. See {ISSUE_URL}"
            )
        findings.append(Finding(package, current_count, previous_count, "error", message))
    return findings


def evaluate_packages(repo_root: Path, baseline: Mapping[str, int], threshold: int) -> list[Finding]:
    findings: list[Finding] = []
    for package_root in package_roots(repo_root):
        relative = package_root.relative_to(repo_root).as_posix()
        count = source_count(package_root)
        if count <= threshold or has_architecture_map(package_root):
            continue
        baseline_count = baseline.get(relative)
        if baseline_count is None:
            message = (
                f"{relative} has {count} source files (threshold: {threshold}) and no package-root "
                f"ARCHITECTURE.md or README.md. Add a map before this package grows further. See {ISSUE_URL}"
            )
            level = "error"
        elif count > baseline_count:
            message = (
                f"{relative} grew from its grandfathered {baseline_count} source files to {count} without a "
                f"package-root ARCHITECTURE.md or README.md. Add a map or revert the growth. See {ISSUE_URL}"
            )
            level = "error"
        else:
            message = (
                f"{relative} remains grandfathered without an architecture map at {count} source files "
                f"(baseline: {baseline_count}); add ARCHITECTURE.md or README.md opportunistically."
            )
            level = "warning"
        findings.append(Finding(relative, count, baseline_count, level, message))
    return findings


def annotation_escape(value: object) -> str:
    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit_finding(finding: Finding) -> None:
    title = "Package architecture map required" if finding.level == "error" else "Package needs architecture map"
    print(
        f"::{finding.level} file={annotation_escape(finding.package)},line=1,title={annotation_escape(title)}::"
        f"{annotation_escape(finding.message)}"
    )


def write_summary(findings: list[Finding], threshold: int) -> None:
    lines = [
        "## Package architecture maps",
        "",
        f"Packages over {threshold} source files require a package-root `ARCHITECTURE.md` or `README.md`.",
        "",
    ]
    if not findings:
        lines.append("All oversized packages have maps or remain below the threshold.")
    else:
        lines.extend(["| Level | Package | Source files |", "| --- | --- | ---: |"])
        lines.extend(f"| {item.level} | {item.package} | {item.source_count} |" for item in findings)
    summary = "\n".join(lines) + "\n"
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(summary)
    else:
        print(summary, end="")


def run(
    *,
    repo_root: Path,
    baseline_path: Path,
    threshold: int = DEFAULT_THRESHOLD,
    previous_baseline: Mapping[str, int] | None = None,
) -> int:
    try:
        baseline = load_baseline(baseline_path)
    except ValueError as exc:
        print(f"::error title=Invalid package architecture baseline::{annotation_escape(exc)}")
        return 1
    findings = baseline_change_findings(baseline, previous_baseline)
    findings.extend(evaluate_packages(repo_root, baseline, threshold))
    for finding in findings:
        emit_finding(finding)
    write_summary(findings, threshold)
    return 1 if any(finding.level == "error" for finding in findings) else 0


def main() -> int:
    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--base", help="Git revision whose baseline cannot be increased or extended")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()
    repo_root = args.root.resolve()
    baseline_path = args.baseline or repo_root / ".github" / "scripts" / "package_architecture_baseline.json"
    try:
        previous_baseline = load_baseline_at_ref(repo_root, args.base) if args.base else None
    except ValueError as exc:
        print(f"::error title=Invalid package architecture baseline::{annotation_escape(exc)}")
        return 1
    return run(
        repo_root=repo_root,
        baseline_path=baseline_path,
        threshold=args.threshold,
        previous_baseline=previous_baseline,
    )


if __name__ == "__main__":
    raise SystemExit(main())
