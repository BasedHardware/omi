from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional, cast

from database import knowledge_graph as kg_db
from database._client import get_firestore_client


class MissingKnowledgeGraphEndpointsError(ValueError):
    """Raised when synced edges reference node ids that are not in Firestore yet."""


def _parse_sync_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _parse_aliases_json(value: Any) -> List[str]:
    if isinstance(value, list):
        return sorted({item.strip() for item in cast(List[Any], value) if isinstance(item, str) and item.strip()})
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return sorted({item.strip() for item in parsed if isinstance(item, str) and item.strip()})
    return []


def namespace_for_source(source_namespace: Any) -> str:
    if not isinstance(source_namespace, str) or not source_namespace.strip() or len(source_namespace) > 256:
        raise ValueError("source_namespace must be a non-empty string of at most 256 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in source_namespace):
        raise ValueError("source_namespace contains unsupported control characters")
    return f"kg_{hashlib.sha256(source_namespace.encode('utf-8')).hexdigest()[:24]}"


def _namespaced_id(source_namespace: str, value: Any, field_name: str) -> str:
    local_id = kg_db.validate_knowledge_graph_document_id(value, field_name)
    namespace = namespace_for_source(source_namespace)
    return kg_db.validate_knowledge_graph_document_id(f"{namespace}_{local_id}", field_name)


def _local_kg_node_to_firestore(row: Dict[str, Any], source_namespace: str) -> Optional[Dict[str, Any]]:
    node_id = row.get("nodeId") or row.get("node_id")
    label = row.get("label")
    if not isinstance(node_id, str) or not node_id.strip() or not isinstance(label, str) or not label.strip():
        return None
    node_type = row.get("nodeType") or row.get("node_type") or "concept"
    aliases = _parse_aliases_json(row.get("aliasesJson") if "aliasesJson" in row else row.get("aliases_json"))
    node_data: Dict[str, Any] = {
        "id": _namespaced_id(source_namespace, node_id, "node id"),
        "label": label.strip(),
        "node_type": node_type if isinstance(node_type, str) and node_type.strip() else "concept",
        "aliases": aliases,
        "memory_ids": [],
        "sync_namespace": namespace_for_source(source_namespace),
    }
    created_at = _parse_sync_timestamp(row.get("createdAt") if "createdAt" in row else row.get("created_at"))
    updated_at = _parse_sync_timestamp(row.get("updatedAt") if "updatedAt" in row else row.get("updated_at"))
    if created_at is not None:
        node_data["created_at"] = created_at
    if updated_at is not None:
        node_data["updated_at"] = updated_at
    return node_data


def _local_kg_edge_to_firestore(row: Dict[str, Any], source_namespace: str) -> Optional[Dict[str, Any]]:
    edge_id = row.get("edgeId") or row.get("edge_id")
    source_id = row.get("sourceNodeId") or row.get("source_node_id")
    target_id = row.get("targetNodeId") or row.get("target_node_id")
    label = row.get("label")
    if (
        not isinstance(edge_id, str)
        or not edge_id.strip()
        or not isinstance(source_id, str)
        or not source_id.strip()
        or not isinstance(target_id, str)
        or not target_id.strip()
        or not isinstance(label, str)
        or not label.strip()
    ):
        return None
    edge_data: Dict[str, Any] = {
        "id": _namespaced_id(source_namespace, edge_id, "edge id"),
        "source_id": _namespaced_id(source_namespace, source_id, "source node id"),
        "target_id": _namespaced_id(source_namespace, target_id, "target node id"),
        "label": label.strip(),
        "memory_ids": [],
        "sync_namespace": namespace_for_source(source_namespace),
    }
    created_at = _parse_sync_timestamp(row.get("createdAt") if "createdAt" in row else row.get("created_at"))
    if created_at is not None:
        edge_data["created_at"] = created_at
    return edge_data


def _existing_node_ids(uid: str, endpoint_ids: Iterable[str], *, db_client: Any = None) -> set[str]:
    client = db_client if db_client is not None else get_firestore_client()
    nodes_ref = client.collection(kg_db.users_collection).document(uid).collection(kg_db.knowledge_nodes_collection)
    refs = [nodes_ref.document(node_id) for node_id in sorted(set(endpoint_ids))]
    return {snapshot.id for snapshot in client.get_all(refs) if snapshot.exists}


def _empty_result(table: str) -> Dict[str, Any]:
    return {
        "table": table,
        "merged": 0,
        "skipped": 0,
        "quarantined": 0,
        "deleted": 0,
        "nodes_evicted": 0,
        "edges_evicted": 0,
    }


def enforce_knowledge_graph_caps(uid: str, *, db_client: Any = None) -> Dict[str, int]:
    """Report response caps without deleting persisted graph data."""
    return {"nodes_evicted": 0, "edges_evicted": 0}


def merge_synced_local_kg_nodes(
    uid: str,
    rows: Iterable[Any],
    source_namespace: str,
    *,
    reconcile_complete: bool = False,
    db_client: Any = None,
) -> Dict[str, Any]:
    result = _empty_result("local_kg_nodes")
    namespace = namespace_for_source(source_namespace)
    if reconcile_complete:
        result["deleted"] = kg_db.delete_namespaced_knowledge_graph(uid, namespace, db_client=db_client)
    pending: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            result["skipped"] += 1
            continue
        node_data = _local_kg_node_to_firestore(row, source_namespace)
        if node_data is None:
            result["skipped"] += 1
            continue
        pending.append(node_data)
    merged = kg_db.merge_knowledge_nodes_batch(uid, pending, db_client=db_client) if pending else []
    result["merged"] = len(merged)
    return result


def merge_synced_local_kg_edges(
    uid: str,
    rows: Iterable[Any],
    source_namespace: str,
    *,
    reconcile_complete: bool = False,
    db_client: Any = None,
) -> Dict[str, Any]:
    result = _empty_result("local_kg_edges")
    namespace = namespace_for_source(source_namespace)
    if reconcile_complete:
        result["deleted"] = kg_db.delete_namespaced_knowledge_graph(uid, namespace, db_client=db_client)
    pending: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            result["skipped"] += 1
            continue
        edge_data = _local_kg_edge_to_firestore(row, source_namespace)
        if edge_data is None:
            result["skipped"] += 1
            continue
        pending.append(edge_data)
    endpoint_ids = {cast(str, edge[field]) for edge in pending for field in ("source_id", "target_id")}
    existing_endpoint_ids = _existing_node_ids(uid, endpoint_ids, db_client=db_client)
    valid_edges = [
        edge
        for edge in pending
        if edge["source_id"] in existing_endpoint_ids and edge["target_id"] in existing_endpoint_ids
    ]
    result["quarantined"] = len(pending) - len(valid_edges)
    merged = kg_db.merge_knowledge_edges_batch(uid, valid_edges, db_client=db_client) if valid_edges else []
    result["merged"] = len(merged)
    return result


def merge_synced_local_kg(
    uid: str,
    table: Literal["local_kg_nodes", "local_kg_edges"],
    rows: Iterable[Dict[str, Any]],
    source_namespace: str,
    *,
    reconcile_complete: bool = False,
    db_client: Any = None,
) -> Dict[str, Any]:
    if table == "local_kg_nodes":
        return merge_synced_local_kg_nodes(
            uid,
            rows,
            source_namespace,
            reconcile_complete=reconcile_complete,
            db_client=db_client,
        )
    return merge_synced_local_kg_edges(
        uid,
        rows,
        source_namespace,
        reconcile_complete=reconcile_complete,
        db_client=db_client,
    )
