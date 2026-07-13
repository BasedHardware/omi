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

DEFAULT_SHARED_NAMESPACE = "ns2"
MIN_SAFE_PREFIX_LEN = 12

PASS_FAIL_CRITERIA = {
    "duplicate_stale_physical_ids": (
        "Create at least two throwaway stale physical vector IDs with the same authoritative memory_id under the "
        "confirmed throwaway vector id prefix; worker validation must delete/repair every stale duplicate and leave "
        "no prefix-scoped stale duplicates after a post-run query."
    ),
    "tombstone_precedence_delete": (
        "Authoritative missing/deleted/tombstoned/purged source state must choose delete over repair for every "
        "matching throwaway vector, including duplicate physical IDs."
    ),
    "live_stale_item_repair_upsert": (
        "A live authoritative item with stale projection/revision/source/content metadata must produce exactly one "
        "repair/upsert with current required_projection_commit_id and account_generation metadata."
    ),
    "retry_dead_letter_behavior": (
        "Injected Pinecone delete/upsert failures must produce retry patches until max_attempts and dead_letter after "
        "the terminal attempt; ack failures must be counted separately and not claimed as cleanup success."
    ),
    "shared_ns2_isolation": (
        "Shared ns2 isolation must be read-only inventory unless a separate production-approved plan exists: legacy "
        "vectors not touched, legacy query filters exclude memory schema records, and baseline legacy recall is retained."
    ),
    "legacy_vectors_not_touched": (
        "All mutating operations must be constrained to the confirmed throwaway test namespace and throwaway prefix; "
        "no broad delete/update and no ns2 mutation are allowed by this runner."
    ),
}

NON_CLAIMS = [
    "No production Pinecone delete/upsert is performed by default.",
    "This readiness runner does not prove duplicate stale physical-ID cleanup unless executed later with real "
    "throwaway Pinecone fixtures and recorded PASS output.",
    "This readiness runner does not mutate shared ns2; shared ns2 validation is read-only inventory only.",
    "This readiness runner is not production approval and does not close Firestore/IAM, telemetry, benchmark, "
    "or rollout gates.",
]


@dataclass(frozen=True)
class PineconeRepairValidationConfig:
    execute: bool
    allow_throwaway_mutation: bool
    api_key: str
    index_name: str
    index_host: str
    test_namespace: str
    throwaway_prefix: str
    confirm_throwaway_prefix: str
    shared_ns2_readonly: bool
    require_go: bool = False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe-by-default memory Pinecone repair validation readiness runner. Default mode is NOT_RUN."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Require all safety gates; still emits NOT_RUN plan here."
    )
    parser.add_argument(
        "--allow-throwaway-mutation",
        action="store_true",
        help="Required before any future throwaway Pinecone mutation can run.",
    )
    parser.add_argument("--test-namespace", default=os.getenv("MEMORY_PINECONE_VALIDATION_TEST_NAMESPACE", ""))
    parser.add_argument("--throwaway-prefix", default=os.getenv("MEMORY_PINECONE_VALIDATION_THROWAWAY_PREFIX", ""))
    parser.add_argument(
        "--confirm-throwaway-prefix", default=os.getenv("MEMORY_PINECONE_VALIDATION_CONFIRM_THROWAWAY_PREFIX", "")
    )
    parser.add_argument(
        "--shared-ns2-readonly",
        action="store_true",
        help="Permit read-only shared ns2 inventory criteria; never permits ns2 mutation.",
    )
    parser.add_argument("--api-key", default=os.getenv("PINECONE_API_KEY", ""))
    parser.add_argument("--index-name", default=os.getenv("PINECONE_INDEX_NAME", ""))
    parser.add_argument("--index-host", default=os.getenv("PINECONE_INDEX_HOST", ""))
    add_require_go_arg(parser)
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> PineconeRepairValidationConfig:
    return PineconeRepairValidationConfig(
        execute=bool(args.execute),
        require_go=bool(args.require_go),
        allow_throwaway_mutation=bool(args.allow_throwaway_mutation),
        api_key=str(args.api_key or ""),
        index_name=str(args.index_name or ""),
        index_host=str(args.index_host or ""),
        test_namespace=str(args.test_namespace or ""),
        throwaway_prefix=str(args.throwaway_prefix or ""),
        confirm_throwaway_prefix=str(args.confirm_throwaway_prefix or ""),
        shared_ns2_readonly=bool(args.shared_ns2_readonly),
    )


def evaluate_prerequisites(config: PineconeRepairValidationConfig) -> List[str]:
    prerequisites: List[str] = []
    if not config.api_key:
        prerequisites.append("PINECONE_API_KEY is required")
    if not config.index_name:
        prerequisites.append("PINECONE_INDEX_NAME is required")
    if not config.index_host:
        prerequisites.append("PINECONE_INDEX_HOST is required")
    if config.execute:
        if not config.allow_throwaway_mutation:
            prerequisites.append("--allow-throwaway-mutation is required for execute mode")
        if not config.test_namespace:
            prerequisites.append("--test-namespace is required for execute mode")
        if config.test_namespace == DEFAULT_SHARED_NAMESPACE:
            prerequisites.append("execute mode cannot mutate shared production namespace ns2")
        if not config.throwaway_prefix:
            prerequisites.append("--throwaway-prefix is required for execute mode")
        if config.throwaway_prefix != config.confirm_throwaway_prefix:
            prerequisites.append("--confirm-throwaway-prefix must exactly match --throwaway-prefix")
        if config.throwaway_prefix and len(config.throwaway_prefix) < MIN_SAFE_PREFIX_LEN:
            prerequisites.append("throwaway vector id prefix must be at least 12 characters")
        if config.throwaway_prefix and not config.throwaway_prefix.startswith("memory-proof-"):
            prerequisites.append("throwaway vector id prefix must start with memory-proof-")
    return prerequisites


def build_readiness_artifact(config: PineconeRepairValidationConfig) -> Dict[str, Any]:
    prerequisites = evaluate_prerequisites(config)
    mutation_allowed = (
        config.execute
        and config.allow_throwaway_mutation
        and not prerequisites
        and bool(config.test_namespace)
        and config.test_namespace != DEFAULT_SHARED_NAMESPACE
    )
    return {
        "status": "NOT_RUN",
        "read_only": not mutation_allowed,
        "mutation_allowed": mutation_allowed,
        "namespace": config.test_namespace,
        "shared_namespace": DEFAULT_SHARED_NAMESPACE,
        "shared_ns2_mode": "read_only_inventory_only" if config.shared_ns2_readonly else "not_requested",
        "throwaway_prefix": config.throwaway_prefix,
        "prerequisites": prerequisites,
        "pass_fail_criteria": PASS_FAIL_CRITERIA,
        "planned_safe_commands": build_planned_commands(config),
        "non_claims": NON_CLAIMS,
    }


def build_planned_commands(config: PineconeRepairValidationConfig) -> List[str]:
    return [
        "python3 backend/scripts/pinecone_repair_validation_readiness.py",
        (
            "python3 backend/scripts/pinecone_repair_validation_readiness.py --execute "
            "--allow-throwaway-mutation --test-namespace <throwaway-test-namespace-not-ns2> "
            "--throwaway-prefix memory-proof-<ticket>- --confirm-throwaway-prefix memory-proof-<ticket>- "
            "--shared-ns2-readonly"
        ),
        (
            "Required env: PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_INDEX_HOST; "
            "future mutating validation must touch only IDs beginning with the confirmed throwaway vector id prefix."
        ),
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
