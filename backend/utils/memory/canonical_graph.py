"""Bounded, revision-fenced reads for the canonical memory knowledge graph."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import knowledge_graph as kg_db
from database._client import get_firestore_client
from database.firestore_index_registry import CANONICAL_MEMORY_ATLAS_READ_QUERY
from database.memory_collections import MemoryCollections
from models.memory_promotion import MemoryGraphAssertion
from models.product_memory import RESTRICTED_SENSITIVITY_LABELS
from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason,
    V3TrustedAccountGenerationResult,
    read_memory_v3_trusted_account_generation,
)
from utils.memory.v3.cursor import (
    V3CursorContext,
    V3CursorError,
    V3Keyset,
    create_v3_cursor,
    parse_v3_cursor,
)
from utils.memory.v3.keyset_datetime import KeysetTimeUnit, decode_keyset_time, encode_keyset_time

DEFAULT_CANONICAL_GRAPH_PAGE_LIMIT = 200
MAX_CANONICAL_GRAPH_PAGE_LIMIT = 500
CANONICAL_GRAPH_CURSOR_SOURCE = 'canonical_memory_graph'
CANONICAL_GRAPH_CURSOR_READ_MODE = 'canonical_graph'
CANONICAL_GRAPH_CURSOR_FILTER = 'canonical_graph_v2:updated_at_desc:memory_id_desc'
CANONICAL_GRAPH_CURSOR_TTL_SECONDS = 600
KNOWLEDGE_GRAPH_DOCUMENT_ORDER = '__name__'
CANONICAL_GRAPH_REVISION_READ_RETRIES = 2


class CanonicalGraphCursorError(ValueError):
    """Raised when a canonical graph cursor is invalid, stale, or unavailable."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class CanonicalGraphReadUnavailable(RuntimeError):
    """Raised when the canonical graph cannot establish its trusted read fence."""


@dataclass(frozen=True)
class CanonicalKnowledgeGraphPage:
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    has_more: bool
    next_cursor: Optional[str]
    catalog_nodes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _CanonicalGraphCursorBoundary:
    item: Dict[str, Any]
    updated_at: datetime
    memory_id: str


@dataclass(frozen=True)
class _CanonicalGraphRevision:
    account_generation: int
    commit_sequence: int
    head_commit_id: str


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _enum_value(value: Any) -> Any:
    return getattr(value, 'value', value)


def _firestore_client(db_client: Any = None) -> Any:
    return db_client if db_client is not None else get_firestore_client()


def _revision_from_trusted(trusted: V3TrustedAccountGenerationResult) -> Optional[_CanonicalGraphRevision]:
    """Build the revision fence from a trusted head read, or ``None`` if malformed."""
    if (
        trusted.account_generation is None
        or trusted.commit_sequence is None
        or not isinstance(trusted.head_commit_id, str)
        or not trusted.head_commit_id
    ):
        return None
    return _CanonicalGraphRevision(
        account_generation=trusted.account_generation,
        commit_sequence=trusted.commit_sequence,
        head_commit_id=trusted.head_commit_id,
    )


def _read_canonical_graph_revision(uid: str, *, db_client: Any) -> _CanonicalGraphRevision:
    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
    if trusted.read_error_reason is not None:
        raise CanonicalGraphReadUnavailable(trusted.read_error_reason.value)
    revision = _revision_from_trusted(trusted)
    if revision is None:
        raise CanonicalGraphReadUnavailable('malformed_memory_state_head')
    return revision


class CanonicalGraphState(str, Enum):
    """Tri-state answer to "is canonical graph state established for this account?".

    ``UNESTABLISHED`` is a positive answer: the state-head document is genuinely
    absent, so no derived state exists. ``INDETERMINATE`` means the question was
    not answered — a timed-out read, a corrupt head, a schema the reader does not
    understand. A caller deciding whether derived state exists must never
    collapse ``INDETERMINATE`` into ``UNESTABLISHED``: on a destructive path that
    turns a transient Firestore blip into permanent data loss.
    """

    ESTABLISHED = 'established'
    UNESTABLISHED = 'unestablished'
    INDETERMINATE = 'indeterminate'


