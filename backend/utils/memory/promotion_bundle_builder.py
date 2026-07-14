from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple, cast

from database import memory_ledger
from models.product_memory import MemoryAccessPolicy
from utils.memory.projections import rebuild_memory_memory_projections
from utils.memory_ingestion.ids import canonical_json

try:
    from utils.memory import vector_search_service as _vector_search_service

    _vector_search_import_error: Exception | None = None
except Exception as exc:
    _vector_search_service = None
    _vector_search_import_error = exc

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)
_STOPWORDS = {
    'the',
    'a',
    'an',
    'and',
    'or',
    'to',
    'of',
    'in',
    'is',
    'are',
    'was',
    'were',
    'user',
    'prefers',
    'likes',
    'has',
    'have',
    'with',
    'for',
    'on',
    'that',
    'this',
    'it',
    'manual',
    'automatic',
}

Payload = Dict[str, Any]
PayloadList = List[Payload]
ScoredMemory = Tuple[float, List[str], Payload]


class DefaultVectorSearchService(Protocol):
    def __call__(
        self,
        uid: str,
        query: str,
        *,
        db_client: Any,
        policy: MemoryAccessPolicy,
        limit: int,
        required_projection_commit_id: str,
        required_account_generation: int,
    ) -> Payload:
        ...


def _default_vector_search_service() -> DefaultVectorSearchService | None:
    if _vector_search_service is None:
        return None
    return cast(DefaultVectorSearchService, getattr(_vector_search_service, 'fetch_default_vector_memory_search'))


def _empty_payload() -> Payload:
    return {}


