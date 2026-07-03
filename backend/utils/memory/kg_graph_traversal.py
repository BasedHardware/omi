"""Bounded read-only knowledge-graph traversal for canonical cohort (WS-N).

The KG is stored in Firestore (``users/{uid}/knowledge_nodes`` +
``knowledge_edges``) via ``database.knowledge_graph`` — there is no live Neo4j
backend in this repo. Traversal is prod-inert for legacy users.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, cast

from database._client import db as default_db_client
from database import knowledge_graph as kg_db
from utils.memory.atom_keyword_index import is_indexable_long_term_atom
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items

logger = logging.getLogger(__name__)

GraphNode = Dict[str, Any]
GraphEdge = Dict[str, Any]
MemoryCitation = Dict[str, str]

# Q14 defaults — hop budget + fan-out + subgraph caps (long_term-only source).
MAX_TRAVERSAL_HOPS = int(os.environ.get("KG_TRAVERSAL_MAX_HOPS", "2"))
MAX_EDGES_PER_NODE = int(os.environ.get("KG_TRAVERSAL_MAX_EDGES_PER_NODE", "25"))
MAX_TRIPLES = int(os.environ.get("KG_TRAVERSAL_MAX_TRIPLES", "60"))


@dataclass(frozen=True)
class GraphTriple:
    source_id: str
    source_label: str
    relation: str
    target_id: str
    target_label: str
    memory_ids: Tuple[str, ...]
    hop_distance: int


def _empty_str_list() -> List[str]:
    return []


def _empty_triple_list() -> List[GraphTriple]:
    return []


def _empty_node_list() -> List[GraphNode]:
    return []


def _empty_citation_list() -> List[MemoryCitation]:
    return []


@dataclass
class TraversalResult:
    entity_query: str
    requested_hops: int
    effective_hops: int
    hops_capped: bool
    seed_node_ids: List[str] = field(default_factory=_empty_str_list)
    triples: List[GraphTriple] = field(default_factory=_empty_triple_list)
    nodes: List[GraphNode] = field(default_factory=_empty_node_list)
    memory_citations: List[MemoryCitation] = field(default_factory=_empty_citation_list)
    skipped_reason: Optional[str] = None


def user_allows_kg_traversal(uid: str, *, db_client: Any = None) -> bool:
    """Traversal is meaningful only for the canonical memory cohort."""
    return resolve_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL


def _long_term_memory_ids(uid: str, *, db_client: Any) -> Set[str]:
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
    return {item.memory_id for item in items if is_indexable_long_term_atom(item)}


def _normalize_hops(requested: int) -> Tuple[int, bool]:
    if requested < 1:
        return 1, True
    if requested > MAX_TRAVERSAL_HOPS:
        return MAX_TRAVERSAL_HOPS, True
    return requested, False


def _resolve_seed_node_ids(nodes: List[GraphNode], entity_query: str) -> List[str]:
    query = (entity_query or "").strip().lower()
    if not query:
        return []

    exact: List[str] = []
    partial: List[str] = []
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        label = (node.get("label") or "").lower()
        raw_aliases = node.get("aliases")
        aliases = (
            [str(alias).lower() for alias in cast(List[Any], raw_aliases)] if isinstance(raw_aliases, list) else []
        )
        if label == query or query in aliases:
            exact.append(node_id)
        elif query in label or any(query in alias for alias in aliases):
            partial.append(node_id)

    return exact or partial


def _build_adjacency(edges: List[GraphEdge]) -> Dict[str, List[GraphEdge]]:
    adjacency: Dict[str, List[GraphEdge]] = {}
    for edge in edges:
        source_id = edge.get("source_id")
        target_id = edge.get("target_id")
        if not source_id or not target_id:
            continue
        adjacency.setdefault(source_id, []).append(edge)
        reverse: GraphEdge = {
            "id": edge.get("id"),
            "source_id": target_id,
            "target_id": source_id,
            "label": edge.get("label", ""),
            "memory_ids": edge.get("memory_ids") or [],
            "_reversed": True,
        }
        adjacency.setdefault(target_id, []).append(reverse)
    return adjacency


def _edge_triple(
    edge: GraphEdge,
    nodes_by_id: Dict[str, GraphNode],
    hop_distance: int,
    allowed_memory_ids: Set[str],
) -> Optional[GraphTriple]:
    raw_memory_ids = edge.get("memory_ids")
    memory_ids = (
        tuple(
            memory_id
            for memory_id in cast(List[Any], raw_memory_ids)
            if isinstance(memory_id, str) and memory_id in allowed_memory_ids
        )
        if isinstance(raw_memory_ids, list)
        else ()
    )
    if not memory_ids:
        return None

    source = nodes_by_id.get(edge.get("source_id") or "")
    target = nodes_by_id.get(edge.get("target_id") or "")
    if not source or not target:
        return None

    return GraphTriple(
        source_id=source["id"],
        source_label=source.get("label", ""),
        relation=edge.get("label", ""),
        target_id=target["id"],
        target_label=target.get("label", ""),
        memory_ids=memory_ids,
        hop_distance=hop_distance,
    )


def traverse_knowledge_graph(
    uid: str,
    entity_query: str,
    *,
    hops: int = 1,
    db_client: Any = None,
    graph: Optional[Dict[str, Any]] = None,
) -> TraversalResult:
    """Read-only BFS neighborhood expansion capped at ``MAX_TRAVERSAL_HOPS``."""
    client = db_client if db_client is not None else default_db_client
    effective_hops, hops_capped = _normalize_hops(hops)
    result = TraversalResult(
        entity_query=entity_query,
        requested_hops=hops,
        effective_hops=effective_hops,
        hops_capped=hops_capped,
    )

    if not user_allows_kg_traversal(uid, db_client=client):
        result.skipped_reason = "not_canonical_cohort"
        return result

    allowed_memory_ids = _long_term_memory_ids(uid, db_client=client)
    if graph is None:
        get_knowledge_graph = cast(Callable[[str], Dict[str, Any]], getattr(kg_db, "get_knowledge_graph"))
        graph = get_knowledge_graph(uid)

    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    nodes = cast(List[GraphNode], raw_nodes) if isinstance(raw_nodes, list) else []
    edges = cast(List[GraphEdge], raw_edges) if isinstance(raw_edges, list) else []
    nodes_by_id: Dict[str, GraphNode] = {
        node_id: node for node in nodes if isinstance((node_id := node.get("id")), str)
    }
    result.seed_node_ids = _resolve_seed_node_ids(nodes, entity_query)
    if not result.seed_node_ids:
        return result

    adjacency = _build_adjacency(edges)
    visited_nodes: Set[str] = set()
    collected_edge_ids: Set[str] = set()
    collected_triples: List[GraphTriple] = []
    collected_node_ids: Set[str] = set(result.seed_node_ids)

    frontier: List[Tuple[str, int]] = [(node_id, 0) for node_id in result.seed_node_ids]
    for node_id in result.seed_node_ids:
        visited_nodes.add(node_id)

    while frontier and len(collected_triples) < MAX_TRIPLES:
        current_id, depth = frontier.pop(0)
        if depth >= effective_hops:
            continue

        node_edges = adjacency.get(current_id, [])[:MAX_EDGES_PER_NODE]
        for edge in node_edges:
            edge_id = edge.get("id")
            if edge_id and edge_id in collected_edge_ids:
                continue

            triple = _edge_triple(edge, nodes_by_id, depth + 1, allowed_memory_ids)
            if triple is None:
                continue

            if edge_id:
                collected_edge_ids.add(edge_id)
            collected_triples.append(triple)
            if len(collected_triples) >= MAX_TRIPLES:
                break

            neighbor_id = edge.get("target_id")
            if neighbor_id:
                collected_node_ids.add(neighbor_id)
                if neighbor_id not in visited_nodes and depth + 1 < effective_hops:
                    visited_nodes.add(neighbor_id)
                    frontier.append((neighbor_id, depth + 1))

    result.triples = collected_triples
    result.nodes = [nodes_by_id[node_id] for node_id in sorted(collected_node_ids) if node_id in nodes_by_id]

    cited_ids: List[str] = []
    seen_citations: Set[str] = set()
    for triple in collected_triples:
        for memory_id in triple.memory_ids:
            if memory_id not in seen_citations:
                seen_citations.add(memory_id)
                cited_ids.append(memory_id)

    if cited_ids:
        items_by_id = {
            item.memory_id: item for item in fetch_authoritative_product_memory_items(uid=uid, db_client=client)
        }
        for memory_id in cited_ids:
            item = items_by_id.get(memory_id)
            if item and is_indexable_long_term_atom(item):
                result.memory_citations.append({"memory_id": memory_id, "content": (item.content or "").strip()})

    return result


def format_traversal_result(result: TraversalResult) -> str:
    if result.skipped_reason == "not_canonical_cohort":
        return "Knowledge graph traversal is unavailable for this account."

    if not result.seed_node_ids:
        return f"No knowledge-graph entities matched '{result.entity_query}'."

    lines = [
        f"Knowledge graph neighborhood for '{result.entity_query}' "
        f"({result.effective_hops} hop{'s' if result.effective_hops != 1 else ''}"
        f"{', hop budget capped' if result.hops_capped else ''}):",
        "",
    ]

    if not result.triples:
        lines.append("No connected long-term relationships found within the hop budget.")
        return "\n".join(lines)

    for triple in result.triples:
        lines.append(
            f"- {triple.source_label} --{triple.relation}--> {triple.target_label} "
            f"(hop {triple.hop_distance}, memories: {', '.join(triple.memory_ids)})"
        )

    if result.memory_citations:
        lines.append("")
        lines.append("Cited long-term atoms:")
        for citation in result.memory_citations:
            lines.append(f"- [{citation['memory_id']}] {citation['content']}")

    if len(result.triples) >= MAX_TRIPLES:
        lines.append("")
        lines.append(f"(Subgraph capped at {MAX_TRIPLES} triples.)")

    return "\n".join(lines)
