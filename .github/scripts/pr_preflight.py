#!/usr/bin/env python3
"""Run fast, deterministic pull-request contract checks."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from pr_metadata import PullRequestMetadata, load_from_api, load_from_gh


@dataclass(frozen=True)
class Check:
    name: str
    reason: str


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def changed_files(root: Path, base: str, head: str) -> list[str]:
    output = run_git(root, "diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}")
    return [line for line in output.splitlines() if line]


def select_checks(files: list[str]) -> list[Check]:
    checks = [
        Check("diff-hygiene", "all PRs"),
        Check("architecture-guardrails", "all PRs"),
        Check("product-invariants", "all PRs; changed paths determine required citations"),
        Check("desktop-changelog-data", "repository-wide changelog schema contract"),
    ]
    if any(path.startswith("desktop/macos/") for path in files):
        checks.append(Check("desktop-changelog-entry", "desktop files changed"))
    if any(path.startswith("desktop/macos/Desktop/Sources/") and path.endswith(".swift") for path in files):
        checks.append(Check("desktop-e2e-flow-coverage", "desktop Swift sources changed"))
    return checks


def resolve_pr_metadata(
    root: Path,
    body_file: Path | None,
    repository: str | None,
    pr_number: int | None,
) -> PullRequestMetadata | None:
    if body_file is None:
        env_body = os.getenv("OMI_PR_BODY_FILE", "").strip()
        if env_body:
            body_file = Path(env_body)
    if body_file:
        resolved = body_file.expanduser()
        if not resolved.is_file():
            raise RuntimeError(f"PR body file not found: {resolved}")
        return PullRequestMetadata(
            number=0,
            body=resolved.read_text(encoding="utf-8"),
            updated_at="local file",
            labels=(),
            source=str(resolved.resolve()),
        )
    if repository and pr_number:
        return load_from_api(repository, pr_number, os.getenv("GITHUB_TOKEN", ""))
    try:
        return load_from_gh(root)
    except RuntimeError as exc:
        print(f"PR metadata: unavailable ({exc})")
        print("If invariant citations are required, rerun with --pr-body-file <draft.md>")
        print("or set OMI_PR_BODY_FILE, or run: scripts/pr-preflight --suggest")
        return None


def command_for_check(
    check: Check,
    files_path: Path,
    base: str,
    head: str,
    body_path: Path,
    skip_changelog: bool,
) -> list[str]:
    python = sys.executable
    commands = {
        "architecture-guardrails": [
            python,
            ".github/scripts/check_arch_guardrails.py",
            "--changed-files",
            str(files_path),
        ],
        "product-invariants": [
            python,
            ".github/scripts/check_product_invariants.py",
            "--changed-files",
            str(files_path),
            "--pr-body-file",
            str(body_path),
        ],
        "desktop-changelog-data": [python, ".github/scripts/desktop-changelog.py", "validate"],
        "desktop-changelog-entry": [
            python,
            ".github/scripts/check-desktop-changelog.py",
            "--base",
            base,
            "--head",
            head,
            *(["--skip"] if skip_changelog else []),
        ],
        "desktop-e2e-flow-coverage": [
            python,
            "desktop/macos/scripts/check-e2e-flow-coverage.py",
            "--strict",
            *files_path.read_text(encoding="utf-8").splitlines(),
        ],
    }
    return commands[check.name]


def check_diff_hygiene(root: Path, base: str, head: str, files: list[str]) -> int:
    diff_check = subprocess.run(["git", "diff", "--check", f"{base}...{head}"], cwd=root, check=False)
    if diff_check.returncode:
        return diff_check.returncode
    failed = False
    for path in files:
        result = subprocess.run(
            ["git", "grep", "-n", "-I", "-E", "^(<<<<<<<|>>>>>>>)", head, "--", path],
            cwd=root,
            check=False,
        )
        if result.returncode == 0:
            failed = True
    if failed:
        print("FAIL: unresolved merge conflict markers found in changed files", file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument("--repository", help="GitHub repository as owner/name; requires --pr-number")
    parser.add_argument("--pr-number", type=int, help="Load current PR metadata through the GitHub API")
    parser.add_argument("--head-branch", help="PR head branch, used for release-changelog policy")
    parser.add_argument("--list", action="store_true", help="Print selected checks without running them")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Print a paste-ready product-invariants PR body section for the diff and exit 0",
    )
    parser.add_argument("--root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.repository) != bool(args.pr_number):
        print("FAIL: --repository and --pr-number must be supplied together", file=sys.stderr)
        return 2
    root = (args.root or Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel"))).resolve()
    started = time.monotonic()
    try:
        merge_base = run_git(root, "merge-base", args.base, args.head)
        files = changed_files(root, args.base, args.head)
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: could not resolve preflight diff: {exc.stderr.strip()}", file=sys.stderr)
        return 1
    checks = select_checks(files)
    summary = f"PR preflight: base={args.base} ({merge_base[:12]}) head={args.head} files={len(files)}"
    selected_lines = [f"  SELECTED {check.name}: {check.reason}" for check in checks]
    if args.suggest:
        print(summary, file=sys.stderr)
        for line in selected_lines:
            print(line, file=sys.stderr)
    else:
        print(summary)
        for line in selected_lines:
            print(line)
    if args.list:
        return 0

    with tempfile.TemporaryDirectory(prefix="omi-pr-preflight-") as temp_dir:
        temp = Path(temp_dir)
        files_path = temp / "changed-files.txt"
        files_path.write_text("".join(f"{path}\n" for path in files), encoding="utf-8")

        if args.suggest:
            suggest = subprocess.run(
                [
                    sys.executable,
                    ".github/scripts/check_product_invariants.py",
                    "--changed-files",
                    str(files_path),
                    "--suggest",
                ],
                cwd=root,
                check=False,
            )
            return suggest.returncode

        try:
            metadata = resolve_pr_metadata(root, args.pr_body_file, args.repository, args.pr_number)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        labels = metadata.labels if metadata else ()
        head_branch = args.head_branch or os.getenv("GITHUB_HEAD_REF", "")
        if not head_branch:
            head_branch = subprocess.run(
                ["git", "symbolic-ref", "--short", "-q", "HEAD"],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
        skip_changelog = "no-changelog-needed" in labels or head_branch.startswith("changelog/v")
        if metadata:
            print(f"PR metadata: {metadata.source}, updated_at={metadata.updated_at}")
        elif any(check.name == "product-invariants" for check in checks):
            print("PR metadata: none (product-invariants will use an empty body)")

        body_path = temp / "pr-body.txt"
        body_path.write_text(metadata.body if metadata else "", encoding="utf-8")
        failures: list[str] = []
        for check in checks:
            phase_started = time.monotonic()
            print(f"==> {check.name}", flush=True)
            if check.name == "diff-hygiene":
                returncode = check_diff_hygiene(root, args.base, args.head, files)
            else:
                command = command_for_check(check, files_path, args.base, args.head, body_path, skip_changelog)
                returncode = subprocess.run(command, cwd=root, check=False).returncode
            elapsed = time.monotonic() - phase_started
            status = "PASS" if returncode == 0 else "FAIL"
            print(f"<== {status} {check.name} ({elapsed:.2f}s)", flush=True)
            if returncode:
                failures.append(check.name)
                break

    elapsed = time.monotonic() - started
    if failures:
        print(f"PR preflight failed in {elapsed:.2f}s: {', '.join(failures)}", file=sys.stderr)
        if "product-invariants" in failures:
            print(
                "Remediation: scripts/pr-preflight --suggest  # paste into PR body / draft, then re-run",
                file=sys.stderr,
            )
        return 1
    print(f"PR preflight passed: {len(checks)} checks in {elapsed:.2f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