def _payload_or_empty(value: object) -> Payload:
    return cast(Payload, value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class PromotionBundleConfig:
    vector_seed_limit: int = 8
    graph_hops: int = 2
    graph_node_budget: int = 80
    graph_edge_budget: int = 120
    packet_group_mode: str = 'theme'

    def __post_init__(self):
        if self.vector_seed_limit < 0:
            raise ValueError('vector_seed_limit must be non-negative')
        if self.graph_hops < 0:
            raise ValueError('graph_hops must be non-negative')
        if self.graph_node_budget < 1:
            raise ValueError('graph_node_budget must be positive')
        if self.graph_edge_budget < 1:
            raise ValueError('graph_edge_budget must be positive')
        if self.packet_group_mode not in {'theme', 'observation'}:
            raise ValueError('packet_group_mode must be theme or observation')


@dataclass(frozen=True)
class PromotionBundle:
    schema_version: str
    bundle_id: str
    uid: str
    session_ids: List[str]
    l1_items: PayloadList
    evidence_packets: PayloadList
    vector_seed: PayloadList
    graph_snapshot: Payload
    observed_head_commit_id: Optional[str]
    observed_head: Optional[str] = None
    config: Payload = field(default_factory=_empty_payload)

    def to_dict(self) -> Payload:
        return {
            'schema_version': self.schema_version,
            'bundle_id': self.bundle_id,
            'uid': self.uid,
            'session_ids': self.session_ids,
            'l1_items': self.l1_items,
            'evidence_packets': self.evidence_packets,
            'vector_seed': self.vector_seed,
            'graph_snapshot': self.graph_snapshot,
            'observed_head_commit_id': self.observed_head_commit_id,
            'observed_head': self.observed_head,
            'config': self.config,
        }


class UngroundedPromotionError(RuntimeError):
    pass


VectorSeedFetcher = Callable[[str, str, int], PayloadList]
GraphSnapshotFetcher = Callable[[str, PayloadList, PromotionBundleConfig], Payload]
HeadReader = Callable[[str], Optional[str]]
DurableFactsFetcher = Callable[[str], PayloadList]


def stable_id(namespace: str, payload: Payload) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(f'{namespace}|{serialized}'.encode('utf-8')).hexdigest()[:20]


_canonical_json = canonical_json


def tokens(text: str) -> set[str]:
    return {
        token.lower() for token in _TOKEN_RE.findall(text or '') if len(token) > 2 and token.lower() not in _STOPWORDS
    }


def retrieve_existing_memories(query_text: str, existing_memories: Iterable[Payload], limit: int = 8) -> PayloadList:
    query_tokens = tokens(query_text)
    if not query_tokens or limit <= 0:
        return []
    scored: List[ScoredMemory] = []
    for memory in existing_memories:
        memory_tokens = tokens(str(memory.get('content') or memory.get('memory_text') or ''))
        overlap = query_tokens.intersection(memory_tokens)
        if not overlap:
            continue
        score = len(overlap) / max(len(query_tokens), 1)
        scored.append((score, sorted(overlap), memory))
    scored.sort(key=lambda item: (-item[0], str(item[2].get('memory_id') or item[2].get('id') or '')))
    return [
        {
            'memory_id': memory.get('memory_id') or memory.get('id') or memory.get('card_id'),
            'content': memory.get('content') or memory.get('memory_text') or '',
            'status': memory.get('status') or memory.get('memory_state') or 'active',
            'score': round(score, 4),
            'matched_terms': overlap,
            'retrieval_reason': 'lexical_overlap',
        }
        for score, overlap, memory in scored[:limit]
    ]


def _group_key(observation: Payload, group_mode: str) -> Tuple[str, str, str]:
    if group_mode == 'observation':
        return (
            str(observation.get('session_id') or observation.get('source_id') or 'unknown_source'),
            str(observation.get('observation_id') or observation.get('id') or observation.get('content') or ''),
            str(observation.get('status') or 'working'),
        )
    return (
        str(observation.get('session_id') or observation.get('source_id') or 'unknown_source'),
        str(observation.get('packet_theme') or observation.get('candidate_kind_hint') or 'unclassified'),
        str(observation.get('status') or 'working'),
    )


def build_l2_packets(
    observations: PayloadList,
    existing_memories: Iterable[Payload],
    *,
    run_id: str = 'l2_promotion_bundle_builder',
    group_mode: str = 'theme',
) -> PayloadList:
    groups: Dict[Tuple[str, str, str], PayloadList] = defaultdict(list)
    for observation in observations:
        groups[_group_key(observation, group_mode)].append(observation)

    packets: PayloadList = []
    existing = list(existing_memories)
    for key, rows in sorted(groups.items(), key=lambda item: item[0]):
        source_id, theme, status = key
        ordered_rows = sorted(rows, key=lambda row: str(row.get('observation_id') or row.get('id') or ''))
        packet_text = '\n'.join(str(row.get('content') or row.get('text') or '') for row in ordered_rows)
        evidence_ids: List[str] = []
        source_refs: PayloadList = []
        for row in ordered_rows:
            row_evidence_ids = row.get('evidence_ids')
            if isinstance(row_evidence_ids, list):
                evidence_ids.extend(str(value) for value in cast(List[object], row_evidence_ids) if value)
            row_source_refs = row.get('source_refs')
            if isinstance(row_source_refs, list):
                source_refs.extend(
                    cast(Payload, value) for value in cast(List[object], row_source_refs) if isinstance(value, dict)
                )
        packet_id = 'pkt_' + stable_id(
            'memory-l2-packet',
            {
                'source_id': source_id,
                'theme': theme,
                'status': status,
                'observation_ids': [row.get('observation_id') or row.get('id') for row in ordered_rows],
            },
        )
        retrieved = retrieve_existing_memories(packet_text, existing)
        packets.append(
            {
                'schema_version': 'l2_evidence_packet.v1',
                'builder_version': 'product_promotion_bundle_builder_v1',
                'run_id': run_id,
                'packet_id': packet_id,
                'packet_theme': theme,
                'status': status,
                'observation_ids': [row.get('observation_id') or row.get('id') for row in ordered_rows],
                'source_example_ids': sorted(
                    str(value)
                    for value in {
                        row.get('session_id') or row.get('source_id')
                        for row in ordered_rows
                        if row.get('session_id') or row.get('source_id')
                    }
                ),
                'source_types': sorted(str(row.get('source_type')) for row in ordered_rows if row.get('source_type')),
                'evidence_ids': sorted(set(evidence_ids)),
                'source_refs': source_refs,
                'observations': ordered_rows,
                'retrieved_memory_context': retrieved,
                'retrieval_status': 'empty' if not retrieved else 'found',
            }
        )
    return packets


def _query_text(l1_items: PayloadList) -> str:
    return '\n'.join(str(item.get('content') or item.get('text') or '') for item in l1_items)


def fetch_durable_facts_from_ledger(uid: str) -> PayloadList:
    return list(memory_ledger.replay_to(uid).values())


def vector_seed_from_durable_facts(query: str, durable_facts: Iterable[Payload], limit: int) -> PayloadList:
    return retrieve_existing_memories(query, durable_facts, limit=limit)


def make_vector_seed_fetcher(
    *,
    db_client: Any = None,
    policy: Optional[MemoryAccessPolicy] = None,
    required_projection_commit_id: Optional[str] = None,
    required_account_generation: int = 0,
) -> VectorSeedFetcher:
    def fetch(uid: str, query: str, limit: int) -> PayloadList:
        vector_search = _default_vector_search_service()
        if vector_search is None or db_client is None or policy is None or not required_projection_commit_id:
            return vector_seed_from_durable_facts(query, fetch_durable_facts_from_ledger(uid), limit)
        response = vector_search(
            uid,
            query,
            db_client=db_client,
            policy=policy,
            limit=limit,
            required_projection_commit_id=required_projection_commit_id,
            required_account_generation=required_account_generation,
        )
        items = response.get('items')
        return [item for item in cast(List[object], items) if isinstance(item, dict)] if isinstance(items, list) else []

    return fetch


def _subject_keys(items: PayloadList) -> set[str]:
    keys: set[str] = set()
    for item in items:
        for key in ('subject_entity_id', 'subject', 'about'):
            value = item.get(key)
            if value:
                keys.add(str(value))
    return keys


def build_bounded_graph_snapshot(
    uid: str,
    l1_items: PayloadList,
    config: PromotionBundleConfig,
    durable_facts: Optional[Iterable[Payload]] = None,
) -> Payload:
    subjects = _subject_keys(l1_items)
    projections = rebuild_memory_memory_projections(list(durable_facts or []))
    raw_projected_graph: object = projections.get('graph')
    projected_graph = _payload_or_empty(raw_projected_graph)
    nodes: Dict[str, Payload] = {}
    edges: PayloadList = []
    projected_nodes = (
        cast(Dict[str, Payload], projected_graph.get('nodes')) if isinstance(projected_graph.get('nodes'), dict) else {}
    )
    projected_edges = projected_graph.get('edges')
    for edge in cast(List[object], projected_edges) if isinstance(projected_edges, list) else []:
        if not isinstance(edge, dict):
            continue
        edge_payload = cast(Payload, edge)
        subject = edge_payload.get('subject_entity_id')
        raw_arguments = edge_payload.get('arguments')
        arguments = cast(Payload, raw_arguments) if isinstance(raw_arguments, dict) else {}
        obj = arguments.get('object') or arguments.get('object_entity_id')
        fact_id = edge_payload.get('memory_id') or edge_payload.get('fact_id')
        include = not subjects or subject in subjects or obj in subjects
        if not include:
            continue
        if subject and len(nodes) < config.graph_node_budget:
            nodes.setdefault(str(subject), projected_nodes.get(str(subject)) or {'entity_id': str(subject)})
        if obj and len(nodes) < config.graph_node_budget:
            nodes.setdefault(str(obj), projected_nodes.get(str(obj)) or {'entity_id': str(obj)})
        if len(edges) < config.graph_edge_budget:
            edges.append(
                {
                    'fact_id': fact_id,
                    'edge_id': edge_payload.get('edge_id'),
                    'subject_entity_id': subject,
                    'predicate': edge_payload.get('predicate'),
                    'object': obj,
                    'arguments': arguments,
                    'content': edge_payload.get('content'),
                }
            )
    return {
        'schema_version': 'bounded_graph_snapshot.v1',
        'uid': uid,
        'seed_subjects': sorted(subjects),
        'hops': config.graph_hops,
        'nodes': list(nodes.values()),
        'edges': edges,
        'node_budget': config.graph_node_budget,
        'edge_budget': config.graph_edge_budget,
    }


def build_promotion_bundle(
    *,
    uid: str,
    session_ids: List[str],
    l1_items: PayloadList,
    existing_memories: Optional[Iterable[Payload]] = None,
    durable_facts: Optional[Iterable[Payload]] = None,
    durable_facts_fetcher: Optional[DurableFactsFetcher] = None,
    vector_seed_fetcher: Optional[VectorSeedFetcher] = None,
    graph_snapshot_fetcher: Optional[GraphSnapshotFetcher] = None,
    head_reader: Optional[HeadReader] = None,
    config: Optional[PromotionBundleConfig] = None,
) -> PromotionBundle:
    if not uid or not uid.strip():
        raise ValueError('uid is required')
    cfg = config or PromotionBundleConfig()
    ordered_l1 = sorted(
        l1_items, key=lambda item: str(item.get('created_at') or item.get('id') or item.get('memory_id') or '')
    )
    query = _query_text(ordered_l1)
    resolved_durable_facts = (
        list(durable_facts)
        if durable_facts is not None
        else (durable_facts_fetcher(uid) if durable_facts_fetcher is not None else fetch_durable_facts_from_ledger(uid))
    )
    if vector_seed_fetcher is None:
        vector_seed = vector_seed_from_durable_facts(query, resolved_durable_facts, cfg.vector_seed_limit)
    else:
        vector_seed = vector_seed_fetcher(uid, query, cfg.vector_seed_limit)
    existing = list(existing_memories) if existing_memories is not None else vector_seed
    packets = build_l2_packets(ordered_l1, existing, group_mode=cfg.packet_group_mode)
    if graph_snapshot_fetcher is not None:
        graph_snapshot = graph_snapshot_fetcher(uid, ordered_l1, cfg)
    else:
        graph_snapshot = build_bounded_graph_snapshot(uid, ordered_l1, cfg, resolved_durable_facts)
    read_head = head_reader or memory_ledger.read_head
    observed_head_commit_id = read_head(uid)
    bundle_id = 'pbn_' + stable_id(
        'promotion-bundle',
        {
            'uid': uid,
            'session_ids': session_ids,
            'l1_item_ids': [
                item.get('id') or item.get('memory_id') or item.get('observation_id') for item in ordered_l1
            ],
            'observed_head_commit_id': observed_head_commit_id,
        },
    )
    return PromotionBundle(
        schema_version='promotion_bundle.v1',
        bundle_id=bundle_id,
        uid=uid,
        session_ids=list(session_ids),
        l1_items=ordered_l1,
        evidence_packets=packets,
        vector_seed=vector_seed,
        graph_snapshot=graph_snapshot,
        observed_head_commit_id=observed_head_commit_id,
        observed_head=observed_head_commit_id,
        config={
            'vector_seed_limit': cfg.vector_seed_limit,
            'graph_hops': cfg.graph_hops,
            'graph_node_budget': cfg.graph_node_budget,
            'graph_edge_budget': cfg.graph_edge_budget,
            'packet_group_mode': cfg.packet_group_mode,
        },
    )


def enforce_grounded_promotion_bundle(bundle: Payload, *, environment: str = 'dev') -> Payload:
    if not bundle.get('observed_head_commit_id'):
        return {'ok': True, 'reason': 'no_existing_head'}
    raw_vector_seed = bundle.get('vector_seed')
    vector_seed: List[object] = cast(List[object], raw_vector_seed) if isinstance(raw_vector_seed, list) else []
    raw_graph_snapshot = bundle.get('graph_snapshot')
    graph_snapshot = cast(Payload, raw_graph_snapshot) if isinstance(raw_graph_snapshot, dict) else {}
    raw_graph_edges = graph_snapshot.get('edges')
    graph_edges: List[object] = cast(List[object], raw_graph_edges) if isinstance(raw_graph_edges, list) else []
    if vector_seed or graph_edges:
        return {
            'ok': True,
            'reason': 'grounding_nonempty',
            'vector_seed_count': len(vector_seed),
            'graph_edge_count': len(graph_edges),
        }
    payload = {
        'ok': False,
        'error': 'ungrounded_promotion',
        'uid': bundle.get('uid'),
        'bundle_id': bundle.get('bundle_id'),
        'observed_head_commit_id': bundle.get('observed_head_commit_id'),
        'vector_seed_count': 0,
        'graph_edge_count': 0,
    }
    if environment in {'prod', 'production'}:
        return payload
    raise UngroundedPromotionError(_canonical_json(payload))
