#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

SHARED_NAMESPACE = "ns2"

REQUIRED_ENVIRONMENT = {
    "pinecone": ["PINECONE_API_KEY", "PINECONE_INDEX_NAME", "PINECONE_INDEX_HOST"],
    "firestore": ["MEMORY_PROVIDER_PROOF_FIRESTORE_PROJECT", "MEMORY_PROVIDER_PROOF_UID"],
}

PROOF_CASES: Dict[str, Dict[str, Any]] = {
    "provider_pagination_refill_semantics": {
        "status": "NOT_RUN",
        "goal": "Prove real Pinecone top-k windows/refill behavior preserves memory recall after stale/malformed candidates.",
        "planned_read_only_evidence": [
            "Run bounded read-only Pinecone candidate queries at increasing limits against an explicit proof uid.",
            "Compare candidate counts, duplicate vector ids, rejected metadata counts, and refill stop reasons.",
        ],
        "evidence": [],
    },
    "provider_vector_query_timeout_behavior": {
        "status": "NOT_RUN",
        "goal": "Prove provider-level query timeout semantics and local deadline handling under slow/failed reads.",
        "planned_read_only_evidence": [
            "Measure read-only vector query elapsed time with configured local timeout controls.",
            "Record whether the provider client exposes/request-honors per-call timeout settings without mutation.",
        ],
        "evidence": [],
    },
    "firestore_candidate_hydration_read_counts": {
        "status": "NOT_RUN",
        "goal": "Prove candidate-ID hydration uses bounded Firestore document reads, not full collection scans.",
        "planned_read_only_evidence": [
            "Inventory exact users/{uid}/memory_items/{memory_id} document-get attempts for vector candidates.",
            "Compare attempted reads to max_candidate_hydration_reads and returned/rejected result counts.",
        ],
        "evidence": [],
    },
    "malformed_or_stale_metadata": {
        "status": "NOT_RUN",
        "goal": "Prove malformed/stale vector metadata is rejected before authoritative return and does not trigger unsafe purge claims when unread.",
        "planned_read_only_evidence": [
            "Read-only inventory of candidate metadata missing projection_commit_id, content_hash, source_commit_id, or item_revision.",
            "Hydration decision counts for stale_projection, stale_vector, access_denied, and missing_authoritative_item.",
        ],
        "evidence": [],
    },
    "cross_user_hits": {
        "status": "NOT_RUN",
        "goal": "Prove cross-user vector hits are filtered by provider metadata and fail closed again during hydration.",
        "planned_read_only_evidence": [
            "Attempt read-only proof query for one uid and count any candidate metadata uid mismatch.",
            "Confirm mismatched uid candidates are never returned as authoritative memory items.",
        ],
        "evidence": [],
    },
    "expired_short_term": {
        "status": "NOT_RUN",
        "goal": "Prove expired Short-term candidates do not return through default memory vector search.",
        "planned_read_only_evidence": [
            "Inventory candidate memory_tier=short_term with expires_at/lifecycle state past active window.",
            "Confirm authoritative hydration rejects expired or non-active Short-term records.",
        ],
        "evidence": [],
    },
    "archive_default_unavailable": {
        "status": "NOT_RUN",
        "goal": "Prove Archive vectors are not default-visible and require separate explicit capability path.",
        "planned_read_only_evidence": [
            "Count archive-tier candidates returned by default provider filters, expecting zero.",
            "Confirm response archive_default_visible=false and no Archive item returns in default mode.",
        ],
        "evidence": [],
    },
    "deleted_or_tombstoned_sources": {
        "status": "NOT_RUN",
        "goal": "Prove deleted/tombstoned source candidates do not return and produce bounded repair evidence only when authoritative state was read.",
        "planned_read_only_evidence": [
            "Inventory candidate source_state/status values for tombstoned or deleted source records.",
            "Compare hydration decisions with repair_purge_candidate_count and outbox record planning without writing.",
        ],
        "evidence": [],
    },
    "duplicate_revisions": {
        "status": "NOT_RUN",
        "goal": "Prove duplicate physical vectors and stale revisions cannot produce duplicate or stale returned memories.",
        "planned_read_only_evidence": [
            "Group read-only candidates by memory_id and item_revision/content_hash.",
            "Confirm returned results are unique by memory_id and match authoritative latest revision fences.",
        ],
        "evidence": [],
    },
    "partial_outages": {
        "status": "NOT_RUN",
        "goal": "Prove partial Pinecone/Firestore read failures return bounded NOT_READY/partial status without legacy fallback or unsafe disclosure.",
        "planned_read_only_evidence": [
            "Record provider read error class using sanitized low-cardinality labels only.",
            "Confirm legacy_fallback_used=false and no raw uid/query/vector ids/errors in evidence payloads.",
        ],
        "evidence": [],
    },
    "high_volume_account_candidate_budgets": {
        "status": "NOT_RUN",
        "goal": "Prove high-volume accounts respect vector query, candidate, hydration-read, and deadline budgets.",
        "planned_read_only_evidence": [
            "Run bounded read-only candidate-window inventory for a proof uid with many memory memories.",
            "Record vector_query_count, candidate_request_limit, hydrated_candidate_count, and exhaustion flags.",
        ],
        "evidence": [],
    },
    "load_recall_latency_criteria": {
        "status": "NOT_RUN",
        "goal": "Collect production-like load, recall, and latency criteria before rollout approval.",
        "planned_read_only_evidence": [
            "Define recall fixture/query set, p50/p95/p99 latency budgets, and acceptable no-silent-data-loss thresholds.",
            "Run only against explicitly approved read-only proof data; no benchmark evidence exists until executed.",
        ],
        "evidence": [],
    },
}

