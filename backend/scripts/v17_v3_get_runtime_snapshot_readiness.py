#!/usr/bin/env python3
"""Safe V17-V3-F2 request-scoped runtime snapshot readiness artifact.

This emits a local, read-only contract report for the framework-independent
snapshot builder. It does not import FastAPI routers, read or write Firestore,
call providers/vector stores/network services, emit telemetry, or approve
runtime activation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from utils.memory.v17_v3_get_runtime_snapshot import (  # noqa: E402
    LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS,
    V17V3GetRuntimeSnapshotInput,
    build_v17_v3_get_runtime_snapshot,
)


def _coherent_input(**overrides: Any) -> V17V3GetRuntimeSnapshotInput:
    values: dict[str, Any] = {
        'authenticated_subject_uid': 'sample-subject',
        'control_subject_uid': 'sample-subject',
        'grant_subject_uid': 'sample-subject',
        'projection_subject_uid': 'sample-subject',
        'cursor_subject_uid': 'sample-subject',
        'cohort': 'v17_enrolled',
        'control_generation': 3,
        'default_memory_grant': True,
        'runtime_config_version': 'present',
        'runtime_config_stale': False,
        'account_generation': 3,
        'projection_generation': 3,
        'projection_commit': 'present',
        'projection_converged': True,
        'write_converged': True,
        'delete_converged': True,
        'tombstone_converged': True,
        'cursor_policy_version': 'present',
        'cursor_secret_version': 'present',
        'archive_capability': False,
        'archive_requested': False,
        'deadline_ms': 250,
        'deadline_remaining_ms': 100,
        'read_timestamp_ms': 10_000,
        'server_now_ms': 10_010,
    }
    values.update(overrides)
    return V17V3GetRuntimeSnapshotInput(**values)


def build_report(*, execute: bool = False) -> dict[str, Any]:
    cases = {
        'coherent': _coherent_input(),
        'generation_mismatch': _coherent_input(projection_generation=4),
        'missing_grant': _coherent_input(default_memory_grant=False),
        'archive_without_capability': _coherent_input(archive_requested=True, archive_capability=False),
        'expired_deadline': _coherent_input(deadline_remaining_ms=0),
        'future_read_timestamp': _coherent_input(read_timestamp_ms=12_000),
        'malformed_source': _coherent_input(server_owned_projection=False),
    }
    results = {case_id: build_v17_v3_get_runtime_snapshot(case).log_fields for case_id, case in cases.items()}
    reason_counts: dict[str, int] = {}
    for fields in results.values():
        reason = fields['reason']
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        'script': 'v17_v3_get_runtime_snapshot_readiness',
        'status': 'BLOCKED',
        'proof_status': 'BLOCKED' if execute else 'NOT_RUN',
        'approval': False,
        'read_only': True,
        'route_wiring': False,
        'runtime_behavior_changed': False,
        'production_call_count': 0,
        'firestore_read_count': 0,
        'firestore_write_count': 0,
        'network_call_count': 0,
        'telemetry_sink_call_count': 0,
        'provider_or_vector_call_count': 0,
        'case_count': len(results),
        'reason_counts': reason_counts,
        'low_cardinality_reasons': sorted(LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS),
        'sanitized_case_log_fields': results,
        'non_claims': [
            'No backend/routers/memories.py runtime wiring changed.',
            'No production traffic, Firestore, provider/vector, network, or telemetry calls executed.',
            'No runtime activation or approval claimed.',
            'This local contract proof is not real service evidence.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Emit the same safe BLOCKED local contract report')
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
