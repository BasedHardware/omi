#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from readiness_gate_common import (
    add_require_go_arg,
    collect_gates_from_artifact,
    evaluate_gates,
    exit_code_for_status,
)

SHARED_NAMESPACE = "ns2"

LEGACY_SEARCH_INVENTORY = [
    {
        "function": "database.vector_db.find_similar_memories",
        "namespace": SHARED_NAMESPACE,
        "caller_examples": ["MCP legacy fallback", "chat legacy fallback", "duplicate checks"],
        "required_filter_barrier": {"memory_schema_version": {"$exists": False}},
        "legacy_id_shape": "{uid}-{memory_id}",
    },
    {
        "function": "database.vector_db.search_memories_by_vector",
        "namespace": SHARED_NAMESPACE,
        "caller_examples": ["legacy semantic memory search"],
        "required_filter_barrier": {"memory_schema_version": {"$exists": False}},
        "legacy_id_shape": "{uid}-{memory_id}",
    },
]

MEMORY_METADATA_BARRIERS = {
    "memory_schema_version": "memory vectors must carry memory_schema_version=1; legacy queries exclude records where it exists.",
    "uid": "Both legacy and memory filters must constrain exact uid before hydration.",
    "memory_tier": "memory default filters only short_term/long_term; archive requires explicit archive mode.",
    "status": "memory vector filters require active status; hydration remains authoritative.",
    "source_state": "memory vector filters require active source_state so tombstoned/deleted sources do not pass metadata filtering.",
    "restricted_sensitivity": "memory vector filters exclude restricted_sensitivity=true from candidate selection.",
    "account_generation": "Hydration must compare candidate metadata to the current required account generation.",
    "item_revision": "Hydration must compare candidate metadata to the authoritative item revision.",
    "source_commit_id": "Hydration must reject missing or stale source commit metadata.",
    "content_hash": "Hydration must reject missing or stale content hash metadata.",
    "projection_commit_id": "Hydration must reject missing or stale projection metadata.",
}

REQUIRED_BARRIERS = {
    "legacy_queries_exclude_memory_schema": (
        "Every legacy ns2 memory search must include {'memory_schema_version': {'$exists': False}} before top-k "
        "selection so memory Short-term, Long-term, Archive, tombstoned, or stale-revision vectors cannot consume "
        "legacy result slots."
    ),
    "memory_queries_include_schema_and_tier_filters": (
        "memory ns2 searches must include memory_schema_version, uid, tier, status, source_state, visibility, and "
        "restricted_sensitivity filters before hydration."
    ),
    "stale_or_deleted_physical_ids": (
        "Legacy filters only exclude memory schema records; real Pinecone proof is still required for stale/deleted "
        "legacy physical IDs and duplicate memory physical IDs."
    ),
    "overfetch_refill": (
        "This slice does not solve memory overfetch/refill: stale filtered candidates can still collapse recall until P0-7 "
        "adds measured overfetch/refill and budgets."
    ),
}

NON_CLAIMS = [
    "No real Pinecone shared `ns2` proof was executed by this runner in default mode.",
    "No Pinecone upsert/delete/update/mutation is performed by this runner.",
    "This artifact does not prove production baseline recall retention or coexistence benchmarks.",
    "This artifact does not approve production rollout and does not close Firestore/IAM, telemetry, benchmark, or P0-7 gates.",
]


@dataclass(frozen=True)
class SharedNs2LegacyIsolationConfig:
    execute: bool
    api_key: str
    index_name: str
    index_host: str
    require_go: bool = False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe-by-default shared ns2 legacy/memory vector isolation readiness runner. Default mode is NOT_RUN."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Check provider prerequisites for future read-only proof."
    )
    parser.add_argument("--api-key", default=os.getenv("PINECONE_API_KEY", ""))
    parser.add_argument("--index-name", default=os.getenv("PINECONE_INDEX_NAME", ""))
    parser.add_argument("--index-host", default=os.getenv("PINECONE_INDEX_HOST", ""))
    add_require_go_arg(parser)
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> SharedNs2LegacyIsolationConfig:
    return SharedNs2LegacyIsolationConfig(
        execute=bool(args.execute),
        require_go=bool(args.require_go),
        api_key=str(args.api_key or ""),
        index_name=str(args.index_name or ""),
        index_host=str(args.index_host or ""),
    )


def evaluate_prerequisites(config: SharedNs2LegacyIsolationConfig) -> List[str]:
    prerequisites: List[str] = []
    if not config.api_key:
        prerequisites.append("PINECONE_API_KEY is required")
    if not config.index_name:
        prerequisites.append("PINECONE_INDEX_NAME is required")
    if not config.index_host:
        prerequisites.append("PINECONE_INDEX_HOST is required")
    return prerequisites


def build_readiness_artifact(config: SharedNs2LegacyIsolationConfig) -> Dict[str, Any]:
    prerequisites = evaluate_prerequisites(config)
    provider_ready_for_readonly_inventory = bool(config.execute and not prerequisites)
    return {
        "status": "NOT_RUN",
        "read_only": True,
        "mutation_allowed": False,
        "shared_namespace": SHARED_NAMESPACE,
        "provider_ready_for_readonly_inventory": provider_ready_for_readonly_inventory,
        "prerequisites": prerequisites,
        "legacy_search_inventory": LEGACY_SEARCH_INVENTORY,
        "memory_metadata_barriers": MEMORY_METADATA_BARRIERS,
        "required_barriers": REQUIRED_BARRIERS,
        "planned_provider_actions": ["read-only query/inventory only; no upsert/delete/update"],
        "planned_safe_commands": build_planned_commands(),
        "non_claims": NON_CLAIMS,
    }


def build_planned_commands() -> List[str]:
    return [
        "python3 backend/scripts/shared_ns2_legacy_isolation_readiness.py",
        "python3 backend/scripts/shared_ns2_legacy_isolation_readiness.py --execute",
        "Required env for future provider proof: PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_INDEX_HOST.",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    artifact = build_readiness_artifact(config)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    if config.execute and artifact["prerequisites"]:
        return 2
    if config.require_go:
        overall_status, _ = evaluate_gates(collect_gates_from_artifact(artifact))
        return exit_code_for_status(overall_status, require_go=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