PASS_FAIL_CRITERIA = {
    "provider_pagination_refill": "PASS only with real read-only Pinecone evidence showing refill reaches enough fresh hydrated candidates without exceeding budgets.",
    "timeout_semantics": "PASS only with measured provider/client/local timeout behavior and sanitized error/status labels.",
    "firestore_read_counts": "PASS only when read counts prove candidate-ID document gets stay within configured hydration budget.",
    "recall_latency_load": "PASS only with explicit recall fixture results and p50/p95/p99 latency/load output from an approved environment.",
    "no_archive_by_default": "PASS only when Archive candidates are absent from default returns; Archive remains default-unavailable.",
    "no_mutation": "PASS requires no Pinecone upsert/delete/update and no Firestore create/set/update/delete operations.",
}

NON_CLAIMS = [
    "no real Pinecone/Firestore provider proof was executed by this runner in default mode",
    "No real Pinecone/Firestore provider proof, benchmark evidence, load/recall/latency result, or production approval is claimed unless an explicit read-only execution artifact says so.",
    "No Pinecone upsert/delete/update is performed; shared ns2 must never be mutated by this runner.",
    "No Firestore writes are performed; readiness inventory is read-only and may be NOT_RUN when credentials/config are unavailable.",
    "Archive remains default-unavailable and stale Short-term remains not default-visible.",
]


@dataclass(frozen=True)
class VectorSearchProviderReadinessConfig:
    execute: bool
    pinecone_api_key: str
    pinecone_index_name: str
    pinecone_index_host: str
    firestore_project: str
    proof_uid: str
    proof_namespace: str


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe-by-default memory vector search provider proof/readiness runner. Default mode is NOT_RUN."
    )
    parser.add_argument("--execute", action="store_true", help="Gate future safe read-only readiness checks.")
    parser.add_argument("--pinecone-api-key", default=os.getenv("PINECONE_API_KEY", ""))
    parser.add_argument("--pinecone-index-name", default=os.getenv("PINECONE_INDEX_NAME", ""))
    parser.add_argument("--pinecone-index-host", default=os.getenv("PINECONE_INDEX_HOST", ""))
    parser.add_argument("--firestore-project", default=os.getenv("MEMORY_PROVIDER_PROOF_FIRESTORE_PROJECT", ""))
    parser.add_argument("--proof-uid", default=os.getenv("MEMORY_PROVIDER_PROOF_UID", ""))
    parser.add_argument("--proof-namespace", default=os.getenv("MEMORY_PROVIDER_PROOF_NAMESPACE", SHARED_NAMESPACE))
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> VectorSearchProviderReadinessConfig:
    return VectorSearchProviderReadinessConfig(
        execute=bool(args.execute),
        pinecone_api_key=str(args.pinecone_api_key or ""),
        pinecone_index_name=str(args.pinecone_index_name or ""),
        pinecone_index_host=str(args.pinecone_index_host or ""),
        firestore_project=str(args.firestore_project or ""),
        proof_uid=str(args.proof_uid or ""),
        proof_namespace=str(args.proof_namespace or SHARED_NAMESPACE),
    )


def evaluate_prerequisites(config: VectorSearchProviderReadinessConfig) -> List[str]:
    prerequisites: List[str] = []
    if not config.pinecone_api_key:
        prerequisites.append("PINECONE_API_KEY is required")
    if not config.pinecone_index_name:
        prerequisites.append("PINECONE_INDEX_NAME is required")
    if not config.pinecone_index_host:
        prerequisites.append("PINECONE_INDEX_HOST is required")
    if not config.firestore_project:
        prerequisites.append("MEMORY_PROVIDER_PROOF_FIRESTORE_PROJECT or --firestore-project is required")
    if not config.proof_uid:
        prerequisites.append("MEMORY_PROVIDER_PROOF_UID or --proof-uid is required")
    return prerequisites


def build_readiness_artifact(config: VectorSearchProviderReadinessConfig) -> Dict[str, Any]:
    prerequisites = evaluate_prerequisites(config)
    ready_for_readonly_execution = bool(config.execute and not prerequisites)
    return {
        "status": "NOT_RUN",
        "read_only": True,
        "mutation_allowed": False,
        "provider_calls_executed": False,
        "provider_ready_for_readonly_execution": ready_for_readonly_execution,
        "production_rollout_approved": False,
        "benchmark_evidence_collected": False,
        "shared_namespace": config.proof_namespace,
        "required_environment": REQUIRED_ENVIRONMENT,
        "prerequisites": prerequisites,
        "proof_cases": PROOF_CASES,
        "pass_fail_criteria": PASS_FAIL_CRITERIA,
        "planned_provider_actions": [
            "read-only Pinecone query/inventory only; no upsert/delete/update",
            "read-only Firestore document get/query accounting only; no create/set/update/delete",
        ],
        "planned_safe_commands": build_planned_commands(),
        "non_claims": NON_CLAIMS,
    }


def build_planned_commands() -> List[str]:
    return [
        "python3 backend/scripts/vector_search_provider_readiness.py",
        "python3 backend/scripts/vector_search_provider_readiness.py --execute",
        "Required env: PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_INDEX_HOST, MEMORY_PROVIDER_PROOF_FIRESTORE_PROJECT, MEMORY_PROVIDER_PROOF_UID.",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    artifact = build_readiness_artifact(config)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    if config.execute and artifact["prerequisites"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
