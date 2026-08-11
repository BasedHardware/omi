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
OPERATOR_REF_CHECKOUT_RE = re.compile(r"ref:\s*\$\{\{\s*(?:github\.event\.)?inputs\.")
WORKFLOW_DISPATCH_REF_CHECKOUT_RE = re.compile(r"ref:\s*\$\{\{\s*github\.event\.inputs\.")
RUN_SHA_RE = re.compile(r"GITHUB_SHA|github\.sha")
JOB_START_RE = re.compile(r"^ {2}[A-Za-z_][\w-]*:\s*(?:#.*)?$")
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
        if any(current.glob("*.yml")) or any(current.glob("*.yaml")):
            found.append(rel)
    return sorted(found)


def _workflow_paths(root: Path) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml")))


def _action_paths(root: Path) -> list[Path]:
    actions = root / ".github" / "actions"
    if not actions.is_dir():
        return []
    return sorted(actions.glob("*/action.y*ml"))


def _operator_ref_scopes(text: str, ref_re: re.Pattern[str], is_workflow: bool) -> set[int]:
    """Line numbers belonging to a scope that checks out an operator-selected ref.

    A job owns one workspace, so provenance is a per-job property: a sibling job
    that checks out the default ref may legitimately use the run SHA.
    """
    lines = text.splitlines()
    if not is_workflow:
        return set(range(1, len(lines) + 1)) if ref_re.search(text) else set()

    scopes: set[int] = set()
    in_jobs = False
    start = 0
    selected = False

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
            start, selected = index, False
        elif ref_re.search(line):
            selected = True
    close(len(lines))
    return scopes


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    for nested in _nested_workflow_dirs(root):
        if nested in KNOWN_NESTED_WORKFLOW_DIRS:
            continue
        errors.append(
            f"{nested}: nested GitHub Actions workflows are forbidden; "
            "root .github/workflows/ is the only Actions entrypoint (stale "
            "deploy templates have previously looked like live prod pipelines)"
        )

    for path in (*_workflow_paths(root), *_action_paths(root)):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        is_workflow = path.parent.name == "workflows"
        # A composite action's `inputs.*` are supplied by the calling workflow,
        # not by an operator, so only the dispatch payload counts there.
        ref_re = OPERATOR_REF_CHECKOUT_RE if is_workflow else WORKFLOW_DISPATCH_REF_CHECKOUT_RE
        operator_ref_scopes = _operator_ref_scopes(text, ref_re, is_workflow)
        for line_number, line in enumerate(text.splitlines(), start=1):
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
                uses = match.group(1)
                for forbidden in FORBIDDEN_USES_SUBSTRINGS:
                    if forbidden in uses:
                        errors.append(
                            f"{rel}:{line_number}: mutable or retired action ref "
                            f"{uses!r} is forbidden; pin a full commit SHA "
                            f"(matched {forbidden!r})"
                        )
                if uses.startswith(("actions/", "./")):
                    pass
                elif uses.endswith(("@master", "@main")) and not SHA_REF_RE.search(uses):
                    errors.append(
                        f"{rel}:{line_number}: third-party action {uses!r} must not "
                        "track a moving branch; pin a full commit SHA"
                    )

            if FLUTTER_CACHE_KEY_RE.search(line) and "github.run_id" in line:
                errors.append(
                    f"{rel}:{line_number}: flutter-buildrunner cache key must not "
                    "include github.run_id (exact key never hits; parallel jobs race)"
                )

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
