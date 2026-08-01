#!/usr/bin/env python3
"""Admit only tag-bound trusted qualification evidence for desktop promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


def validate_qualification_run(
    run: object,
    repository: str,
    release_tag: str,
    candidate_sha: str,
    *,
    require_tag_binding: bool = False,
) -> None:
    """Require a successful trusted qualification run for the candidate.

    A workflow dispatch can start from the candidate tag (the normal planner
    path) or from ``main`` (a manual dispatch). The workflow's own isolated
    checkout and the evidence artifact bind the latter to the exact tag; only
    the tag-dispatched path can use GitHub's workflow-run SHA as that proof.

    ``require_tag_binding`` is for callers that do NOT independently verify the
    qualification evidence artifact. Without that artifact the ``main`` arm
    proves nothing about which candidate ran, so those callers must demand the
    tag-dispatched run whose own head SHA is the candidate.
    """
    if not isinstance(run, dict):
        raise ValueError("qualification run must be an object")
    required = {
        "status": "completed",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "path": ".github/workflows/desktop_qualify_beta.yml",
        "name": "Qualify Desktop Beta Candidate",
    }
    for key, expected in required.items():
        if run.get(key) != expected:
            raise ValueError(f"qualification run {key} must equal {expected!r}")
    head_branch = run.get("head_branch")
    head_sha = run.get("head_sha")
    if head_branch == release_tag:
        if head_sha != candidate_sha:
            raise ValueError("qualification run must execute the candidate source SHA")
    elif head_branch == "main":
        if require_tag_binding:
            raise ValueError("qualification run must be dispatched from the candidate tag to bind it to this release")
        if not isinstance(head_sha, str) or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
            raise ValueError("manual qualification run must have an immutable dispatch SHA")
    else:
        raise ValueError("qualification run must execute the candidate tag controls or trusted main controls")
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
    parser.add_argument("--require-tag-binding", action="store_true")
    args = parser.parse_args()
    validate_qualification_run(
        json.loads(args.run_json.read_text(encoding="utf-8")),
        args.repository,
        args.release_tag,
        args.candidate_sha,
        require_tag_binding=args.require_tag_binding,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