def probe_canonical_graph_state(uid: str, *, db_client: Any = None) -> CanonicalGraphState:
    """One-document probe of the canonical revision fence.

    ``users/{uid}/memory_state/head`` is the fence every canonical graph read is
    built on, and only the canonical apply transaction writes it. Its existence
    — not whether a materialized page happens to carry assertions — is the
    "canonical state is established" signal, so this reads the head directly
    instead of paging the atlas. That also keeps the probe independent of
    ``MEMORY_V3_CURSOR_SECRET`` and of the atlas composite index.
    """
    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=_firestore_client(db_client))
    reason = trusted.read_error_reason
    if reason is V3AccountGenerationFailureReason.MISSING_STATE_HEAD:
        return CanonicalGraphState.UNESTABLISHED
    if reason is not None:
        return CanonicalGraphState.INDETERMINATE
    if _revision_from_trusted(trusted) is None:
        return CanonicalGraphState.INDETERMINATE
    return CanonicalGraphState.ESTABLISHED


def _canonical_graph_cursor_secret() -> bytes:
    raw_secret = os.environ.get('MEMORY_V3_CURSOR_SECRET') or ''
    if not raw_secret:
        raise CanonicalGraphReadUnavailable('missing_cursor_secret')
    return raw_secret.encode('utf-8')


def _canonical_graph_cursor_ttl_seconds() -> int:
    raw_ttl = os.environ.get('MEMORY_V3_CURSOR_TTL_SECONDS') or ''
    if not raw_ttl:
        return CANONICAL_GRAPH_CURSOR_TTL_SECONDS
    try:
        return max(1, int(raw_ttl))
    except ValueError:
        return CANONICAL_GRAPH_CURSOR_TTL_SECONDS


def _canonical_graph_cursor_context(
    uid: str,
    revision: _CanonicalGraphRevision,
    *,
    now_epoch_seconds: Optional[int] = None,
) -> V3CursorContext:
    return V3CursorContext(
        uid=uid,
        account_generation=revision.account_generation,
        # The trusted state-head commit sequence is the canonical graph's
        # revision fence. It advances with every canonical apply commit.
        projection_generation=revision.commit_sequence,
        filter_hash=f'{CANONICAL_GRAPH_CURSOR_FILTER}:{revision.head_commit_id}',
        source=CANONICAL_GRAPH_CURSOR_SOURCE,
        read_mode=CANONICAL_GRAPH_CURSOR_READ_MODE,
        now_epoch_seconds=(
            now_epoch_seconds if now_epoch_seconds is not None else int(datetime.now(tz=timezone.utc).timestamp())
        ),
    )


def _canonical_graph_cursor_time(value: datetime) -> int:
    try:
        return encode_keyset_time(value, KeysetTimeUnit.MICROSECONDS)
    except ValueError as exc:
        raise CanonicalGraphCursorError('malformed_cursor_boundary') from exc


def _canonical_graph_time_from_cursor(value: Any) -> datetime:
    try:
        return decode_keyset_time(value, KeysetTimeUnit.MICROSECONDS)
    except ValueError as exc:
        raise CanonicalGraphCursorError('malformed_cursor_boundary') from exc


def _canonical_graph_decode_cursor(
    cursor: str,
    *,
    uid: str,
    revision: _CanonicalGraphRevision,
    secret: bytes,
) -> Tuple[datetime, str]:
    context = _canonical_graph_cursor_context(uid, revision)
    try:
        claims = parse_v3_cursor(cursor, context, secret)
    except V3CursorError as exc:
        raise CanonicalGraphCursorError(exc.reason) from exc
    except (TypeError, ValueError) as exc:
        raise CanonicalGraphCursorError('malformed_cursor') from exc
    memory_id = claims.keyset.memory_id
    if not memory_id.strip():
        raise CanonicalGraphCursorError('malformed_cursor_boundary')
    return _canonical_graph_time_from_cursor(claims.keyset.created_at_ms), memory_id


