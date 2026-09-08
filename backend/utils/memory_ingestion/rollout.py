# LIFECYCLE: permanent
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from utils.memory_ingestion.ids import canonical_json

WriteMode = Literal["legacy_only", "dual_write", "graph_only"]
ReadMode = Literal["legacy", "graph_head"]
GateStatus = Literal["unknown", "running", "failed", "passed"]

LEGACY_MIGRATION_VERSION = "genesis_ledger_backfill.v1"
LEGACY_EVIDENCE_KIND = "legacy_memory_without_raw_artifact"
LEGACY_CAPTURE_CONFIDENCE = 0.5


@dataclass(frozen=True)
class MemoryGraphRolloutFlags:
    write_mode: WriteMode = "dual_write"
    read_mode: ReadMode = "legacy"
    parity_status: GateStatus = "unknown"
    shadow_eval_status: GateStatus = "unknown"
    benchmark_compare_status: GateStatus = "unknown"
    force_graph_read: bool = False


@dataclass(frozen=True)
class MemoryGraphRolloutDecision:
    write_legacy: bool
    write_graph: bool
    read_source: ReadMode
    shadow_eval: bool
    benchmark_compare: bool
    rollback_read_source: ReadMode = "legacy"


def decide_rollout(flags: MemoryGraphRolloutFlags) -> MemoryGraphRolloutDecision:
    if flags.write_mode == "legacy_only":
        write_legacy = True
        write_graph = False
    elif flags.write_mode == "graph_only":
        write_legacy = False
        write_graph = True
    else:
        write_legacy = True
        write_graph = True

    graph_read_allowed = flags.force_graph_read or (
        flags.parity_status == "passed"
        and flags.shadow_eval_status == "passed"
        and flags.benchmark_compare_status == "passed"
    )
    read_source: ReadMode = "graph_head" if flags.read_mode == "graph_head" and graph_read_allowed else "legacy"
    return MemoryGraphRolloutDecision(
        write_legacy=write_legacy,
        write_graph=write_graph,
        read_source=read_source,
        shadow_eval=write_graph and flags.shadow_eval_status in ("unknown", "running"),
        benchmark_compare=write_graph and flags.benchmark_compare_status in ("unknown", "running"),
    )


def legacy_memory_to_migrated_fact(
    memory: dict[str, Any],
    *,
    migration_time: datetime,
    migration_version: str = LEGACY_MIGRATION_VERSION,
) -> dict[str, Any]:
    memory_id = str(memory.get("id") or memory.get("memory_id") or memory.get("backendId"))
    source_id = _first_present(memory, "conversation_id", "conversationId", "source_id", "sourceId")
    created_at = _parse_datetime(_first_present(memory, "created_at", "createdAt"))
    updated_at = _parse_datetime(_first_present(memory, "updated_at", "updatedAt")) or migration_time
    evidence = {
        "evidence_id": f"legacy:{memory_id}",
        "kind": LEGACY_EVIDENCE_KIND,
        "source_id": source_id,
        "independence_group": source_id or f"legacy:{memory_id}",
        "capture_confidence": LEGACY_CAPTURE_CONFIDENCE,
        "redaction_status": "active",
        "migration_version": migration_version,
    }
    epistemic_status, veracity = _legacy_epistemic_status_and_veracity(memory)
    fact = copy.deepcopy(memory)
    fact.update(
        {
            "id": memory_id,
            "original_memory_id": memory_id,
            "content": memory.get("content"),
            "subject_entity_id": "user",
            "subject_attribution": "legacy_assumed",
            "scope": memory.get("scope") or "global",
            "valid_time_status": "unknown",
            "valid_at": None,
            "valid_interval": {"kind": "unknown"},
            "evidence": [evidence],
            "capture_confidence": LEGACY_CAPTURE_CONFIDENCE,
            "veracity": veracity,
            "commit_time": migration_time,
            "created_at": created_at or migration_time,
            "updated_at": updated_at,
            "migration_version": migration_version,
            "legacy_migrated": True,
            "migration_metadata": {
                "version": migration_version,
                "legacy_epistemic_status": epistemic_status,
            },
        }
    )
    fact.setdefault("qualifiers", {})["valid_time_status"] = "unknown"
    fact["qualifiers"]["epistemic_status"] = epistemic_status
    return fact


