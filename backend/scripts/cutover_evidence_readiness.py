#!/usr/bin/env python3
# LIFECYCLE: one-time
# DELETE-AFTER: INV-MEM-3

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from readiness_gate_common import (
    add_require_go_arg,
    collect_gates_from_artifact,
    evaluate_gates,
    exit_code_for_status,
)

CUTOVER_GATE_STATUS_BLOCKED = "BLOCKED"
CUTOVER_GATE_STATUS_NOT_RUN = "NOT_RUN"

CUTOVER_EVIDENCE_GATES: Dict[str, Dict[str, Any]] = {
    "milestone_oracle_final_approval": {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "summary": "Milestone-specific Oracle review exists, but final approval for memory production cutover is absent.",
        "required_proof_commands_or_artifacts": [
            "docs/operational/memory_readiness_evidence_markers.md updated with final approval section",
            "Signed milestone/final approval artifact explicitly changing Oracle verdict from BLOCK production rollout to approved",
        ],
        "blockers": ["Oracle verdict remains BLOCK production rollout / NO-GO", "final approval not granted"],
        "evidence": [],
        "approval_claimed": False,
    },
    "real_pinecone_validation": {
        "status": CUTOVER_GATE_STATUS_NOT_RUN,
        "summary": "real Pinecone validation remains absent for shared namespace, provider pagination/refill, stale metadata, and repair cases.",
        "required_proof_commands_or_artifacts": [
            "python3 backend/scripts/vector_search_provider_readiness.py --execute with approved Pinecone read-only credentials",
            "python3 backend/scripts/pinecone_repair_validation_readiness.py --execute with approved throwaway namespace controls",
            "Read-only Pinecone evidence artifact for ns2 coexistence, stale/deleted/duplicate vectors, malformed metadata, partial outage, and high-volume candidates",
        ],
        "blockers": ["no real Pinecone proof output", "no shared ns2 production coexistence proof"],
        "evidence": [],
        "approval_claimed": False,
    },
    "real_firestore_cloud_iam_rules_validation": {
        "status": CUTOVER_GATE_STATUS_NOT_RUN,
        "summary": "Real Firestore/cloud IAM and deployed Security Rules validation for memory paths is absent.",
        "required_proof_commands_or_artifacts": [
            "python3 backend/scripts/firestore_rules_iam_proof.py --execute --project <approved-project>",
            "Cloud IAM/service-account binding evidence for memory_items, vector repair outbox, MCP keys, and app/key grants",
            "Deployed Firestore Security Rules denial/allowance evidence for server-owned memory control documents",
        ],
        "blockers": ["no deployed Firestore/IAM proof output", "local emulator evidence is not cloud validation"],
        "evidence": [],
        "approval_claimed": False,
    },
    "recall_precision_latency_no_silent_data_loss_benchmarks": {
        "status": CUTOVER_GATE_STATUS_NOT_RUN,
        "summary": "Recall/precision/latency/no-silent-data-loss benchmarks are not collected for production-shaped memory default reads/vector search.",
        "required_proof_commands_or_artifacts": [
            "Approved benchmark plan with Base/memory recall and precision fixture set",
            "Latency/load run with p50/p95/p99 budgets and high-volume accounts",
            "No-silent-data-loss report covering stale Short-term, Archive default-unavailable, tombstones, duplicates, malformed metadata, and partial outages",
        ],
        "blockers": ["no benchmark run", "no recall/precision/latency/no-silent-data-loss artifact"],
        "evidence": [],
        "approval_claimed": False,
    },
    "production_metrics_aggregation_central_telemetry": {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "summary": "Production metrics aggregation/central telemetry is not wired to the selected ops sink/dashboard/alert policy.",
        "required_proof_commands_or_artifacts": [
            "Central metrics sink integration for memory rollout/read/vector/repair counters with low-cardinality labels",
            "Dashboard and alert policy evidence for empty-after-hydration, budget exhaustion, retry/dead-letter backlog, and rollback gates",
            "Production-safe metric cardinality review showing no uid/query/vector/memory IDs or raw errors",
        ],
        "blockers": [
            "fake-injectable telemetry seams exist only locally",
            "no central monitoring sink or alert policy evidence",
        ],
        "evidence": [],
        "approval_claimed": False,
    },
    "t20_repair_projection_consistency": {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "summary": "T20 repair/projection-consistency is not demonstrated with real vector repair, shared namespace, and authoritative projection evidence.",
        "required_proof_commands_or_artifacts": [
            "python3 backend/scripts/t20_repair_projection_consistency_readiness.py",
            "T20 repair/projection-consistency evidence tying projection_commit_id/account_generation/item_revision/source_commit_id/content_hash to memory_items, vector metadata, and vector repair outbox records",
            "Vector repair outbox enqueue/dead-letter/backlog and worker execution artifact proving stale physical vectors/tombstones/duplicates converge without data loss",
            "shared ns2 legacy/memory isolation under stale candidates proof with repair/refill behavior",
        ],
        "blockers": [
            "real repair/projection consistency not proven",
            "T20 readiness matrix remains NOT_RUN/BLOCKED with empty evidence",
            "Pinecone repair and shared ns2 validation remain readiness-only",
        ],
        "evidence": [],
        "approval_claimed": False,
    },
    "t21_v3_compatibility_cursor_pagination": {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "summary": "T21 /v3 compatibility and cursor pagination requirements are not demonstrated for production cutover.",
        "required_proof_commands_or_artifacts": [
            "python3 backend/scripts/t21_v3_compatibility_cursor_readiness.py",
            "T21 `/v3` compatibility and cursor pagination matrix for legacy/memory readers covering /v3 endpoint compatibility, stable cursor pagination, category filters, and stable ordering",
            "Compatibility evidence for disabled/malformed/no-grant, enabled-but-empty, deleted/non-active records, Archive default-unavailable, external response shape compatibility, developer category filtering, and MCP REST/SSE shape consistency",
            "Regression output for affected `/v3` endpoints and product/developer/MCP/chat caller regression coverage",
        ],
        "blockers": [
            "no T21 /v3 compatibility proof",
            "stable cursor pagination behavior not cutover-proven",
            "product/developer/MCP/chat caller regression evidence remains NOT_RUN",
        ],
        "evidence": [],
        "approval_claimed": False,
    },
    "t22_t23_external_writes_and_caller_coverage": {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "summary": "T22/T23 external writes and caller coverage remain incomplete for Developer API, MCP, chat/tools, and agent surfaces.",
        "required_proof_commands_or_artifacts": [
            "python3 backend/scripts/t22_t23_external_writes_caller_coverage_readiness.py",
            "T22/T23 external writes and caller coverage matrix for external create/edit/delete/list/search write/read convergence across /v3, Developer API, MCP REST/SSE, chat, tools, and agent paths",
            "Durable memory write convergence or tested dual-write/outbox evidence before authoritative external reads, including no legacy unsafe fallback after memory writes",
            "Caller coverage regression proving Developer API write/read paths, MCP REST/SSE write/read/list/search paths, chat/tool/agent caller coverage, app/key/scope grant enforcement, Archive default-unavailable, response-shape compatibility, delete/review/import compatibility, and rollback/disable behavior",
        ],
        "blockers": [
            "no T22/T23 external writes and caller coverage proof",
            "external create/edit/delete/list/search write/read convergence remains NOT_RUN",
            "durable memory-write convergence or dual-write/outbox evidence remains NOT_RUN",
            "caller coverage incomplete across Developer API, MCP REST/SSE, chat, tools, and agent paths",
        ],
        "evidence": [],
        "approval_claimed": False,
    },
    "production_cutover_approval": {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "summary": "production cutover approval is absent and must remain false until every gate has real evidence and explicit approval.",
        "required_proof_commands_or_artifacts": [
            "Final cutover checklist with all gates PASS and attached real evidence artifacts",
            "Explicit production owner approval naming environment, rollout cohort, rollback plan, and monitoring gates",
            "Rollback/disable drill output for memory read/vector cutover",
        ],
        "blockers": ["required evidence absent", "production rollout approval not granted"],
        "evidence": [],
        "approval_claimed": False,
    },
}

