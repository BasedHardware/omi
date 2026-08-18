#!/usr/bin/env python3
"""Reject high-confidence GitHub Actions supply-chain and cache hygiene defects."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

USES_RE = re.compile(r"^\s*-?\s*uses:\s*['\"]?([^\s#'\"]+)")
FLUTTER_CACHE_KEY_RE = re.compile(r"key:\s*.*flutter-buildrunner")
SHA_REF_RE = re.compile(r"@[0-9a-f]{40}$")
# `github.event.inputs.*` is the workflow_dispatch payload; `inputs.*` is the
# same operator selection in workflow_dispatch/workflow_call context. Both name
# a ref the operator chose, which is not what the run SHA describes.
OPERATOR_REF_CHECKOUT_RE = re.compile(
    r"ref:\s*(?:['\"]\s*)?(?:[|>][-+]?\s*)?(?:['\"]\s*)?\$\{\{\s*(?:github\.event\.)?inputs(?:\.|\[\s*['\"][^'\"]+['\"]\s*\])"
)
WORKFLOW_DISPATCH_REF_CHECKOUT_RE = re.compile(
    r"ref:\s*(?:['\"]\s*)?(?:[|>][-+]?\s*)?(?:['\"]\s*)?\$\{\{\s*github\.event\.inputs(?:\.|\[\s*['\"][^'\"]+['\"]\s*\])"
)
RUN_SHA_RE = re.compile(r"GITHUB_SHA|github\.sha")
JOB_START_RE = re.compile(r"^ {2}[A-Za-z_][\w-]*:\s*(?:#.*)?$")
STEP_START_RE = re.compile(r"^(\s*)-\s+")
CHECKOUT_STEP_RE = re.compile(r"^\s*-\s+uses:\s*['\"]?actions/checkout(?:@|['\"]|\s|$)")
CHECKOUT_USES_RE = re.compile(r"^\s+uses:\s*['\"]?actions/checkout(?:@|['\"]|\s|$)")
TRAILING_COMMENT_RE = re.compile(r"\s+#.*$")

# Mutable refs that have already caused (or clearly invite) supply-chain risk.
FORBIDDEN_USES_SUBSTRINGS = (
    "@latest",
    "pypa/gh-action-pypi-publish@release/",
    "dtolnay/rust-toolchain@stable",
    "dtolnay/rust-toolchain@nightly",
    "dtolnay/rust-toolchain@beta",
    "Entelligence-AI/entelligence-pr-reviewer",
)

# Directory names that hold vendored/third-party trees. Workflows inside them
# belong to the upstream project and are not this repository's entrypoints.
PRUNED_DIR_NAMES = frozenset(
    {
        ".git",
        ".pio",
        "node_modules",
        "Pods",
        "build",
        "dist",
        ".dart_tool",
        "venv",
        ".venv",
        "third_party",
        "vendor",
    }
)

# Ratchet: nested workflow directories that predate this guard. GitHub only ever
# runs `.github/workflows` at the repository root, so everything listed here is
# unreachable-by-construction and must shrink, never grow.
# Tracking: https://github.com/BasedHardware/omi/issues/11408
KNOWN_NESTED_WORKFLOW_DIRS = frozenset(
    {
        "desktop/macos/.github/workflows",
        "plugins/omi-github-app/.github/workflows",
    }
)
KNOWN_NESTED_WORKFLOW_FILES = frozenset(
    {
        "desktop/macos/.github/workflows/test-install.yml",
        "plugins/omi-github-app/.github/workflows/create-pr.yml",
    }
)


def _nested_workflow_dirs(root: Path) -> list[str]:
    """Every in-repo `.github/workflows` directory other than the root one."""
    found: list[str] = []
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIR_NAMES]
        current = Path(dirpath)
        if current.name != "workflows" or current.parent.name != ".github":
            continue
        rel = current.relative_to(root).as_posix()
        if rel == ".github/workflows":
            continue
        if _workflow_files_under(current):
            found.append(rel)
    return sorted(found)


def _workflow_files_under(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIR_NAMES]
        for filename in filenames:
            if filename.endswith((".yml", ".yaml")):
                found.append(Path(dirpath) / filename)
    return sorted(found)


def _workflow_paths(root: Path) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml")))


def _action_paths(root: Path) -> list[Path]:
    actions = root / ".github" / "actions"
    if not actions.is_dir():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(actions):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIR_NAMES]
        for filename in filenames:
            if filename in {"action.yml", "action.yaml"}:
                found.append(Path(dirpath) / filename)
    return sorted(found)


def _join_folded_scalars(lines: list[str]) -> list[str]:
    joined = list(lines)
    for index, line in enumerate(lines):
        if not re.search(r"^\s*ref:\s*[|>]", line):
            continue
        base_indent = len(line) - len(line.lstrip())
        parts: list[str] = []
        continuation = index + 1
        while continuation < len(lines):
            candidate = lines[continuation]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= base_indent:
                break
            parts.append(candidate.strip())
            continuation += 1
        joined[index] = f"{line} {' '.join(parts)}"
    return joined


def _property_blocks(lines: list[str], property_name: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    property_re = re.compile(rf"^(\s*)(?:-\s*)?{re.escape(property_name)}:\s*[|>]")
    for index, line in enumerate(lines):
        match = property_re.match(line)
        if not match:
            continue
        base_indent = len(match.group(1))
        parts = [line]
        continuation = index + 1
        while continuation < len(lines):
            candidate = lines[continuation]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= base_indent:
                break
            parts.append(candidate)
            continuation += 1
        blocks.append((index + 1, "\n".join(parts)))
    return blocks


def _operator_ref_scopes(text: str, ref_re: re.Pattern[str], is_workflow: bool) -> set[int]:
    """Line numbers belonging to a scope that checks out an operator-selected ref.

    A job owns one workspace, so provenance is a per-job property: a sibling job
    that checks out the default ref may legitimately use the run SHA.
    """
    lines = _join_folded_scalars(text.splitlines())
    if not is_workflow:
        return set(range(1, len(lines) + 1)) if ref_re.search(text) else set()

    scopes: set[int] = set()
    in_jobs = False
    start = 0
    selected = False
    checkout_step_indent: int | None = None
    current_step_indent: int | None = None

    def close(end: int) -> None:
        if selected and start:
            scopes.update(range(start, end + 1))

    for index, line in enumerate(lines, start=1):
        if not in_jobs:
            if line.rstrip().startswith("jobs:") and not line.startswith(" "):
                in_jobs = True
            continue
        if JOB_START_RE.match(line):
            close(index - 1)
            start, selected, checkout_step_indent, current_step_indent = index, False, None, None
        elif (step_match := STEP_START_RE.match(line)) is not None:
            step_indent = len(step_match.group(1))
            current_step_indent = step_indent
            if CHECKOUT_STEP_RE.match(line):
                checkout_step_indent = step_indent
            else:
                checkout_step_indent = None
        elif (
            current_step_indent is not None
            and len(line) - len(line.lstrip()) > current_step_indent
            and CHECKOUT_USES_RE.match(line)
        ):
            checkout_step_indent = current_step_indent
        elif checkout_step_indent is not None and ref_re.search(line):
            selected = True
    close(len(lines))
    return scopes


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    for nested in _nested_workflow_dirs(root):
        if nested not in KNOWN_NESTED_WORKFLOW_DIRS:
            errors.append(
                f"{nested}: nested GitHub Actions workflows are forbidden; "
                "root .github/workflows/ is the only Actions entrypoint (stale "
                "deploy templates have previously looked like live prod pipelines)"
            )
            continue
        nested_path = root / nested
        for path in _workflow_files_under(nested_path):
            rel = path.relative_to(root).as_posix()
            if rel not in KNOWN_NESTED_WORKFLOW_FILES:
                errors.append(
                    f"{rel}: nested workflow file is not in the ratchet baseline; "
                    "remove it or register the exact legacy file"
                )

    for path in (*_workflow_paths(root), *_action_paths(root)):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        is_workflow = path.parent.name == "workflows"
        # A composite action's `inputs.*` are supplied by the calling workflow,
        # not by an operator, so only the dispatch payload counts there.
        ref_re = OPERATOR_REF_CHECKOUT_RE if is_workflow else WORKFLOW_DISPATCH_REF_CHECKOUT_RE
        operator_ref_scopes = _operator_ref_scopes(text, ref_re, is_workflow)
        lines = text.splitlines()
        for line_number, block in _property_blocks(lines, "key"):
            if "flutter-buildrunner" in block and "github.run_id" in block:
                errors.append(
                    f"{rel}:{line_number}: flutter-buildrunner cache key must not "
                    "include github.run_id (exact key never hits; parallel jobs race)"
                )

        def check_uses(line_number: int, uses: str) -> None:
            for forbidden in FORBIDDEN_USES_SUBSTRINGS:
                if forbidden in uses:
                    errors.append(
                        f"{rel}:{line_number}: mutable or retired action ref "
                        f"{uses!r} is forbidden; pin a full commit SHA "
                        f"(matched {forbidden!r})"
                    )
            if uses.startswith(("actions/", "./")):
                return
            if uses.endswith(("@master", "@main")) and not SHA_REF_RE.search(uses):
                errors.append(
                    f"{rel}:{line_number}: third-party action {uses!r} must not "
                    "track a moving branch; pin a full commit SHA"
                )

        for line_number, block in _property_blocks(lines, "uses"):
            block_lines = block.splitlines()
            first, *continuation = block_lines
            prefix = re.match(r"^(\s*-?\s*uses:)\s*[|>][-+]?\s*", first)
            if prefix is not None:
                synthetic = f"{prefix.group(1)} {' '.join(part.strip() for part in continuation)}"
                match = USES_RE.match(synthetic)
                if match:
                    check_uses(line_number, match.group(1))

        for line_number, line in enumerate(lines, start=1):
            if FLUTTER_CACHE_KEY_RE.search(line) and "github.run_id" in line:
                errors.append(
                    f"{rel}:{line_number}: flutter-buildrunner cache key must not "
                    "include github.run_id (exact key never hits; parallel jobs race)"
                )
            code = TRAILING_COMMENT_RE.sub("", line)
            if line_number in operator_ref_scopes and RUN_SHA_RE.search(code) and not code.lstrip().startswith("#"):
                errors.append(
                    f"{rel}:{line_number}: workflow checks out an operator-selected "
                    "ref, so the run SHA is not the checked-out commit; derive "
                    "provenance from the checked-out tree "
                    "(git rev-parse --short=7 HEAD) instead of GITHUB_SHA/github.sha"
                )

            match = USES_RE.match(line)
            if match:
                check_uses(line_number, match.group(1))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        print("\n".join(errors))
        return 1
    print("GitHub Actions hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
