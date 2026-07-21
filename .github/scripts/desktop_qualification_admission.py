#!/usr/bin/env python3
"""Admit only tag-bound trusted qualification evidence for desktop promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_qualification_run(run: object, repository: str, release_tag: str, candidate_sha: str) -> None:
    """Require a successful same-repository workflow dispatched on the candidate tag."""
    if not isinstance(run, dict):
        raise ValueError("qualification run must be an object")
    required = {
        "conclusion": "success",
        "event": "workflow_dispatch",
        "path": ".github/workflows/desktop_qualify_beta.yml",
        "head_branch": release_tag,
        "head_sha": candidate_sha,
        "name": "Qualify Desktop Beta Candidate",
    }
    for key, expected in required.items():
        if run.get(key) != expected:
            if key == "head_branch":
                raise ValueError("qualification run must execute the candidate tag controls")
            if key == "head_sha":
                raise ValueError("qualification run must execute the candidate source SHA")
            raise ValueError(f"qualification run {key} must equal {expected!r}")
    for key in ("repository", "head_repository"):
        value = run.get(key)
        if not isinstance(value, dict) or value.get("full_name") != repository:
            raise ValueError(f"qualification run {key} must be the trusted repository")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    validate_qualification_run(
        json.loads(args.run_json.read_text(encoding="utf-8")), args.repository, args.release_tag, args.candidate_sha
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