NON_CLAIMS = [
    "Oracle verdict remains BLOCK production rollout / NO-GO.",
    "production_rollout_approved=false; no production approval or final cutover approval is claimed.",
    "No cloud/provider proof, Pinecone validation, Firestore/IAM proof, benchmark evidence, or telemetry sink evidence is claimed by this readiness artifact.",
    "Default and execute modes are read-only checklist inventory only; no network/provider/cloud calls are executed and no mutations are planned.",
    "Archive remains default-unavailable and stale Short-term remains not default-visible.",
]


@dataclass(frozen=True)
class CutoverEvidenceReadinessConfig:
    execute: bool
    require_go: bool = False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe memory production cutover evidence readiness checklist. It inventories gates as BLOCKED/NOT_RUN without approval claims."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Emit the same read-only checklist; does not call providers."
    )
    add_require_go_arg(parser)
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> CutoverEvidenceReadinessConfig:
    return CutoverEvidenceReadinessConfig(
        execute=bool(args.execute),
        require_go=bool(args.require_go),
    )


def build_readiness_artifact(config: CutoverEvidenceReadinessConfig) -> Dict[str, Any]:
    return {
        "status": CUTOVER_GATE_STATUS_BLOCKED,
        "read_only": True,
        "mutation_allowed": False,
        "execute_requested": config.execute,
        "network_or_provider_calls_executed": False,
        "benchmark_evidence_collected": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "gates": CUTOVER_EVIDENCE_GATES,
        "planned_safe_commands": [
            "python3 backend/scripts/cutover_evidence_readiness.py",
            "python3 backend/scripts/cutover_evidence_readiness.py --execute",
        ],
        "non_claims": NON_CLAIMS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    artifact = build_readiness_artifact(config)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    if config.require_go:
        overall_status, _ = evaluate_gates(collect_gates_from_artifact(artifact))
        return exit_code_for_status(overall_status, require_go=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
