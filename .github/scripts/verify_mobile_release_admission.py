#!/usr/bin/env python3
"""Fail closed unless a mobile source has both canonical release proofs.

This verifier is intentionally offline.  A caller (Codemagic or a future tag
admission workflow) supplies a bounded JSON evidence file assembled from its
own authenticated GitHub checks, then passes the requested source explicitly:

    python3 .github/scripts/verify_mobile_release_admission.py \
      --sha "$SOURCE_SHA" --repository "$GITHUB_REPOSITORY" \
      --proof mobile-release-admission.json

The proof document has this normalized shape (additional fields are ignored):

    {
      "schema_version": 1,
      "repository": "BasedHardware/omi",
      "source_sha": "<40 lowercase hex chars>",
      "current_main": {
        "branch": "main",
        "sha": "<40 lowercase hex chars>",
        "source_sha_is_ancestor_of_current_main": true
      },
      "release_eligibility": {
        "workflow_name": "Release Eligibility",
        "workflow_path": ".github/workflows/release-eligibility.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "head_branch": "main",
        "head_sha": "<source_sha>",
        "repository": "BasedHardware/omi"
      },
      "mobile_aggregate": {
        "check_name": "Mobile Release Eligibility",
        "workflow_name": "Mobile App Checks",
        "workflow_path": ".github/workflows/mobile-app-checks.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "<source_sha>",
        "repository": "BasedHardware/omi"
      }
    }

The source may be behind current main, but only when the caller provides
positive ancestry evidence.  This prevents a tag-admission caller from
silently accepting an unrelated or stale branch while allowing main to move
after the proof runs.  The verifier never contacts GitHub and never creates
credentials or store-side effects.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

EXPECTED_REPOSITORY = "BasedHardware/omi"
MAIN_BRANCH = "main"
RELEASE_WORKFLOW_NAME = "Release Eligibility"
RELEASE_WORKFLOW_PATH = ".github/workflows/release-eligibility.yml"
MOBILE_CHECK_NAME = "Mobile Release Eligibility"
MOBILE_WORKFLOW_NAME = "Mobile App Checks"
MOBILE_WORKFLOW_PATH = ".github/workflows/mobile-app-checks.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ZERO_SHA = "0" * 40
MAX_PROOF_BYTES = 1_048_576


class MobileReleaseAdmissionError(ValueError):
    """The requested mobile source lacks an immutable, successful proof."""


def require_full_sha(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value) or value == ZERO_SHA:
        raise MobileReleaseAdmissionError(f"{label} must be a non-zero full 40-character lowercase SHA")
    return value


def _require_object(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise MobileReleaseAdmissionError(f"{label} must be a JSON object")
    return value


def _require_string(mapping: Mapping[str, Any], key: str, expected: str, *, label: str) -> None:
    if mapping.get(key) != expected:
        raise MobileReleaseAdmissionError(f"{label}.{key} must be {expected!r}")


def _require_sha(mapping: Mapping[str, Any], key: str, expected: str, *, label: str) -> None:
    value = require_full_sha(mapping.get(key), label=f"{label}.{key}")
    if value != expected:
        raise MobileReleaseAdmissionError(f"{label}.{key} does not match the requested source SHA")


def _require_repository(mapping: Mapping[str, Any], *, label: str) -> None:
    _require_string(mapping, "repository", EXPECTED_REPOSITORY, label=label)


def validate_mobile_job_results(job_results: object) -> None:
    """Validate optional per-job evidence used to explain the aggregate.

    The workflow deliberately treats a conditionally inapplicable mobile job
    as ``skipped``.  If a caller includes this optional diagnostic map, every
    known job must be present and only ``success`` or ``skipped`` is accepted.
    """

    expected_jobs = {
        "changes",
        "generated-files",
        "analyze-and-test",
        "journeys-hermetic",
        "android-compile-smoke",
        "android-unit-tests",
        "ios-compile-check",
        "dart-tests-kiritimati",
    }
    values = _require_object(job_results, label="mobile_aggregate.job_results")
    if set(values) != expected_jobs:
        raise MobileReleaseAdmissionError("mobile_aggregate.job_results must enumerate every mobile job exactly")
    if values.get("changes") != "success":
        raise MobileReleaseAdmissionError("mobile_aggregate.job_results.changes must be success")
    invalid = {name: result for name, result in values.items() if result not in {"success", "skipped"}}
    if invalid:
        raise MobileReleaseAdmissionError(
            "mobile_aggregate.job_results contains a failed, cancelled, pending, or malformed job"
        )


def _validate_current_main(current_main: object) -> None:
    proof = _require_object(current_main, label="current_main")
    _require_string(proof, "branch", MAIN_BRANCH, label="current_main")
    require_full_sha(proof.get("sha"), label="current_main.sha")
    if proof.get("source_sha_is_ancestor_of_current_main") is not True:
        raise MobileReleaseAdmissionError(
            "current_main.source_sha_is_ancestor_of_current_main must be true"
        )
    # Equality is valid, and a newer main tip is valid only with the explicit
    # ancestry assertion above.  The input is intentionally normalized so the
    # caller, not this verifier, owns the read-only git/API collection step.


def _validate_release_proof(release: object, *, sha: str) -> None:
    proof = _require_object(release, label="release_eligibility")
    label = "release_eligibility"
    _require_string(proof, "workflow_name", RELEASE_WORKFLOW_NAME, label=label)
    _require_string(proof, "workflow_path", RELEASE_WORKFLOW_PATH, label=label)
    _require_string(proof, "event", "push", label=label)
    _require_string(proof, "status", "completed", label=label)
    _require_string(proof, "conclusion", "success", label=label)
    _require_string(proof, "head_branch", MAIN_BRANCH, label=label)
    _require_repository(proof, label=label)
    _require_sha(proof, "head_sha", sha, label=label)
    if type(proof.get("run_attempt")) is not int or proof.get("run_attempt") != 1:
        raise MobileReleaseAdmissionError("release_eligibility.run_attempt must be the first attempt (1)")


def _validate_mobile_aggregate(aggregate: object, *, sha: str) -> None:
    proof = _require_object(aggregate, label="mobile_aggregate")
    label = "mobile_aggregate"
    _require_string(proof, "check_name", MOBILE_CHECK_NAME, label=label)
    _require_string(proof, "workflow_name", MOBILE_WORKFLOW_NAME, label=label)
    _require_string(proof, "workflow_path", MOBILE_WORKFLOW_PATH, label=label)
    _require_string(proof, "event", "push", label=label)
    _require_string(proof, "status", "completed", label=label)
    _require_string(proof, "conclusion", "success", label=label)
    if type(proof.get("run_attempt")) is not int or proof.get("run_attempt") != 1:
        raise MobileReleaseAdmissionError("mobile_aggregate.run_attempt must be the first attempt (1)")
    _require_string(proof, "head_branch", MAIN_BRANCH, label=label)
    _require_repository(proof, label=label)
    _require_sha(proof, "head_sha", sha, label=label)
    if "job_results" in proof:
        validate_mobile_job_results(proof["job_results"])


def validate_admission(payload: object, *, sha: str, repository: str) -> None:
    """Validate one exact source against both required main-branch proofs."""

    require_full_sha(sha, label="release SHA")
    if repository != EXPECTED_REPOSITORY:
        raise MobileReleaseAdmissionError(
            f"repository must be the canonical {EXPECTED_REPOSITORY!r} repository"
        )
    proof = _require_object(payload, label="proof")
    if proof.get("schema_version") != 1:
        raise MobileReleaseAdmissionError("proof.schema_version must be 1")
    _require_string(proof, "repository", EXPECTED_REPOSITORY, label="proof")
    _require_sha(proof, "source_sha", sha, label="proof")
    _validate_current_main(proof.get("current_main"))
    _validate_release_proof(proof.get("release_eligibility"), sha=sha)
    _validate_mobile_aggregate(proof.get("mobile_aggregate"), sha=sha)


def _read_proof(path: Path) -> object:
    raw = path.read_bytes()
    if len(raw) > MAX_PROOF_BYTES:
        raise MobileReleaseAdmissionError("proof exceeds the 1 MiB bounded input limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MobileReleaseAdmissionError("proof is not valid UTF-8 JSON") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="Exact mobile source SHA to admit.")
    parser.add_argument("--repository", required=True, help="Must be BasedHardware/omi.")
    parser.add_argument("--proof", type=Path, required=True, help="Offline normalized JSON evidence file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate_admission(_read_proof(args.proof), sha=args.sha, repository=args.repository)
    except (OSError, MobileReleaseAdmissionError) as exc:
        print(f"mobile release admission failed: {exc}", file=sys.stderr)
        return 1
    print(f"mobile release source admitted: sha={args.sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
