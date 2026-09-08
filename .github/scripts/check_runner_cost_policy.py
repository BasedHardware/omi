#!/usr/bin/env python3
"""Reject paid GitHub-hosted runner labels in this public repository."""

from __future__ import annotations

import argparse
from pathlib import Path

PAID_RUNNER_LABELS = ("ubuntu-latest-m",)


def validate(root: Path) -> list[str]:
    workflows = root / ".github" / "workflows"
    errors: list[str] = []
    for path in sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml"))):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for label in PAID_RUNNER_LABELS:
                if label in line:
                    errors.append(
                        f"{path.relative_to(root)}:{line_number}: paid runner label {label!r} "
                        "is forbidden; public-repository jobs must use a standard runner"
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
    print("GitHub runner cost policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
