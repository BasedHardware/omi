#!/usr/bin/env python3
"""Resolve PR metadata, then run the shared deterministic check manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from pr_metadata import PullRequestMetadata, load_from_api, load_from_gh
from run_checks import load_manifest, resolve_checks


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
    output = run_git(root, "diff", "--name-only", "--diff-filter=ACMRD", f"{base}...{head}")
    return [line for line in output.splitlines() if line]


def select_checks(files: list[str], lane: str = "ci") -> list[Check]:
    root = Path(__file__).resolve().parents[2]
    manifest = load_manifest(root / ".github/checks-manifest.yaml")
    return [Check(check.id, check.reason) for check in resolve_checks(manifest, files, lane)]


def format_failure_class_suggest(payload: dict) -> str:
    """Render manual failure-class guidance alongside invariant suggestions.

    Failure classes deliberately do not infer a classification from paths or a
    diff. This formatter therefore supplies the required field and structured
    choices while making the author-owned decision explicit.
    """
    lines = ["## Failure class (fixes)", ""]
    if not payload.get("requires_declaration"):
        lines.extend(
            ["No `fix:` commits were detected; no declaration is required.", ""]
        )
        return "\n".join(lines)

    patch = payload.get("pr_body_patch", {})
    declaration = (
        patch.get("text", "Failure-Class: none\n").strip()
        if isinstance(patch, dict)
        else "Failure-Class: none"
    )
    lines.extend(
        [
            declaration,
            "",
            "<!-- A `fix:` commit is in this diff. Choose manually: this command does not infer a class from paths or diffs.",
            "Before opening the PR, inspect a relevant class with `scripts/failure-class explain FC-<slug> --format json`; replace `none` only if an existing class applies, or use `new` for a genuinely new class.",
            "Available classes:",
        ]
    )
    for candidate in payload.get("advisory_candidates", []):
        if isinstance(candidate, dict):
            lines.append(f"- {candidate['id']}: {candidate['violated_contract']}")
    lines.extend(["-->", ""])
    return "\n".join(lines)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--lane", choices=("local", "ci"), default="ci")
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument("--repository", help="GitHub repository as owner/name; requires --pr-number")
    parser.add_argument("--pr-number", type=int, help="Load current PR metadata through the GitHub API")
    parser.add_argument("--head-branch", help="PR head branch, used for release-changelog policy")
    parser.add_argument("--list", action="store_true", help="Print selected checks without running them")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Print paste-ready product-invariant and failure-class PR guidance for the diff and exit 0",
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
    checks = select_checks(files, args.lane)
    summary = f"PR preflight: lane={args.lane} base={args.base} ({merge_base[:12]}) head={args.head} files={len(files)}"
    print(summary, file=sys.stderr if args.suggest else sys.stdout)
    for check in checks:
        print(f"  SELECTED {check.name}: {check.reason}", file=sys.stderr if args.suggest else sys.stdout)
    if args.list:
        return 0

    with tempfile.TemporaryDirectory(prefix="omi-pr-preflight-") as temp_dir:
        temp = Path(temp_dir)
        files_path = temp / "changed-files.txt"
        files_path.write_text("".join(f"{path}\n" for path in files), encoding="utf-8")
        if args.suggest:
            invariants = subprocess.run(
                [
                    sys.executable,
                    ".github/scripts/check_product_invariants.py",
                    "--changed-files",
                    str(files_path),
                    "--suggest",
                ],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if invariants.stdout:
                print(invariants.stdout, end="")
            if invariants.returncode:
                return invariants.returncode

            suggestion_body = temp / "suggest-pr-body.md"
            suggestion_body.write_text("", encoding="utf-8")
            failure_classes = subprocess.run(
                [
                    sys.executable,
                    "scripts/failure-class",
                    "prepare",
                    "--base",
                    args.base,
                    "--head",
                    args.head,
                    "--pr-body-file",
                    str(suggestion_body),
                    "--format",
                    "json",
                ],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if failure_classes.returncode:
                print("FAIL: failure-class preparation failed.", file=sys.stderr)
                if failure_classes.stdout:
                    print(failure_classes.stdout, end="", file=sys.stderr)
                return failure_classes.returncode
            try:
                payload = json.loads(failure_classes.stdout)
            except json.JSONDecodeError:
                print(
                    "FAIL: failure-class preparation returned invalid JSON.",
                    file=sys.stderr,
                )
                return 1
            print(format_failure_class_suggest(payload), end="")
            return 0

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
        skip_changelog = (
            "no-changelog-needed" in labels
            or head_branch.startswith("changelog/v")
            or os.getenv("PRE_PUSH_SKIP_DESKTOP_CHANGELOG") == "1"
        )
        if metadata:
            print(f"PR metadata: {metadata.source}, updated_at={metadata.updated_at}")
        elif any(check.name == "product-invariants" for check in checks):
            print("PR metadata: none (product-invariants will use an empty body)")

        body_path = temp / "pr-body.txt"
        body_path.write_text(metadata.body if metadata else "", encoding="utf-8")
        command = [
            sys.executable,
            ".github/scripts/run_checks.py",
            "--lane",
            args.lane,
            "--base",
            args.base,
            "--head",
            args.head,
            "--changed-files",
            str(files_path),
            "--pr-body-file",
            str(body_path),
        ]
        if skip_changelog:
            command.append("--skip-changelog")
        result = subprocess.run(command, cwd=root, check=False)

    elapsed = time.monotonic() - started
    if result.returncode:
        print(f"PR preflight failed in {elapsed:.2f}s.", file=sys.stderr)
        return result.returncode
    print(f"PR preflight passed: {len(checks)} checks in {elapsed:.2f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
