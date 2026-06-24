#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Sequence

SHARED_NAMESPACE = "ns2"

LOCAL_SEAMS_AND_RUNNERS = {
    "provider_readiness": "backend/scripts/vector_search_provider_readiness.py",
    "shared_ns2_isolation_readiness": "backend/scripts/shared_ns2_legacy_isolation_readiness.py",
    "pinecone_repair_validation_readiness": "backend/scripts/pinecone_repair_validation_readiness.py",
    "repair_outbox_telemetry": "backend/database/v17_vector_repair_outbox_telemetry.py",
    "repair_outbox_worker": "backend/database/v17_vector_repair_outbox_worker.py",
    "repair_outbox_records": "backend/database/v17_vector_repair_outbox.py",
    "vector_metadata_gateway": "backend/database/v17_vector_metadata.py",
    "vector_search_service": "backend/utils/memory/v17_vector_search_service.py",
}

PROOF_MATRIX: Dict[str, Dict[str, Any]] = {
    "projection_commit_id_parity": {
        "status": "NOT_RUN",
        "scope": "Prove projection_commit_id parity across users/{uid}/memory_items, vector metadata, vector repair outbox records, and repaired vectors.",
        "required_artifacts": [
            "Read-only inventory joining memory_items.projection_commit_id with vector metadata projection_commit_id for each candidate memory_id.",
            "Repair outbox record sample showing required_projection_commit_id and stale_projection repair/delete reason for mismatches.",
            "Post-repair convergence artifact proving no returned vector has a missing or stale projection_commit_id.",
        ],
        "pass_fail_criteria": "PASS only when every returned/repaired vector exactly matches authoritative memory_items projection_commit_id; missing/stale projection metadata is rejected and repair-queued or deleted before return.",
        "evidence": [],
    },
    "account_generation_parity": {
        "status": "NOT_RUN",
        "scope": "Prove account_generation parity across control-plane generation, memory_items, vector metadata, outbox records, and repaired vectors.",
        "required_artifacts": [
            "Read-only current account_generation source-of-truth artifact from V17 rollout/control state.",
            "Candidate inventory proving vector metadata account_generation equals current required account_generation and authoritative memory_items account_generation.",
            "Purge/repair outbox evidence for stale-generation vectors after account purge or generation bump.",
        ],
        "pass_fail_criteria": "PASS only when stale-generation candidates are never returned and stale-generation physical vectors converge to deleted/repaired state without cross-generation data leakage.",
        "evidence": [],
    },
    "item_revision_source_commit_content_hash_parity": {
        "status": "NOT_RUN",
        "scope": "Prove item_revision/source_commit_id/content_hash parity across memory_items, vector metadata, and repaired vectors.",
        "required_artifacts": [
            "Read-only candidate inventory comparing item_revision, source_commit_id, and content_hash from vector metadata to users/{uid}/memory_items/{memory_id}.",
            "Hydration reject/repair reason counts for stale_vector, missing_vector_freshness_metadata, and stale_item_revision_or_content.",
            "Post-worker convergence artifact proving repaired vectors carry current item_revision/source_commit_id/content_hash metadata.",
        ],
        "pass_fail_criteria": "PASS only when missing or mismatched item_revision/source_commit_id/content_hash rejects before return and leaves no stale physical vector after repair convergence.",
        "evidence": [],
    },
    "tombstone_deleted_source_handling": {
        "status": "NOT_RUN",
        "scope": "Prove tombstone/deleted source handling takes delete precedence over repair and never resurrects deleted content.",
        "required_artifacts": [
            "Read-only memory_items/source-state inventory for tombstoned/deleted/purged sources and matching physical vectors.",
            "Repair worker decision artifact proving delete action, not repair/upsert, for missing authoritative item, tombstone, deleted source, or purged generation.",
            "No returned default vector results for tombstoned/deleted sources; Archive default-unavailable remains preserved.",
        ],
        "pass_fail_criteria": "PASS only when tombstoned/deleted source vectors are deleted or quarantined, never repaired into active vectors, and never returned by default search.",
        "evidence": [],
    },
    "stale_physical_vector_detection": {
        "status": "NOT_RUN",
        "scope": "Prove stale physical vector IDs from old tier/revision/source projections are detected before return and queued for repair/purge.",
        "required_artifacts": [
            "Physical vector inventory grouped by memory_id, tier, item_revision, source_commit_id, content_hash, and projection_commit_id.",
            "Hydration reject output with vector_id surfaced as repair/purge candidate for stale physical IDs.",
            "pinecone_repair_validation_readiness.py execution artifact in an approved throwaway namespace, plus read-only shared ns2 stale-candidate inventory.",
        ],
        "pass_fail_criteria": "PASS only when stale physical vectors cannot consume returned slots silently and converge to deleted or repaired current vectors within the worker SLO.",
        "evidence": [],
    },
    "duplicate_vector_detection": {
        "status": "NOT_RUN",
        "scope": "Prove duplicate physical vectors for one memory_id are detected, de-duplicated in returns, and converged by repair.",
        "required_artifacts": [
            "Read-only provider inventory grouping duplicate vector_id candidates by memory_id and freshness tuple.",
            "Result uniqueness artifact proving at most one returned memory per authoritative memory_id after hydration/refill.",
            "Repair outbox/worker convergence artifact showing stale duplicates deleted and current duplicate repaired once idempotently.",
        ],
        "pass_fail_criteria": "PASS only when duplicate stale vectors neither duplicate returned memories nor suppress fresh recall, and worker convergence leaves one current vector per required projection.",
        "evidence": [],
    },
    "repair_outbox_enqueue_dead_letter_backlog": {
        "status": "NOT_RUN",
        "scope": "Prove vector repair outbox enqueue/dead-letter/backlog handling is durable, idempotent, observable, and bounded.",
        "required_artifacts": [
            "Firestore/outbox evidence for deterministic users/{uid}/memory_outbox/{record_id} enqueue with stable idempotency_key.",
            "Retry and dead-letter evidence from vector repair worker with sanitized errors and max_attempts behavior.",
            "Backlog telemetry artifact from v17_vector_repair_outbox_telemetry.py including pending count, oldest age, retry/dead-letter totals, and no high-cardinality labels.",
        ],
        "pass_fail_criteria": "PASS only when enqueue is idempotent, retries/dead-letter are bounded and visible centrally, backlog alerts exist, and no repair event is silently dropped.",
        "evidence": [],
    },
    "repair_worker_convergence": {
        "status": "NOT_RUN",
        "scope": "Prove repair worker convergence for delete and repair actions under retries, lease contention, and partial provider failure.",
        "required_artifacts": [
            "Worker tick execution artifact over prepared pending records covering delete, repair, skip, retry, dead_letter, and ack failure outcomes.",
            "Post-run provider/read-only inventory proving stale vectors removed or repaired with current metadata and no pending eligible backlog remains beyond SLO.",
            "Lease contention/emulator or cloud proof that concurrent workers do not double-apply non-idempotent operations.",
        ],
        "pass_fail_criteria": "PASS only when all eligible stale/deleted/duplicate candidates converge to completed or explicit dead_letter with alertable backlog, without unsafe broad provider mutation.",
        "evidence": [],
    },
    "shared_ns2_legacy_v17_isolation_under_stale_candidates": {
        "status": "NOT_RUN",
        "scope": "Prove shared ns2 legacy/V17 isolation under stale candidates, duplicate V17 candidates, and legacy fallback surfaces.",
        "required_artifacts": [
            "shared_ns2_legacy_isolation_readiness.py read-only provider evidence showing legacy filters exclude v17_schema_version records before top-k.",
            "vector_search_provider_readiness.py evidence for V17 overfetch/refill when stale V17 candidates appear in shared ns2.",
            "Legacy baseline recall comparison proving V17 stale/deleted/duplicate physical IDs do not consume legacy result slots.",
        ],
        "pass_fail_criteria": "PASS only when legacy ns2 paths exclude V17 records, V17 paths reject stale legacy/cross-schema records, and stale candidates do not cause unsafe fallback or silent recall loss.",
        "evidence": [],
    },
    "no_silent_data_loss": {
        "status": "NOT_RUN",
        "scope": "Prove no silent data loss across stale Short-term, Archive default-unavailable, tombstones, malformed metadata, duplicates, partial outages, and repair convergence.",
        "required_artifacts": [
            "No-silent-data-loss matrix covering stale Short-term not default-visible, Archive default-unavailable, tombstones/deleted sources, stale physical vectors, duplicates, malformed metadata, and partial outages.",
            "Recall/precision/latency benchmark output anchored to Base Omi and V17 default-read policy with no legacy unsafe fallback.",
            "Repair convergence and backlog evidence proving rejected-but-repairable vectors either converge or are explicit dead_letter with central alerting.",
        ],
        "pass_fail_criteria": "PASS only when every excluded/failed candidate is explainable by policy, benchmarked recall stays within approved budget, no authoritative live memory disappears silently, and rollback/alerts are proven.",
        "evidence": [],
    },
}

