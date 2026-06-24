"""Canonical alias module for ``utils.memory.v17_v3_dev_cloud_proof`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_dev_cloud_proof import (
    DEV_FIXTURE_SOURCE,
    DevCloudPreflight,
    DevCloudTarget,
    GATE_STATUS_BLOCKED,
    GATE_STATUS_NOT_RUN,
    GATE_STATUS_READY_TO_EXECUTE,
    PROOF_MATRIX,
    REQUIRED_ARTIFACTS,
    ROUTE_SCOPE,
    build_candidate_manifest,
    build_checksums,
    build_dev_cloud_fixture_bundle,
    build_proof_matrix,
    build_review_template,
    build_target_preflight_report,
    evaluate_target_preflight,
    redacted_env_snapshot,
    sha256_file,
    split_csv,
    target_from_env,
    write_artifact,
    write_prepared_bundle,
)

__all__ = [
    "DEV_FIXTURE_SOURCE",
    "DevCloudPreflight",
    "DevCloudTarget",
    "GATE_STATUS_BLOCKED",
    "GATE_STATUS_NOT_RUN",
    "GATE_STATUS_READY_TO_EXECUTE",
    "PROOF_MATRIX",
    "REQUIRED_ARTIFACTS",
    "ROUTE_SCOPE",
    "build_candidate_manifest",
    "build_checksums",
    "build_dev_cloud_fixture_bundle",
    "build_proof_matrix",
    "build_review_template",
    "build_target_preflight_report",
    "evaluate_target_preflight",
    "redacted_env_snapshot",
    "sha256_file",
    "split_csv",
    "target_from_env",
    "write_artifact",
    "write_prepared_bundle",
]
