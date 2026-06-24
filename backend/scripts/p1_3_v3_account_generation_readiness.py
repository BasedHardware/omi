#!/usr/bin/env python3
"""Safe V17 `/v3` trusted account-generation source/readiness artifact.

This artifact identifies the independent server-owned account-generation source
that future `GET /v3/memories` wiring must use for `expected_account_generation`
and records local writer/emulator evidence for its state-head document. It
intentionally does not import FastAPI routers, call providers, wire runtime
behavior, or claim production rollout approval.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

TRUSTED_ACCOUNT_GENERATION_SOURCE = {
    "source_id": "trusted_memory_state_head",
    "canonical_path": "users/{uid}/memory_state/head",
    "reader_contract": "backend/utils/memory/v17_v3_account_generation_source.py",
    "writer": "backend/database/v17_memory_apply_store.py",
    "unit_test": "backend/tests/unit/test_v3_account_generation_source.py",
    "writer_unit_test": "backend/tests/unit/test_firestore_apply_store.py",
    "emulator_test": "backend/scripts/firestore_python_apply_emulator_test.py",
    "rules_emulator_test": "backend/scripts/firestore_rules_emulator_test.mjs",
    "npm_emulator_command": "npm run test:v17-v3-state-head:emulator",
    "schema_version": 1,
    "required_source_field": "v17_memory_state_head",
    "required_fields": ["uid", "schema_version", "source", "account_generation", "head_commit_id", "commit_sequence"],
    "server_owned": True,
    "independent_from_control_doc": True,
    "independent_from_projection_doc": True,
    "client_supplied_generation_trusted": False,
    "used_for_runtime_expected_generation_now": False,
    "runtime_wired": False,
    "production_rollout_approved": False,
}

STATE_HEAD_WRITER_EMULATOR_EVIDENCE = {
    "status": "LOCAL_WRITER_EMULATOR_PROVED_RUNTIME_BLOCKED",
    "writer_path": "backend/database/v17_memory_apply_store.py",
    "writer_function": "_write_apply_result",
    "materializes_from": "committed MemoryControlState returned by apply_long_term_patch_transaction",
    "lockstep_fields": ["uid", "account_generation", "head_commit_id", "commit_sequence", "updated_at"],
    "reader_contract_fields": TRUSTED_ACCOUNT_GENERATION_SOURCE["required_fields"],
    "server_owned": True,
    "client_rules_denial_proof": "backend/scripts/firestore_rules_emulator_test.mjs",
    "admin_emulator_writer_reader_proof": "backend/scripts/firestore_python_apply_emulator_test.py",
    "npm_emulator_command": "npm run test:v17-v3-state-head:emulator",
    "runtime_wired": False,
    "production_rollout_approved": False,
}

FUTURE_ROUTE_GENERATION_REQUIREMENTS = {
    "expected_account_generation_source": "trusted_memory_state_head_reader",
    "must_equal": [
        "trusted_account_generation",
        "control_state.account_generation",
        "projection_state.account_generation",
        "cursor.account_generation_when_present",
    ],
    "forbidden_shortcuts": [
        "copy_control_state_account_generation_into_expected_account_generation",
        "copy_projection_state_account_generation_into_expected_account_generation",
        "trust_client_supplied_expected_account_generation",
    ],
    "fail_closed_reasons": [
        "missing_state_head",
        "malformed_state_head",
        "uid_mismatch",
        "source_mismatch",
        "unsupported_schema",
        "malformed_account_generation",
        "read_failed",
        "trusted_control_projection_cursor_generation_mismatch",
    ],
    "runtime_wired": False,
}

REMAINING_RUNTIME_BLOCKER = {
    "blocker_id": "runtime_route_integration_and_remaining_gates_missing",
    "status": "BLOCKED",
    "required_before_runtime_change": (
        "Runtime GET /v3 route wiring, remaining gate evidence, telemetry/approval, and real route fail-closed "
        "integration are still required before changing backend/routers/memories.py."
    ),
    "safe_local_contract_proved": True,
    "safe_local_writer_emulator_proved": True,
    "runtime_wired": False,
    "approval_claimed": False,
}

NON_CLAIMS = [
    "No backend/routers/memories.py change.",
    "No runtime /v3 behavior change.",
    "No production rollout approval.",
    "No production Firestore/cloud/provider/vector calls.",
    "No client-supplied generation trust.",
    "No copying observed control/projection generation into expected generation.",
    "No legacy fallback/merge for V17 failures.",
]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    proof_status = "LOCAL_WRITER_EMULATOR_PROVED_RUNTIME_BLOCKED" if execute else "NOT_RUN"
    return {
        "artifact": "v17_p1_3_v3_account_generation_readiness",
        "status": "BLOCKED",
        "proof_status": proof_status,
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "routers_memories_modified": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "trusted_account_generation_source": TRUSTED_ACCOUNT_GENERATION_SOURCE,
        "state_head_writer_emulator_evidence": STATE_HEAD_WRITER_EMULATOR_EVIDENCE,
        "future_route_generation_requirements": FUTURE_ROUTE_GENERATION_REQUIREMENTS,
        "remaining_runtime_blocker": REMAINING_RUNTIME_BLOCKER,
        "non_claims": NON_CLAIMS,
        "summary": {
            "status": "BLOCKED",
            "proof_status": proof_status,
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "approval_claimed": False,
            "trusted_source_identified": True,
            "state_head_writer_emulator_proved": execute,
            "remaining_runtime_blocker_count": 1,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe report with execute=true")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