NON_CLAIMS = [
    "Oracle verdict remains BLOCK production rollout / NO-GO.",
    "This T20 repair/projection-consistency readiness matrix is NOT_RUN/BLOCKED and does not claim production approval.",
    "Default and execute modes are read-only inventory only; no network/provider/cloud calls are executed and no mutations are planned.",
    "No Pinecone upsert/delete/update, Firestore create/set/update/delete, benchmark run, telemetry sink integration, or cutover approval is performed by this artifact.",
    "Archive remains default-unavailable and stale Short-term remains not default-visible.",
]


@dataclass(frozen=True)
class T20RepairProjectionConsistencyReadinessConfig:
    execute: bool


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe T20 repair/projection-consistency readiness/proof matrix. It inventories required evidence without provider calls."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Emit the same read-only matrix; does not call providers."
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> T20RepairProjectionConsistencyReadinessConfig:
    return T20RepairProjectionConsistencyReadinessConfig(execute=bool(args.execute))


def build_readiness_artifact(config: T20RepairProjectionConsistencyReadinessConfig) -> Dict[str, Any]:
    return {
        "status": "BLOCKED",
        "read_only": True,
        "mutation_allowed": False,
        "execute_requested": config.execute,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "benchmark_evidence_collected": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "shared_namespace": SHARED_NAMESPACE,
        "consistency_fields": [
            "projection_commit_id",
            "account_generation",
            "item_revision",
            "source_commit_id",
            "content_hash",
        ],
        "authoritative_surfaces": [
            "users/{uid}/memory_items/{memory_id}",
            "vector metadata in shared ns2",
            "users/{uid}/memory_outbox/{record_id} vector repair outbox",
            "vector repair worker convergence output",
        ],
        "local_seams_and_runners": LOCAL_SEAMS_AND_RUNNERS,
        "proof_matrix": PROOF_MATRIX,
        "planned_safe_commands": [
            "python3 backend/scripts/t20_repair_projection_consistency_readiness.py",
            "python3 backend/scripts/t20_repair_projection_consistency_readiness.py --execute",
            "python3 backend/scripts/vector_search_provider_readiness.py --execute with approved read-only provider credentials",
            "python3 backend/scripts/shared_ns2_legacy_isolation_readiness.py --execute with approved read-only Pinecone credentials",
            "python3 backend/scripts/pinecone_repair_validation_readiness.py --execute --allow-throwaway-mutation only in a confirmed throwaway namespace, never shared ns2",
        ],
        "required_summary": "projection_commit_id/account_generation/item_revision/source_commit_id/content_hash parity; repair outbox enqueue/dead-letter/backlog; shared ns2 legacy/V17 isolation under stale candidates",
        "non_claims": NON_CLAIMS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    print(json.dumps(build_readiness_artifact(config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