def _canonical_graph_encode_cursor(
    *,
    uid: str,
    revision: _CanonicalGraphRevision,
    updated_at: datetime,
    memory_id: str,
    secret: bytes,
) -> str:
    context = _canonical_graph_cursor_context(uid, revision)
    try:
        return create_v3_cursor(
            V3Keyset(
                created_at_ms=_canonical_graph_cursor_time(updated_at),
                memory_id=memory_id,
            ),
            context,
            secret,
            ttl_seconds=_canonical_graph_cursor_ttl_seconds(),
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalGraphReadUnavailable('cursor_encoding_failed') from exc


def _canonical_graph_item_order_key(item: Dict[str, Any]) -> Optional[Tuple[datetime, str]]:
    updated_at = item.get('updated_at')
    memory_id = item.get('memory_id')
    if (
        not isinstance(updated_at, datetime)
        or updated_at.tzinfo is None
        or updated_at.utcoffset() is None
        or not isinstance(memory_id, str)
        or not memory_id.strip()
    ):
        return None
    return updated_at, memory_id


def _canonical_graph_query_item_is_eligible(
    uid: str,
    item: Dict[str, Any],
    *,
    account_generation: int,
) -> bool:
    item_account_generation = item.get('account_generation')
    promotion = item.get('promotion')
    sensitivity_labels = item.get('sensitivity_labels')
    if not isinstance(promotion, dict) or not isinstance(sensitivity_labels, list):
        return False
    if any(not isinstance(label, str) for label in sensitivity_labels):
        return False
    return (
        item.get('uid') == uid
        and isinstance(item.get('memory_id'), str)
        and not isinstance(item_account_generation, bool)
        and isinstance(item_account_generation, int)
        and item_account_generation == account_generation
        and _enum_value(item.get('status')) == 'active'
        and _enum_value(item.get('tier')) == 'long_term'
        and _enum_value(item.get('processing_state')) == 'processed'
        and _enum_value(item.get('source_state')) == 'active'
        and not set(sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and promotion.get('is_locked') is not True
        and promotion.get('user_review') is not False
    )


def _canonical_graph_snapshot_item(
    uid: str,
    snapshot: Any,
    *,
    account_generation: int,
) -> Optional[Dict[str, Any]]:
    item = _typed_doc(snapshot)
    snapshot_id = getattr(snapshot, 'id', None)
    if snapshot_id != item.get('memory_id') or _canonical_graph_item_order_key(item) is None:
        return None
    if not _canonical_graph_query_item_is_eligible(
        uid,
        item,
        account_generation=account_generation,
    ):
        return None
    return item


def _canonical_graph_cursor_boundary_from_snapshot(snapshot: Any) -> _CanonicalGraphCursorBoundary:
    cursor_item = _typed_doc(snapshot)
    if (
        getattr(snapshot, 'id', None) != cursor_item.get('memory_id')
        or _canonical_graph_item_order_key(cursor_item) is None
    ):
        raise CanonicalGraphReadUnavailable('malformed_cursor_boundary')
    cursor_updated_at = cursor_item.get('updated_at')
    cursor_memory_id = cursor_item.get('memory_id')
    if not isinstance(cursor_updated_at, datetime) or not isinstance(cursor_memory_id, str):
        raise CanonicalGraphReadUnavailable('malformed_cursor_boundary')
    return _CanonicalGraphCursorBoundary(
        item=cursor_item,
        updated_at=cursor_updated_at,
        memory_id=cursor_memory_id,
    )


def _build_canonical_graph_items_query(
    client: Any,
    uid: str,
    revision: _CanonicalGraphRevision,
    *,
    cursor_boundary: Optional[Tuple[datetime, str]],
):
    items_ref = client.collection(MemoryCollections(uid=uid).memory_items)
    query = CANONICAL_MEMORY_ATLAS_READ_QUERY.build(
        items_ref,
        {
            'account_generation': revision.account_generation,
            'tier': 'long_term',
            'status': 'active',
            'processing_state': 'processed',
        },
        field_filter_factory=FieldFilter,
    )
    query = query.order_by('updated_at', direction=firestore.Query.DESCENDING).order_by(
        KNOWLEDGE_GRAPH_DOCUMENT_ORDER,
        direction=firestore.Query.DESCENDING,
    )
    if cursor_boundary is not None:
        query = query.start_after(
            {
                'updated_at': cursor_boundary[0],
                KNOWLEDGE_GRAPH_DOCUMENT_ORDER: items_ref.document(cursor_boundary[1]),
            }
        )
    return query


def _canonical_memory_catalog_node(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Represent every durable canonical memory without inventing a relationship.

    The catalog is the one-to-one memory browser. Assertion-backed entities and
    relationships remain exclusively in the fenced graph records below, so the
    atlas never needs to infer a relationship merely to show a memory.
    """
    content = item.get('content')
    memory_id = item.get('memory_id')
    updated_at = item.get('updated_at')
    if not isinstance(content, str) or not isinstance(memory_id, str) or not isinstance(updated_at, datetime):
        return None
    label = ' '.join(content.split())
    # Eligibility, authority, and access are decided before presentation. A
    # historical item with blank source text is still a canonical memory; do
    # not erase it from the user's one-to-one browser merely because it has no
    # safe text to display. The fallback makes no semantic claim or edge.
    if not label:
        label = 'Untitled canonical memory'
    return {
        'id': f'memory:{memory_id}',
        'label': label[:240],
        'node_type': 'concept',
        'aliases': [],
        'memory_ids': [memory_id],
        'created_at': item.get('captured_at') or updated_at,
        'updated_at': updated_at,
    }


def _read_canonical_graph_page_once(
    uid: str,
    *,
    db_client: Any,
    limit: int,
    cursor: Optional[str],
) -> CanonicalKnowledgeGraphPage:
    client = _firestore_client(db_client)
    secret = _canonical_graph_cursor_secret()
    revision = _read_canonical_graph_revision(uid, db_client=client)
    cursor_boundary: Optional[Tuple[datetime, str]] = None
    if cursor is not None:
        cursor_boundary = _canonical_graph_decode_cursor(
            cursor,
            uid=uid,
            revision=revision,
            secret=secret,
        )

    accepted_assertions: List[MemoryGraphAssertion] = []
    catalog_nodes: List[Dict[str, Any]] = []
    visible_memory_ids: set[str] = set()
    pending_snapshots: List[Any] = []
    pending_window_has_more = False
    last_consumed_snapshot: Any = None
    query_boundary = cursor_boundary

    while True:
        while len(visible_memory_ids) < limit:
            if not pending_snapshots:
                query = _build_canonical_graph_items_query(
                    client,
                    uid,
                    revision,
                    cursor_boundary=query_boundary,
                )
                snapshots = list(query.limit(limit + 1).stream())
                if not snapshots:
                    pending_window_has_more = False
                    break
                pending_window_has_more = len(snapshots) > limit
                pending_snapshots = list(snapshots)

            snapshot = pending_snapshots.pop(0)
            last_consumed_snapshot = snapshot

            eligible_batch: List[Dict[str, Any]] = []
            while True:
                item = _canonical_graph_snapshot_item(
                    uid,
                    snapshot,
                    account_generation=revision.account_generation,
                )
                if item is not None:
                    eligible_batch.append(item)
                if len(visible_memory_ids) + len(eligible_batch) >= limit or not pending_snapshots:
                    break
                snapshot = pending_snapshots.pop(0)
                last_consumed_snapshot = snapshot

            if eligible_batch:
                memory_ids = [cast(str, item['memory_id']) for item in eligible_batch]
                loaded_assertions = kg_db.load_fenced_assertions_for_memory_items(
                    uid,
                    memory_ids,
                    account_generation=revision.account_generation,
                    db_client=client,
                )
                for assertion in loaded_assertions:
                    accepted_assertions.append(assertion)
                    visible_memory_ids.add(assertion.memory_id)
                for item in eligible_batch:
                    memory_id = cast(str, item['memory_id'])
                    catalog_node = _canonical_memory_catalog_node(item)
                    if catalog_node is not None:
                        catalog_nodes.append(catalog_node)
                        visible_memory_ids.add(memory_id)

            if len(visible_memory_ids) >= limit:
                break
            if not pending_snapshots and not pending_window_has_more:
                break

            if not pending_snapshots and pending_window_has_more:
                if last_consumed_snapshot is None:
                    raise CanonicalGraphReadUnavailable('missing_cursor_boundary')
                boundary = _canonical_graph_cursor_boundary_from_snapshot(last_consumed_snapshot)
                query_boundary = (boundary.updated_at, boundary.memory_id)
                pending_window_has_more = False

        if pending_snapshots:
            has_more = True
        elif pending_window_has_more:
            if last_consumed_snapshot is None:
                raise CanonicalGraphReadUnavailable('missing_cursor_boundary')
            boundary = _canonical_graph_cursor_boundary_from_snapshot(last_consumed_snapshot)
            probe_query = _build_canonical_graph_items_query(
                client,
                uid,
                revision,
                cursor_boundary=(boundary.updated_at, boundary.memory_id),
            )
            has_more = bool(list(probe_query.limit(1).stream()))
        else:
            has_more = False

        if visible_memory_ids or not has_more:
            break
        if last_consumed_snapshot is None:
            break
        boundary = _canonical_graph_cursor_boundary_from_snapshot(last_consumed_snapshot)
        query_boundary = (boundary.updated_at, boundary.memory_id)
        pending_snapshots = []
        pending_window_has_more = False

    # Refuse to return a page assembled across two canonical revisions. The
    # second head read is bounded and makes the signed cursor's revision fence
    # meaningful even when writes race this request.
    ending_revision = _read_canonical_graph_revision(uid, db_client=client)
    if ending_revision != revision:
        raise CanonicalGraphReadUnavailable('canonical_revision_changed_during_read')

    next_cursor: Optional[str] = None
    if has_more:
        if last_consumed_snapshot is None:
            raise CanonicalGraphReadUnavailable('missing_cursor_boundary')
        boundary = _canonical_graph_cursor_boundary_from_snapshot(last_consumed_snapshot)
        next_cursor = _canonical_graph_encode_cursor(
            uid=uid,
            revision=revision,
            updated_at=boundary.updated_at,
            memory_id=boundary.memory_id,
            secret=secret,
        )

    merged = kg_db.merge_knowledge_graph_records(
        {'nodes': [], 'edges': []},
        accepted_assertions,
    )
    return CanonicalKnowledgeGraphPage(
        nodes=merged['nodes'],
        edges=merged['edges'],
        has_more=has_more,
        next_cursor=next_cursor,
        catalog_nodes=catalog_nodes,
    )


def get_canonical_knowledge_graph(
    uid: str,
    *,
    db_client: Any = None,
    limit: int = DEFAULT_CANONICAL_GRAPH_PAGE_LIMIT,
    cursor: Optional[str] = None,
) -> CanonicalKnowledgeGraphPage:
    """Return one bounded, revision-fenced page of the canonical memory graph."""
    if isinstance(limit, bool) or limit < 1 or limit > MAX_CANONICAL_GRAPH_PAGE_LIMIT:
        raise ValueError(f'canonical graph limit must be between 1 and {MAX_CANONICAL_GRAPH_PAGE_LIMIT}')
    if cursor is not None and not cursor.strip():
        raise CanonicalGraphCursorError('malformed_cursor')

    for attempt in range(CANONICAL_GRAPH_REVISION_READ_RETRIES):
        try:
            return _read_canonical_graph_page_once(
                uid,
                db_client=db_client,
                limit=limit,
                cursor=cursor,
            )
        except CanonicalGraphReadUnavailable as exc:
            if str(exc) == 'canonical_revision_changed_during_read' and attempt == 0:
                continue
            raise

    raise CanonicalGraphReadUnavailable('canonical_revision_changed_during_read')