def build_genesis_ledger_backfill(
    uid: str,
    legacy_memories: list[dict[str, Any]],
    *,
    migration_time: datetime | None = None,
    migration_version: str = LEGACY_MIGRATION_VERSION,
) -> dict[str, Any]:
    migration_time = migration_time or datetime.now(timezone.utc)
    mutations: list[dict[str, Any]] = []
    migrated_facts: list[dict[str, Any]] = []
    for memory in legacy_memories:
        if memory.get("deleted") is True:
            continue
        fact = legacy_memory_to_migrated_fact(
            memory,
            migration_time=migration_time,
            migration_version=migration_version,
        )
        migrated_facts.append(fact)
        mutations.append(_add_fact(fact))

    for fact in migrated_facts:
        invalid_at = _parse_datetime(_first_present(fact, "invalid_at", "invalidAt"))
        superseded_by = _first_present(fact, "superseded_by", "supersededBy")
        if superseded_by:
            mutations.append(
                _supersede_fact(
                    fact_id=str(fact["id"]),
                    by=str(superseded_by),
                    kind="legacy_superseded",
                    valid_interval={"valid_to": invalid_at or migration_time, "valid_time_status": "unknown"},
                )
            )
        elif invalid_at:
            mutations.append(_retract_fact(str(fact["id"]), reason="legacy_invalidated"))

    commit = _build_commit(
        None,
        mutations,
        run_id=f"genesis-ledger-backfill:{uid}:{migration_version}",
        commit_time=migration_time,
    )
    return {
        "schema_version": "memory_genesis_ledger_backfill.v1",
        "uid": uid,
        "migration_version": migration_version,
        "migration_time": migration_time,
        "commit": commit,
        "migrated_count": len(migrated_facts),
        "legacy_evidence_kind": LEGACY_EVIDENCE_KIND,
    }


