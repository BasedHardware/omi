"""Canonical projections module (WS-G8a).

Neutral ``projections`` is the source of truth. Canonical projections module.
"""

import copy
import hashlib
from typing import Any, Dict, List


def _status(fact: Dict[str, Any]) -> str:
    return fact.get("status") or fact.get("memory_state") or "active"


def _content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _entity_id(value: Any) -> str:
    return str(value) if value is not None else "unknown"


def _graph_projection(active_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for fact in active_facts:
        subject = _entity_id(fact.get("subject_entity_id") or fact.get("subject") or "user")
        nodes.setdefault(subject, {"entity_id": subject, "source": "durable_fact_projection"})
        arguments = copy.deepcopy(fact.get("arguments") or {})
        for key, value in arguments.items():
            if key.endswith("_entity_id") or key in {"object_entity_id", "person_entity_id", "organization_entity_id"}:
                object_id = _entity_id(value)
                nodes.setdefault(object_id, {"entity_id": object_id, "source": "durable_fact_projection"})
        edges.append(
            {
                "edge_id": f"edge_{fact.get('id')}",
                "memory_id": fact.get("id"),
                "subject_entity_id": subject,
                "predicate": fact.get("predicate"),
                "arguments": arguments,
                "qualifiers": copy.deepcopy(fact.get("qualifiers") or {}),
            }
        )
    return {"nodes": nodes, "edges": edges}


def rebuild_memory_memory_projections(facts: Dict[str, Dict[str, Any]] | List[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(facts, dict):
        fact_rows = [copy.deepcopy(value) for _, value in sorted(facts.items(), key=lambda item: item[0])]
    else:
        fact_rows = sorted([copy.deepcopy(row) for row in facts], key=lambda row: row.get("id") or "")

    active_facts = [fact for fact in fact_rows if _status(fact) == "active"]
    review_facts = [fact for fact in fact_rows if _status(fact) == "review"]
    context_facts = [fact for fact in fact_rows if _status(fact) == "context_only"]

    vector_index = [
        {
            "memory_id": fact.get("id"),
            "content": fact.get("content"),
            "content_hash": _content_hash(fact.get("content") or ""),
            "predicate": fact.get("predicate"),
            "status": "active",
            "projection_source": "durable_ledger_fact",
        }
        for fact in active_facts
    ]
    review_queue = [
        {
            "memory_id": fact.get("id"),
            "content": fact.get("content"),
            "status": _status(fact),
            "evidence_count": len(fact.get("evidence_set") or []),
            "projection_source": "durable_ledger_fact",
        }
        for fact in review_facts
    ]
    context_index = [
        {
            "memory_id": fact.get("id"),
            "content": fact.get("content"),
            "status": _status(fact),
            "projection_source": "durable_ledger_fact",
        }
        for fact in context_facts
    ]

    return {
        "schema_version": "memory_projections.v1",
        "vector_index": vector_index,
        "graph": _graph_projection(active_facts),
        "review_queue": review_queue,
        "context_index": context_index,
        "source_of_truth": "memory_ledger",
    }


# Neutral symbol aliases (memory names remain valid via shim)
rebuild_memory_projections = rebuild_memory_memory_projections
