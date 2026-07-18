#!/usr/bin/env python3
"""Reject version-prefixed source filenames outside their version package."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import PurePosixPath

ISSUE_URL = "https://github.com/BasedHardware/omi/issues/9443"
VERSIONED_FILENAME = re.compile(r"^(?P<version>v[0-9]+)_.+\.(?:py|swift|ts|rs)$")

GRANDFATHERED_VIOLATIONS = {
    "backend/scripts/v3_dev_cloud_proof.py",
    "backend/scripts/v3_dev_cloud_readiness.py",
    "backend/scripts/v3_f5_real_service_evidence_readiness.py",
    "backend/scripts/v3_f6_pre_gcp_aggregate_readiness.py",
    "backend/scripts/v3_limited_rollout_config.py",
    "backend/testing/memory/v3_canary_approval.py",
    "backend/testing/memory/v3_f5_evidence.py",
    "backend/testing/memory/v3_f6/__init__.py",
    "backend/testing/memory/v3_f6/_validation.py",
    "backend/testing/memory/v3_f6/aggregate.py",
    "backend/testing/memory/v3_f6/audit.py",
    "backend/testing/memory/v3_f6/config.py",
    "backend/testing/memory/v3_f6/fingerprints.py",
    "backend/testing/memory/v3_f6/identity_iam.py",
    "backend/testing/memory/v3_f6/local_defaults.py",
    "backend/testing/memory/v3_f6/local_doubles.py",
    "backend/testing/memory/v3_f6/local_smoke.py",
    "backend/testing/memory/v3_f6/pre_gcp_aggregate.py",
    "backend/testing/memory/v3_f6/protocol.py",
    "backend/testing/memory/v3_f6/read_evidence.py",
    "backend/testing/memory/v3_f6/readonly_contracts.py",
    "backend/testing/memory/v3_f6/redaction.py",
    "backend/testing/memory/v3_f6/run_context.py",
    "backend/testing/memory/v3_f6/run_record.py",
    "backend/testing/memory/v3_get_dependency_seam.py",
    "backend/testing/memory/v3_get_runtime_snapshot.py",
    "backend/testing/memory/v3_local_telemetry.py",
    "backend/testing/memory/v3_route_planner.py",
    "backend/tests/unit/v3_prod_read_probes/__init__.py",
    "backend/tests/unit/v3_prod_read_probes/canary_approval_production.py",
    "backend/tests/unit/v3_prod_read_probes/cursor_secret_production.py",
    "backend/tests/unit/v3_prod_read_probes/projection_write_convergence.py",
    "backend/tests/unit/v3_prod_read_probes/runtime_config_source.py",
    "backend/tests/unit/v3_router_probes/__init__.py",
    "backend/tests/unit/v3_router_probes/fail_closed_matrix.py",
    "backend/tests/unit/v3_router_probes/fastapi_route_contract.py",
    "backend/tests/unit/v3_router_probes/get_dependency_auth.py",
    "backend/tests/unit/v3_router_probes/in_process.py",
    "backend/tests/unit/v3_router_probes/real_router_dependency_map.py",
    "backend/tests/unit/v3_router_probes/real_router_get_testclient.py",
    "backend/tests/unit/v3_router_probes/route_signature_integration.py",
    "backend/tests/unit/v3_router_probes/stubs.py",
}


def is_versioned_filename(path: str) -> bool:
    return bool(VERSIONED_FILENAME.fullmatch(PurePosixPath(path).name))


def is_in_versioned_package(path: str) -> bool:
    match = VERSIONED_FILENAME.fullmatch(PurePosixPath(path).name)
    return bool(match and match.group("version") in PurePosixPath(path).parts[:-1])


def violations(paths: Iterable[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if is_versioned_filename(path) and not is_in_versioned_package(path) and path not in GRANDFATHERED_VIOLATIONS
    )


def tracked_paths() -> list[str]:
    return subprocess.check_output(["git", "ls-files"], text=True).splitlines()


def main() -> int:
    invalid_paths = violations(tracked_paths())
    if not invalid_paths:
        print("OK: no new version-prefixed source filenames outside version packages.")
        return 0

    print(f"FAIL: version goes in the package path, not the filename — see {ISSUE_URL}.")
    for path in invalid_paths:
        print(f"  - {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