def project_graph_head_to_legacy_view(
    head_facts: dict[str, dict[str, Any]] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts = head_facts.values() if isinstance(head_facts, dict) else head_facts
    rows: list[dict[str, Any]] = []
    for fact in facts:
        if fact.get("invalid_at") is not None:
            continue
        row: dict[str, Any] = {
            "id": fact.get("id"),
            "content": fact.get("content"),
            "category": fact.get("category"),
            "created_at": fact.get("created_at"),
            "updated_at": fact.get("updated_at"),
            "scoring": fact.get("scoring"),
            "visibility": fact.get("visibility", "public"),
            "reviewed": fact.get("reviewed"),
            "user_review": fact.get("user_review"),
            "arguments": fact.get("arguments") or {},
            "evidence": fact.get("evidence") or [],
        }
        rows.append(row)
    return sorted(rows, key=lambda item: _canonical_json(item))


def diff_legacy_vs_graph_projection(
    legacy_rows: list[dict[str, Any]],
    graph_head_facts: dict[str, dict[str, Any]] | list[dict[str, Any]],
) -> dict[str, Any]:
    graph_rows = project_graph_head_to_legacy_view(graph_head_facts)
    legacy_by_id = {str(row.get("id")): row for row in legacy_rows if row.get("id") is not None}
    graph_by_id = {str(row.get("id")): row for row in graph_rows if row.get("id") is not None}
    missing_from_graph = sorted(set(legacy_by_id) - set(graph_by_id))
    extra_in_graph = sorted(set(graph_by_id) - set(legacy_by_id))
    mismatched: list[dict[str, Any]] = []
    for memory_id in sorted(set(legacy_by_id) & set(graph_by_id)):
        if _canonical_json(_legacy_comparable(legacy_by_id[memory_id])) != _canonical_json(graph_by_id[memory_id]):
            mismatched.append(
                {
                    "id": memory_id,
                    "legacy": _legacy_comparable(legacy_by_id[memory_id]),
                    "graph": graph_by_id[memory_id],
                }
            )
    return {
        "schema_version": "memory_projection_parity_diff.v1",
        "parity": not missing_from_graph and not extra_in_graph and not mismatched,
        "missing_from_graph": missing_from_graph,
        "extra_in_graph": extra_in_graph,
        "mismatched": mismatched,
        "diff_count": len(missing_from_graph) + len(extra_in_graph) + len(mismatched),
    }


def benchmark_rows_from_pipeline_outputs(
    outputs: list[dict[str, Any]],
    *,
    example_id_by_run_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    example_id_by_run_id = example_id_by_run_id or {}
    rows: list[dict[str, Any]] = []
    for output in outputs:
        run_id = output.get("run_id")
        example_id = output.get("example_id") or (example_id_by_run_id.get(str(run_id)) if run_id is not None else None)
        if not example_id:
            raise ValueError(f"pipeline output {run_id or '<unknown>'} is missing example_id")
        row = copy.deepcopy(output)
        row["example_id"] = example_id
        if "entities" not in row and "entity_ops" in row:
            row["entities"] = row.get("entity_ops") or []
        rows.append(row)
    return rows


def compare_benchmark_summaries(legacy_summary: dict[str, Any], graph_summary: dict[str, Any]) -> dict[str, Any]:
    required_metrics = ("dedup", "supersession")
    missing_metrics = [
        metric for metric in required_metrics if metric not in legacy_summary or metric not in graph_summary
    ]
    regressions: list[dict[str, Any]] = []
    for metric in required_metrics:
        if metric in missing_metrics:
            continue
        legacy_score = float(legacy_summary.get(metric, 0.0) or 0.0)
        graph_score = float(graph_summary.get(metric, 0.0) or 0.0)
        if graph_score < legacy_score:
            regressions.append({"metric": metric, "legacy": legacy_score, "graph": graph_score})
    return {
        "schema_version": "memory_benchmark_comparison_gate.v1",
        "parity_or_better": not missing_metrics and not regressions,
        "required_metrics": list(required_metrics),
        "missing_metrics": missing_metrics,
        "regressions": regressions,
    }


def _legacy_comparable(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": memory.get("id"),
        "content": memory.get("content"),
        "category": memory.get("category"),
        "created_at": memory.get("created_at"),
        "updated_at": memory.get("updated_at"),
        "scoring": memory.get("scoring"),
        "visibility": memory.get("visibility", "public"),
        "reviewed": memory.get("reviewed"),
        "user_review": memory.get("user_review"),
        "arguments": memory.get("arguments") or {},
        "evidence": memory.get("evidence") or [],
    }


def _legacy_epistemic_status_and_veracity(memory: dict[str, Any]) -> tuple[str, float]:
    if memory.get("user_review") is False:
        status = "rejected"
        score = 0.0
    elif memory.get("reviewed") is True or memory.get("user_review") is True:
        status = "user_confirmed"
        score = 1.0
    else:
        status = "legacy_default"
        score = 0.5
    return status, score


def _add_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {"type": "add_fact", "fact": copy.deepcopy(fact)}


def _supersede_fact(
    fact_id: str,
    *,
    by: str,
    kind: str,
    valid_interval: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "supersede_fact",
        "fact_id": fact_id,
        "by": by,
        "kind": kind,
        "valid_interval": copy.deepcopy(valid_interval),
    }


def _retract_fact(fact_id: str, *, reason: str) -> dict[str, Any]:
    return {"type": "retract_fact", "fact_id": fact_id, "reason": reason}


def _build_commit(
    parent_commit_id: str | None,
    mutations: list[dict[str, Any]],
    *,
    run_id: str,
    commit_time: datetime,
) -> dict[str, Any]:
    commit_id = hashlib.sha256(
        _canonical_json({"parent_commit_id": parent_commit_id, "mutations": mutations}).encode("utf-8")
    ).hexdigest()
    return {
        "commit_id": commit_id,
        "parent_commit_id": parent_commit_id,
        "commit_time": commit_time,
        "run_id": run_id,
        "mutations": copy.deepcopy(mutations),
    }


def _first_present(memory: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = memory.get(key)
        if value is not None:
            return value
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


_canonical_json = canonical_json
