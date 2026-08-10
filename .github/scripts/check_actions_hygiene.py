#!/usr/bin/env python3
"""Reject high-confidence GitHub Actions supply-chain and cache hygiene defects."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
FLUTTER_CACHE_KEY_RE = re.compile(r"key:\s*.*flutter-buildrunner")
SHA_REF_RE = re.compile(r"@[0-9a-f]{40}$")
OPERATOR_REF_CHECKOUT_RE = re.compile(r"ref:\s*\$\{\{\s*github\.event\.inputs\.")
RUN_SHA_RE = re.compile(r"GITHUB_SHA|github\.sha")

# Mutable refs that have already caused (or clearly invite) supply-chain risk.
FORBIDDEN_USES_SUBSTRINGS = (
    "@latest",
    "pypa/gh-action-pypi-publish@release/",
    "dtolnay/rust-toolchain@stable",
    "dtolnay/rust-toolchain@nightly",
    "dtolnay/rust-toolchain@beta",
    "Entelligence-AI/entelligence-pr-reviewer",
)

NESTED_WORKFLOW_DIRS = (
    "backend/.github/workflows",
)


def _workflow_paths(root: Path) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml")))


def _action_paths(root: Path) -> list[Path]:
    actions = root / ".github" / "actions"
    if not actions.is_dir():
        return []
    return sorted(actions.glob("*/action.y*ml"))


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    for nested in NESTED_WORKFLOW_DIRS:
        nested_path = root / nested
        if nested_path.is_dir() and any(nested_path.glob("*.y*ml")):
            errors.append(
                f"{nested}: nested GitHub Actions workflows are forbidden; "
                "root .github/workflows/ is the only Actions entrypoint (stale "
                "deploy templates have previously looked like live prod pipelines)"
            )

    for path in (*_workflow_paths(root), *_action_paths(root)):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        operator_ref_checkout = bool(OPERATOR_REF_CHECKOUT_RE.search(text))
        for line_number, line in enumerate(text.splitlines(), start=1):
            if operator_ref_checkout and RUN_SHA_RE.search(line) and not line.lstrip().startswith("#"):
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
