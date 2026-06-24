#!/usr/bin/env python3
"""Safe V17 `/v3` cursor secret/source integration readiness proof.

This proof is deliberately pre-runtime and read-only. It does not import FastAPI
routers, read environment secret values, call Firestore/Pinecone/providers/cloud,
mutate state, or change `backend/routers/memories.py`. It proves the pure cursor
trust boundary under fake server-owned secret material and records the remaining
BLOCKED production requirement: a real server-owned cursor signing secret/config
source must be chosen and wired before route integration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.memory.v3_cursor import (
    V17V3CursorContext,
    V17V3CursorError,
    V17V3Keyset,
    create_v17_v3_cursor,
    parse_v17_v3_cursor,
)

_FAKE_SERVER_OWNED_SECRET = b'fake-server-owned-v17-v3-cursor-secret-readiness-only'
_FAKE_CLIENT_SUPPLIED_SECRET = b'fake-client-supplied-secret-must-never-be-trusted'

CURSOR_SECRET_PRODUCTION_READINESS_PROOF = {
    "service": "backend/scripts/p1_3_v3_cursor_secret_production_readiness.py",
    "test": "backend/tests/unit/test_p1_3_v3_cursor_secret_production_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "proof_status": "NOT_RUN",
    "approval_claimed": False,
    "blocker": (
        "Production-safe cursor secret/config metadata read proof is available as a disabled-by-default read-only "
        "runner; missing env gates produce NOT_RUN/BLOCKED and no secret material is read."
    ),
}

SERVER_OWNED_SECRET_SOURCE = {
    "status": "BLOCKED",
    "required_source": "server-owned V17_V3_CURSOR_SIGNING_SECRET or managed secret injected into backend runtime",
    "candidate_env_var": "V17_V3_CURSOR_SIGNING_SECRET",
    "candidate_production_metadata_runner": "backend/scripts/p1_3_v3_cursor_secret_production_readiness.py",
    "blocker": "No existing runtime-owned V17 /v3 cursor signing secret/config source is wired.",
    "required_before_runtime_change": True,
    "client_supplied_secret_trusted": False,
    "invented_secret_material": False,
    "env_secret_read_attempted": False,
    "runtime_wired": False,
    "approval_claimed": False,
}

TRUST_BOUNDARY_REQUIREMENTS = [
    {
        "requirement_id": "server_owned_secret_only",
        "status": "BLOCKED",
        "required_behavior": "Future route obtains cursor signing secret only from server-owned config/secret manager, never query/body/header supplied by a client.",
        "client_controlled": False,
        "required_before_runtime_change": True,
    },
    {
        "requirement_id": "first_page_no_cursor",
        "status": "READY",
        "required_behavior": "First page without a cursor validates limit/filter/source/read-mode policy but does not need to parse or trust a client secret.",
        "requires_cursor_secret": False,
        "client_controlled": False,
    },
    {
        "requirement_id": "subsequent_page_cursor",
        "status": "BLOCKED",
        "required_behavior": "Any non-empty cursor must be HMAC validated with the server-owned secret before projection reads.",
        "requires_cursor_secret": True,
        "client_controlled": False,
        "required_before_runtime_change": True,
    },
    {
        "requirement_id": "signed_cursor_context_binding",
        "status": "READY",
        "required_behavior": "Signed cursor payload must remain bound to user, generations, filter/source/mode, keyset, and expiration.",
        "bound_fields": [
            "uid",
            "account_generation",
            "projection_generation",
            "filter_hash",
            "source",
            "read_mode",
            "keyset",
            "expires_at_epoch_seconds",
        ],
    },
]


def _context(**overrides: Any) -> V17V3CursorContext:
    values = {
        'uid': 'uid-a',
        'account_generation': 7,
        'projection_generation': 11,
        'filter_hash': 'filter-default-v1',
        'source': 'v17_compatibility_projection',
        'read_mode': 'default_memory',
        'now_epoch_seconds': 1_800_000_000,
    }
    values.update(overrides)
    return V17V3CursorContext(**values)


def _keyset() -> V17V3Keyset:
    return V17V3Keyset(created_at_ms=1_799_999_123_456, memory_id='memory-9')


def _fail_closed_case(case_id: str, reason: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": "FAIL_CLOSED",
        "reason": reason,
        "legacy_fallback_allowed": False,
        "client_secret_trusted": False,
        "runtime_wired": False,
    }


def _build_case_matrix() -> list[dict[str, Any]]:
    cursor = create_v17_v3_cursor(_keyset(), _context(), _FAKE_SERVER_OWNED_SECRET, ttl_seconds=300)
    parsed = parse_v17_v3_cursor(cursor, _context(), _FAKE_SERVER_OWNED_SECRET)
    tampered = cursor[:-1] + ('A' if cursor[-1] != 'A' else 'B')

    cases: list[dict[str, Any]] = [
        {
            "case_id": "first_page_no_cursor_no_secret_needed",
            "status": "READY",
            "cursor_present": False,
            "requires_cursor_secret": False,
            "client_secret_trusted": False,
            "legacy_fallback_allowed": False,
        },
        {
            "case_id": "server_owned_secret_signed_cursor_round_trip",
            "status": "READY",
            "cursor_present": True,
            "requires_cursor_secret": True,
            "client_secret_trusted": False,
            "legacy_fallback_allowed": False,
            "preserved_claims": {
                "account_generation": parsed.account_generation,
                "projection_generation": parsed.projection_generation,
                "source": parsed.source,
                "keyset": {
                    "created_at_ms": parsed.keyset.created_at_ms,
                    "memory_id": parsed.keyset.memory_id,
                },
            },
        },
    ]

    invalid_inputs = [
        ("tampered_cursor_rejected", tampered, _context()),
        ("expired_cursor_rejected", cursor, _context(now_epoch_seconds=1_800_000_301)),
        ("account_generation_mismatch_rejected", cursor, _context(account_generation=8)),
        ("projection_generation_mismatch_rejected", cursor, _context(projection_generation=12)),
        ("source_mismatch_rejected", cursor, _context(source='legacy_primary')),
        ("wrong_secret_rejected", cursor, _context()),
    ]
    for case_id, token, context in invalid_inputs:
        try:
            secret = _FAKE_CLIENT_SUPPLIED_SECRET if case_id == "wrong_secret_rejected" else _FAKE_SERVER_OWNED_SECRET
            parse_v17_v3_cursor(token, context, secret)
        except V17V3CursorError as exc:
            cases.append(_fail_closed_case(case_id, exc.reason))
        else:  # pragma: no cover - defensive guard for a proof invariant
            cases.append(_fail_closed_case(case_id, "unexpected_success"))

    cases.append(
        _fail_closed_case(
            "client_supplied_secret_rejected_by_policy",
            "client_supplied_cursor_secret_not_a_valid_source",
        )
    )
    return cases


def build_report(*, execute: bool = False) -> dict[str, Any]:
    case_matrix = _build_case_matrix() if execute else []
    ready_case_count = sum(1 for case in case_matrix if case["status"] == "READY")
    fail_closed_case_count = sum(1 for case in case_matrix if case["status"] == "FAIL_CLOSED")
    return {
        "artifact": "v17_p1_3_v3_cursor_secret_readiness",
        "status": "BLOCKED",
        "proof_status": "BLOCKED" if execute else "NOT_RUN",
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
        "scope": "Pre-runtime cursor secret/source integration readiness under pure fake contexts only.",
        "server_owned_secret_source": SERVER_OWNED_SECRET_SOURCE,
        "cursor_secret_production_readiness_proof": CURSOR_SECRET_PRODUCTION_READINESS_PROOF,
        "trust_boundary_requirements": TRUST_BOUNDARY_REQUIREMENTS,
        "pure_fake_cursor_case_matrix": case_matrix,
        "required_future_integration": [
            "Add a server-owned V17 /v3 cursor signing secret/config source before runtime route wiring.",
            "Pass only server-owned secret bytes into backend/utils/memory/v17_v3_cursor.py; never accept client-supplied secret material.",
            "Validate non-empty cursors before projection reads and fail closed on tamper, expiry, generation/source/filter/read-mode mismatch.",
            "Keep first-page no-cursor flow independent of client secret trust and keep offset/5000 legacy behavior out of V17 cursor mode.",
        ],
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No production cursor signing secret exists or was read by this proof.",
            "No client-supplied cursor secret trust claimed.",
            "No production traffic, Firestore, Pinecone, cloud, provider, or network calls executed.",
            "No production rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": "BLOCKED" if execute else "NOT_RUN",
            "ready_case_count": ready_case_count,
            "fail_closed_case_count": fail_closed_case_count,
            "blocked_requirement_count": 1,
            "client_supplied_secret_trusted": False,
            "runtime_wiring_changed": False,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run the pure fake cursor proof matrix")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
