#!/usr/bin/env python3
"""Validate the immutable Pusher artifact selected from a dev qualification run.

The production workflow downloads a small, non-secret attestation artifact from
the selected development Pusher deployment run.  This verifier binds the digest
to that successful run's immutable source identity before the workflow can copy
the image to the production registry or mutate the production Helm release.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
SCHEMA_VERSION = 1


class EvidenceError(ValueError):
    """The selected development run cannot prove a safe promotion."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"could not read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path}: expected a JSON object")
    return value


def validate(
    evidence: dict[str, Any],
    run: dict[str, Any],
    *,
    expected_digest: str,
    expected_repository: str,
    expected_workflow_id: int,
    expected_run_id: int,
) -> list[str]:
    """Return every missing immutable-promotion proof without exposing secrets."""

    errors: list[str] = []
    expected_fields = {
        "schema_version",
        "environment",
        "image_digest",
        "image_repository",
        "run_id",
        "source_sha",
        "workflow",
    }
    if set(evidence) != expected_fields:
        errors.append("qualification evidence has an unexpected schema")
    if evidence.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"qualification evidence must use schema_version={SCHEMA_VERSION}")
    if evidence.get("environment") != "development":
        errors.append("qualification evidence must be from the development environment")
    if evidence.get("workflow") != "gcp_backend_pusher_auto_deploy.yml":
        errors.append("qualification evidence must be emitted by the automatic dev Pusher workflow")

    digest = evidence.get("image_digest")
    if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        errors.append("qualification evidence must contain an exact sha256 image_digest")
    elif digest != expected_digest:
        errors.append("requested production digest does not match development qualification evidence")
    if not DIGEST_RE.fullmatch(expected_digest):
        errors.append("requested production digest must be an exact sha256 digest")

    if evidence.get("image_repository") != expected_repository:
        errors.append("qualification evidence repository does not match the development Pusher registry")
    if evidence.get("run_id") != expected_run_id:
        errors.append("qualification evidence run_id does not match the selected workflow run")

    source_sha = evidence.get("source_sha")
    if not isinstance(source_sha, str) or not SHA_RE.fullmatch(source_sha):
        errors.append("qualification evidence must contain a full lowercase source SHA")
    if run.get("id") != expected_run_id:
        errors.append("selected workflow API result does not match the requested run id")
    if run.get("workflow_id") != expected_workflow_id:
        errors.append("selected workflow run is not the automatic dev Pusher workflow")
    if run.get("event") != "push" or run.get("head_branch") != "main":
        errors.append("selected workflow run must be a main push qualification")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        errors.append("selected workflow run did not complete successfully")
    if isinstance(source_sha, str) and run.get("head_sha") != source_sha:
        errors.append("qualification evidence source SHA does not match the successful workflow run")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-workflow-id", type=int, required=True)
    parser.add_argument("--expected-run-id", type=int, required=True)
    args = parser.parse_args()

    try:
        failures = validate(
            load_json(args.evidence),
            load_json(args.run_json),
            expected_digest=args.expected_digest,
            expected_repository=args.expected_repository,
            expected_workflow_id=args.expected_workflow_id,
            expected_run_id=args.expected_run_id,
        )
    except EvidenceError as exc:
        failures = [str(exc)]
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: selected Pusher digest is bound to a successful development qualification run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
