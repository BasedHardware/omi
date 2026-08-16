#!/usr/bin/env python3
"""Reject unapproved growth of oversized product-source files.

The target branch is the ratchet. For every changed Swift, Rust, or backend
Python source, this check compares ``--base`` with the synthetic merge of
``--base`` and ``--head``.
Reductions therefore become the next ceiling automatically after merge, and
unrelated pull requests never edit a shared line-count ledger.

Exceptional growth must be declared precisely in pull-request metadata:

``Line-Count-Exception: path | BASE -> CURRENT | reason``

The path and both counts must match the actual diff. Stale, duplicate, unused,
or malformed declarations fail closed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

THRESHOLD = 1500
EXCEPTION_PREFIX = "Line-Count-Exception:"
EXCEPTION_RE = re.compile(
    r"^Line-Count-Exception:\s*(?P<path>[^|]+?)\s*\|\s*"
    r"(?P<base>\d+)\s*->\s*(?P<current>\d+)\s*\|\s*(?P<reason>\S.*)$"
)
DESKTOP_ROOT = "desktop/macos/"
BACKEND_ROOT = "backend/"
VENDORED_PARTS = {
    ".git",
    ".build",
    ".venv",
    "venv",
    "vendor",
    "vendored",
    "third_party",
    "third-party",
    "node_modules",
    "Pods",
    "Carthage",
    "target",
}
TEST_PARTS = {"test", "tests", "Tests"}
@dataclass(frozen=True)
class LineCountException:
    path: str
    base_count: int
    current_count: int
    reason: str
    line_number: int


def clean_git_env() -> dict[str, str]:
    # Hooks and nested Git commands may export repository-specific variables beyond the familiar
    # GIT_DIR/GIT_WORK_TREE pair (for example GIT_COMMON_DIR or GIT_INDEX_FILE). None are inputs to
    # this check, so drop the entire Git namespace before operating on the explicit ``cwd`` repo.
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def repo_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def is_product_source(relative: str) -> bool:
    path = PurePosixPath(relative)
    parts = path.parts
    if path.is_absolute() or not parts or any(part in {".", ".."} for part in parts):
        return False
    if any(part in VENDORED_PARTS or part == "Generated" for part in parts):
        return False
    if any(part in TEST_PARTS for part in parts):
        return False
    name = path.name
    if ".gen." in name or ".g." in name or name.startswith("test_") or name.endswith("_test.py"):
        return False
    if relative.startswith(BACKEND_ROOT):
        return path.suffix == ".py"
    if relative.startswith(DESKTOP_ROOT):
        return path.suffix in {".swift", ".rs"}
    return False


def line_count_text(source: str) -> int:
    return source.count("\n") + (0 if not source or source.endswith("\n") else 1)


def source_count(root: Path, relative: str) -> int | None:
    path = root / relative
    return line_count_text(path.read_text(encoding="utf-8")) if path.is_file() else None


def verify_commit(root: Path, ref: str, label: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=clean_git_env(),
    )
    if result.returncode:
        raise ValueError(f"cannot resolve {label} commit {ref!r}: {result.stderr.strip()}")


def synthetic_merge_tree(root: Path, base: str, head: str) -> str:
    result = subprocess.run(
        ["git", "merge-tree", "--write-tree", base, head],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=clean_git_env(),
    )
    if result.returncode:
        details = (result.stderr or result.stdout).strip()
        raise ValueError(f"cannot measure the synthetic merge of {head} into {base}: {details}")
    tree = result.stdout.splitlines()[0].strip() if result.stdout else ""
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", tree):
        raise ValueError(f"git merge-tree returned an invalid tree id for {head} and {base}")
    return tree


def source_count_at_ref(root: Path, ref: str, relative: str) -> int | None:
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{relative}"],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=clean_git_env(),
    )
    if exists.returncode:
        return None
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=clean_git_env(),
    )
    if result.returncode:
        raise ValueError(f"cannot read {relative} at {ref}: {result.stderr.strip()}")
    return line_count_text(result.stdout)


def read_changed_files(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def changed_product_sources(changed: set[str]) -> list[str]:
    return sorted(relative for relative in changed if is_product_source(relative))


def parse_exceptions(body: str) -> tuple[dict[str, LineCountException], list[str]]:
    exceptions: dict[str, LineCountException] = {}
    failures: list[str] = []
    for line_number, raw_line in enumerate(body.splitlines(), start=1):
        if not raw_line.lstrip().startswith(EXCEPTION_PREFIX):
            continue
        match = EXCEPTION_RE.fullmatch(raw_line.strip())
        if match is None:
            failures.append(
                f"PR body line {line_number}: malformed {EXCEPTION_PREFIX} declaration; expected "
                "'Line-Count-Exception: path | BASE -> CURRENT | reason'"
            )
            continue
        relative = match.group("path").strip()
        reason = match.group("reason").strip()
        if not is_product_source(relative):
            failures.append(f"PR body line {line_number}: unsupported product source path {relative!r}")
            continue
        if len(reason) < 12 or len(reason) > 500:
            failures.append(f"PR body line {line_number}: exception reason must be 12-500 characters")
            continue
        if relative in exceptions:
            failures.append(f"PR body line {line_number}: duplicate exception for {relative}")
            continue
        exceptions[relative] = LineCountException(
            path=relative,
            base_count=int(match.group("base")),
            current_count=int(match.group("current")),
            reason=reason,
            line_number=line_number,
        )
    return exceptions, failures


def requires_exception(base_count: int | None, current_count: int | None) -> bool:
    if current_count is None or current_count < THRESHOLD:
        return False
    return current_count > (base_count or 0)


def evaluate_changes(
    root: Path,
    base: str,
    changed: set[str],
    exceptions: dict[str, LineCountException],
    *,
    candidate_ref: str | None = None,
) -> list[str]:
    failures: list[str] = []
    used: set[str] = set()
    for relative in changed_product_sources(changed):
        current = (
            source_count_at_ref(root, candidate_ref, relative)
            if candidate_ref is not None
            else source_count(root, relative)
        )
        base_value = source_count_at_ref(root, base, relative)
        if not requires_exception(base_value, current):
            continue
        expected_base = base_value or 0
        exception = exceptions.get(relative)
        if exception is None:
            failures.append(
                f"{relative}: grew from {expected_base} to {current} lines against {base}. Split the file, or add "
                f"'Line-Count-Exception: {relative} | {expected_base} -> {current} | reason' to the PR body."
            )
            continue
        used.add(relative)
        if exception.base_count != expected_base or exception.current_count != current:
            failures.append(
                f"PR body line {exception.line_number}: {relative} declares "
                f"{exception.base_count} -> {exception.current_count}, but the diff is {expected_base} -> {current}"
            )

    for relative, exception in exceptions.items():
        if relative in used:
            continue
        if relative not in changed:
            failures.append(f"PR body line {exception.line_number}: unused exception for unchanged source {relative}")
            continue
        current = (
            source_count_at_ref(root, candidate_ref, relative)
            if candidate_ref is not None
            else source_count(root, relative)
        )
        base_value = source_count_at_ref(root, base, relative)
        failures.append(
            f"PR body line {exception.line_number}: unused exception for {relative}; current/base counts "
            f"{current}/{base_value or 0} do not require approval"
        )
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Repository root (default: inferred from this script)")
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument(
        "--base",
        required=True,
        help="Current target-branch commit used as the line-count ceiling",
    )
    parser.add_argument(
        "--head",
        required=True,
        help="Candidate commit merged with --base before source lines are counted",
    )
    parser.add_argument(
        "--pr-body-file",
        type=Path,
        help="PR body containing exact Line-Count-Exception entries",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    try:
        verify_commit(root, args.base, "base")
        verify_commit(root, args.head, "head")
        candidate_tree = synthetic_merge_tree(root, args.base, args.head)
        changed = read_changed_files(args.changed_files)
        body = args.pr_body_file.read_text(encoding="utf-8") if args.pr_body_file else ""
        exceptions, failures = parse_exceptions(body)
        failures.extend(
            evaluate_changes(
                root,
                args.base,
                changed,
                exceptions,
                candidate_ref=candidate_tree,
            )
        )
    except (OSError, UnicodeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    if failures:
        print("FAIL: product file line-count ratchet", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    count = len(changed_product_sources(changed))
    print(f"OK: no unapproved line-count increase across {count} changed product source file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
