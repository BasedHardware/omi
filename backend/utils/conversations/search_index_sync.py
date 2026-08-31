"""Keep the Typesense `conversations` collection in step with the store (ADR-0064).

`utils/conversations/search.py` only ever READS that collection — the single reference to it in the whole
repo is a `search()`. Upstream fills it from a Firestore -> Typesense pipeline that does not exist in this
codebase, so on-prem the index was permanently empty and `POST /v1/conversations/search` (the app's search
bar AND its date-range browse, plus the desktop equivalent and the MCP tool) had nothing to find.

This module is the missing writer. It is deliberately **additive**: it reads through the neutral store
port and writes to Typesense, and touches no upstream module, so a merge cannot conflict with it.

Why a full reconcile rather than an incremental sweep: the store's `updated_at` is document METADATA
(`database/conversations.py:359` is explicit that it is never an application field), so it cannot be
filtered or ordered on through the port. There is no queryable "changed since" key, so a watermark on
`created_at` would index new conversations and silently miss every edit — a title regenerated, a
conversation discarded. A bounded full pass is the honest shape: it costs one read per conversation per
run and it is *correct*, including deletions.

Two rules the bound obeys, because getting them wrong is worse than being slow:
  * the cap is REPORTED, never silent (AGENTS.md): a truncated run says so in its summary and its log.
  * a truncated run does NOT prune. Pruning is "delete everything the scan did not see", so pruning a
    partial scan would delete live conversations from the index.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# The collection name search.py reads. Not configurable: it is one half of a contract with that module.
CONVERSATIONS_COLLECTION = 'conversations'

# Field names carry literal dots. Typesense treats a dotted name as one flat field when nested fields are
# off (verified against the pinned image: a document with the flat key "structured.title" indexes and
# matches `query_by=structured.title`), which is exactly the shape search.py asks for — so no nested-object
# mode and no reshaping of the query side.
CONVERSATIONS_SCHEMA: Dict[str, Any] = {
    'name': CONVERSATIONS_COLLECTION,
    'fields': [
        {'name': 'userId', 'type': 'string', 'facet': True},
        # query_by in search.py
        {'name': 'structured.overview', 'type': 'string', 'optional': True},
        {'name': 'structured.title', 'type': 'string', 'optional': True},
        # filter_by / sort_by in search.py
        {'name': 'created_at', 'type': 'int64'},
        {'name': 'discarded', 'type': 'bool', 'facet': True},
        # Read off each hit: search.py converts all three with int() and SKIPS a hit that fails, so they
        # are required rather than optional — a conversation missing one is not indexed at all.
        {'name': 'started_at', 'type': 'int64'},
        {'name': 'finished_at', 'type': 'int64'},
        # Read off the hit to drop locked conversations before hydration. NOT a filter field by design
        # upstream, so it is stored, not filtered.
        {'name': 'is_locked', 'type': 'bool', 'optional': True},
    ],
    'default_sorting_field': 'created_at',
}

DEFAULT_PAGE_SIZE = 200
# Bound one run. 20k conversations is well past a self-host corpus; the point is that a runaway store
# cannot make one tick unbounded.
DEFAULT_MAX_DOCUMENTS = 20_000
MAX_DOCUMENTS_ENV = 'CONVERSATION_SEARCH_INDEX_MAX_DOCUMENTS'


@dataclass
class ReconcileReport:
    scanned: int = 0
    indexed: int = 0
    skipped_incomplete: int = 0
    pruned: int = 0
    truncated: bool = False
    prune_skipped_reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def as_log(self) -> str:
        return (
            f'scanned={self.scanned} indexed={self.indexed} skipped_incomplete={self.skipped_incomplete} '
            f'pruned={self.pruned} truncated={self.truncated} '
            f'prune_skipped={self.prune_skipped_reason or "-"} errors={len(self.errors)}'
        )


def _epoch(value: Any) -> Optional[int]:
    """Seconds since the epoch, or None when the value cannot be one.

    search.py does ``int(doc['created_at'])`` and skips the hit on failure, so anything it would reject is
    rejected here instead — a hit that cannot be rendered is worse than an absent one.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    to_timestamp = getattr(value, 'timestamp', None)
    if callable(to_timestamp):
        try:
            # Same reason as the branch above: `to_timestamp` was found by getattr on an unknown value,
            # so its result is unknown until it is checked. int() of the wrong thing raises anyway, but
            # the check says which shape is expected instead of relying on the bare except.
            seconds = to_timestamp()
        except Exception:
            return None
        return int(seconds) if isinstance(seconds, (int, float)) else None
    return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def build_conversation_search_document(
    uid: str, conversation_id: str, data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """One Typesense document, or None when the conversation cannot be represented.

    Mirrors what search.py reads, nothing more: the router re-reads the full conversation from the store
    by id after the search, so the index only has to make it FINDABLE.
    """
    if not uid or not conversation_id:
        return None
    created_at = _epoch(data.get('created_at'))
    started_at = _epoch(data.get('started_at'))
    finished_at = _epoch(data.get('finished_at'))
    if created_at is None or started_at is None or finished_at is None:
        return None
    structured = data.get('structured')
    structured = structured if isinstance(structured, dict) else {}
    return {
        'id': conversation_id,
        'userId': uid,
        'structured.overview': _text(structured.get('overview')),
        'structured.title': _text(structured.get('title')),
        'created_at': created_at,
        'discarded': bool(data.get('discarded', False)),
        'started_at': started_at,
        'finished_at': finished_at,
        'is_locked': bool(data.get('is_locked', False)),
    }


def uid_and_id_from_path(path: str) -> Tuple[Optional[str], Optional[str]]:
    """``users/{uid}/conversations/{id}`` -> (uid, id). Anything else -> (None, None).

    The collection-group read returns full logical paths (ADR-0025), and the owner is only in the path —
    a conversation document is not guaranteed to carry its own uid.
    """
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == CONVERSATIONS_COLLECTION:
        return parts[1], parts[3]
    return None, None


def ensure_collection(client: Any) -> None:
    """Create the collection if absent; if present, refuse to proceed when it lacks a field search.py needs.

    A collection made by a different writer (upstream's pipeline, an older version of this module) that
    misses `structured.overview` would make every query fail with Typesense's "Could not find a filter
    field" rather than return nothing — so say which field is missing instead.
    """
    try:
        existing = client.collections[CONVERSATIONS_COLLECTION].retrieve()
    except Exception:
        client.collections.create(CONVERSATIONS_SCHEMA)
        logger.info('conversation_search_index: created collection %s', CONVERSATIONS_COLLECTION)
        return
    actual = {str(f.get('name')) for f in (existing.get('fields') or []) if f.get('name')}
    # EVERY declared name, not just the non-optional ones: `optional` describes the VALUE, and a
    # collection whose schema lacks `structured.overview` makes search.py's query_by fail outright.
    required = {str(f['name']) for f in CONVERSATIONS_SCHEMA['fields']}
    missing = sorted(required - actual)
    if missing:
        raise RuntimeError(
            f'Typesense collection {CONVERSATIONS_COLLECTION!r} is incompatible with conversation search; '
            f'missing fields: {missing}'
        )


def _indexed_ids(client: Any) -> List[str]:
    """Every id currently in the collection, for the prune step."""
    raw = client.collections[CONVERSATIONS_COLLECTION].documents.export()
    if not raw:
        return []
    ids: List[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        doc_id = doc.get('id')
        if isinstance(doc_id, str) and doc_id:
            ids.append(doc_id)
    return ids


def _max_documents() -> int:
    raw = (os.getenv(MAX_DOCUMENTS_ENV) or '').strip()
    if not raw:
        return DEFAULT_MAX_DOCUMENTS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_DOCUMENTS


def _pages(store: Any, page_size: int, max_documents: int) -> Iterable[Sequence[Any]]:
    """Walk the whole `conversations` collection group in bounded pages, keyed on document name.

    Document-name keyset (ADR-0027) rather than a field cursor: it is a stable total order over the group,
    which is what a full pass needs, and it does not depend on any timestamp being present or unique.
    """
    cursor: Optional[str] = None
    emitted = 0
    while emitted < max_documents:
        limit = min(page_size, max_documents - emitted)
        page = store.query_group(CONVERSATIONS_COLLECTION, limit=limit, start_after=cursor)
        if not page:
            return
        yield page
        emitted += len(page)
        cursor = page[-1].path
        if len(page) < limit:
            return


def reconcile_conversation_search_index(
    *,
    store: Any = None,
    client: Any = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_documents: Optional[int] = None,
) -> ReconcileReport:
    """Bring the Typesense `conversations` collection in line with the store. Returns a report."""
    from utils.conversations.search import typesense_configured

    report = ReconcileReport()
    if not typesense_configured():
        raise RuntimeError(
            'TYPESENSE_HOST/TYPESENSE_API_KEY are not set, so there is nothing to index into. '
            'Enable the search profile or disable this job.'
        )
    if store is None:
        from database.store.factory import get_document_store

        store = get_document_store()
    if client is None:
        from utils.conversations.search import client as typesense_client

        client = typesense_client

    ensure_collection(client)
    cap = _max_documents() if max_documents is None else max_documents
    seen: set[str] = set()
    documents = client.collections[CONVERSATIONS_COLLECTION].documents

    for page in _pages(store, page_size, cap):
        for record in page:
            report.scanned += 1
            uid, conversation_id = uid_and_id_from_path(getattr(record, 'path', '') or '')
            data = record.data if isinstance(getattr(record, 'data', None), dict) else None
            if uid is None or conversation_id is None or data is None:
                report.skipped_incomplete += 1
                continue
            document = build_conversation_search_document(uid, conversation_id, data)
            if document is None:
                report.skipped_incomplete += 1
                continue
            try:
                documents.upsert(document)
            except Exception as exc:  # one bad document must not abort the pass
                report.errors.append(f'{conversation_id}: {exc}')
                continue
            seen.add(conversation_id)
            report.indexed += 1

    report.truncated = report.scanned >= cap
    if report.truncated:
        # No silent caps (AGENTS.md): say what was left out, and do NOT prune — "delete what the scan did
        # not see" over a partial scan would delete live conversations from the index.
        report.prune_skipped_reason = f'scan truncated at {cap} documents'
        logger.warning(
            'conversation_search_index: scan truncated at %s documents; prune skipped. Raise %s.',
            cap,
            MAX_DOCUMENTS_ENV,
        )
    else:
        for stale_id in sorted(set(_indexed_ids(client)) - seen):
            try:
                documents[stale_id].delete()
                report.pruned += 1
            except Exception as exc:
                report.errors.append(f'prune {stale_id}: {exc}')

    logger.info('conversation_search_index: %s', report.as_log())
    return report
