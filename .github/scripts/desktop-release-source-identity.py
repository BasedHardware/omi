#!/usr/bin/env python3
"""Build fail-closed evidence for a macOS candidate tag's source identity."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCHEMA = "desktop-release-planner-source-identity/v1"


def require_sha(name: str, value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 40-character lowercase SHA")
    return value


def build_evidence(
    *,
    planned_source_sha: str,
    candidate_source_sha: str,
    origin_main_sha: str,
    first_parent_sha: str = "",
    changelog_commit: str = "",
    changelog_pr: str = "",
) -> dict[str, object]:
    """Prove the candidate tag targets the source currently merged on main.

    A consolidated changelog is merged with a regular GitHub merge commit, so
    its first parent must be the CI-gated planner source. A no-op
    consolidation does not create that PR and may tag the planner source only
    when it is still the exact main tip. Either path rejects source drift.
    """
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    candidate_source_sha = require_sha("candidate_source_sha", candidate_source_sha)
    origin_main_sha = require_sha("origin_main_sha", origin_main_sha)

    if candidate_source_sha != origin_main_sha:
        raise ValueError("candidate_source_sha must exactly match fresh origin/main")

    if changelog_commit or changelog_pr or first_parent_sha:
        if not (changelog_commit and changelog_pr and first_parent_sha):
            raise ValueError("merged changelog evidence requires commit, PR URL, and first parent")
        changelog_commit = require_sha("changelog_commit", changelog_commit)
        first_parent_sha = require_sha("first_parent_sha", first_parent_sha)
        if first_parent_sha != planned_source_sha:
            raise ValueError("merged changelog first parent must match the planner source SHA")
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*", changelog_pr):
            raise ValueError("changelog_pr must be a canonical GitHub pull request URL")
        return {
            "schema": SCHEMA,
            "mode": "merged-changelog",
            "planned_source_sha": planned_source_sha,
            "candidate_source_sha": candidate_source_sha,
            "origin_main_sha": origin_main_sha,
            "changelog_commit": changelog_commit,
            "changelog_pr": changelog_pr,
            "first_parent_sha": first_parent_sha,
        }

    if candidate_source_sha != planned_source_sha:
        raise ValueError("direct candidate source must match the planner source SHA")
    return {
        "schema": SCHEMA,
        "mode": "direct",
        "planned_source_sha": planned_source_sha,
        "candidate_source_sha": candidate_source_sha,
        "origin_main_sha": origin_main_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planned-source-sha", required=True)
    parser.add_argument("--candidate-source-sha", required=True)
    parser.add_argument("--origin-main-sha", required=True)
    parser.add_argument("--first-parent-sha", default="")
    parser.add_argument("--changelog-commit", default="")
    parser.add_argument("--changelog-pr", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        evidence = build_evidence(
            planned_source_sha=args.planned_source_sha,
            candidate_source_sha=args.candidate_source_sha,
            origin_main_sha=args.origin_main_sha,
            first_parent_sha=args.first_parent_sha,
            changelog_commit=args.changelog_commit,
            changelog_pr=args.changelog_pr,
        )
    except ValueError as error:
        parser.error(str(error))

    Path(args.output).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"desktop release source identity verified for {evidence['candidate_source_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
