import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

import typesense

logger = logging.getLogger(__name__)


class ConversationSearchUnavailableError(Exception):
    """Raised when Typesense is unreachable or times out (transient upstream failure)."""


def _is_typesense_transient_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    transient_markers = (
        'timed out',
        'timeout',
        'connection refused',
        'connection reset',
        'temporarily unavailable',
        'service unavailable',
    )
    if any(marker in message for marker in transient_markers):
        return True
    module = type(exc).__module__
    name = type(exc).__name__
    return module.endswith('exceptions') and name in {
        'Timeout',
        'ConnectTimeout',
        'ReadTimeout',
        'ConnectionError',
        'ServiceUnavailable',
    }


# Client creation must remain lazy: retrieval helpers import this module in
# offline tests and unrelated request paths where Typesense is intentionally
# unconfigured. Tests can still inject a fake through the legacy ``client``
# seam without causing a real client to be constructed.
_typesense_client: Any | None = None


def _get_typesense_client() -> Any:
    global _typesense_client
    if _typesense_client is None:
        _typesense_client = typesense.Client(
            {
                'nodes': [
                    {
                        'host': os.getenv('TYPESENSE_HOST'),
                        'port': os.getenv('TYPESENSE_HOST_PORT'),
                        'protocol': os.getenv('TYPESENSE_PROTOCOL', 'https'),
                    }
                ],
                'api_key': os.getenv('TYPESENSE_API_KEY'),
                'connection_timeout_seconds': 2,
            }
        )
    return _typesense_client


def _lazy_getattr(target: Any, name: str) -> Any:
    # Dunders stay unresolved so introspection (copy, pickle, mock) cannot
    # construct a real client and defeat the laziness this shim exists for.
    if name.startswith('__') and name.endswith('__'):
        raise AttributeError(name)
    return getattr(target(), name)


class _LazyCollections:
    def __getitem__(self, name: str) -> Any:
        return _get_typesense_client().collections[name]

    def __getattr__(self, name: str) -> Any:
        return _lazy_getattr(lambda: _get_typesense_client().collections, name)


class _LazyTypesenseClient:
    def __init__(self) -> None:
        self.collections: Any = _LazyCollections()

    def __getattr__(self, name: str) -> Any:
        return _lazy_getattr(_get_typesense_client, name)


client: Any = _LazyTypesenseClient()


def _utc_iso(ts: int) -> str:
    """Convert a stored unix timestamp to a timezone-aware UTC ISO 8601 string (with a +00:00 offset).

    Typesense stores created_at/started_at/finished_at as unix timestamps. Rendering them with
    ``datetime.utcfromtimestamp(ts).isoformat()`` produced a NAIVE string with no offset, so the chat
    model and clients could read a UTC time as local time and show conversation times hours off
    (issue #4643). Anchoring to UTC keeps the offset explicit so consumers interpret it correctly.
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def search_conversations(
    uid: str,
    query: str,
    page: int = 1,
    per_page: int = 10,
    include_discarded: bool = True,
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
    speaker_id: Optional[str] = None,
) -> Dict[str, Any]:
    # page/per_page arrive from SearchRequest where both are Optional and unbounded, so None, 0,
    # negative, or a huge value would otherwise TypeError here (len(...) >= per_page / page + 1) or trip
    # Typesense RequestMalformed and 500 the request. Clamp at this shared boundary, mirroring the
    # clamps in routers/memories.py and routers/mcp.py. Typesense caps a single page at 250 hits.
    page = max(1, page or 1)
    per_page = max(1, min(per_page or 10, 250))
    try:
        stripped_query = query.strip() if query else ''
        has_filter_only_browse = bool(speaker_id) or start_date is not None or end_date is not None
        if not stripped_query and not has_filter_only_browse:
            return {
                'items': [],
                'total_pages': page,
                'current_page': page,
                'per_page': per_page,
            }

        filter_by = f'userId:={uid}'
        if not include_discarded:
            filter_by = filter_by + ' && discarded:=false'

        # Add date range filters if provided
        if start_date is not None:
            filter_by = filter_by + f' && created_at:>={start_date}'
        if end_date is not None:
            filter_by = filter_by + f' && created_at:<={end_date}'

        if speaker_id == 'user':
            filter_by = filter_by + ' && transcript_segments.is_user:=true'
        elif speaker_id:
            filter_by = filter_by + f' && transcript_segments.person_id:={speaker_id}'

        search_parameters = {
            'q': stripped_query or '*',
            'query_by': 'structured.overview, structured.title',
            'filter_by': filter_by,
            'sort_by': 'created_at:desc',
            'per_page': per_page,
            'page': page,
        }

        results: Dict[str, Any] = cast(
            Dict[str, Any],
            client.collections['conversations'].documents.search(search_parameters),
        )  # type: ignore[reportUnknownMemberType]  # typesense client untyped
        memories: List[Dict[str, Any]] = []
        for item in results.get('hits', []):
            doc: Dict[str, Any] = item.get('document', {})
            # Exclude locked conversations entirely to prevent inference leaks
            if doc.get('is_locked', False):
                continue
            try:
                # Convert all three into locals first, then assign, so a hit that fails partway is
                # never left half-converted.
                created_at = _utc_iso(int(doc['created_at']))
                started_at = _utc_iso(int(doc['started_at']))
                finished_at = _utc_iso(int(doc['finished_at']))
            except (KeyError, TypeError, ValueError, OverflowError, OSError) as e:
                # One malformed/legacy indexed doc (missing, null, or out-of-range timestamp) must not
                # 500 the whole search page; skip just this hit (mirrors the per-record tolerance in
                # routers/memories.py get_memories).
                logger.warning("search_conversations skipping malformed hit uid=%s id=%s: %s", uid, doc.get('id'), e)
                continue
            doc['created_at'] = created_at
            doc['started_at'] = started_at
            doc['finished_at'] = finished_at
            memories.append(doc)
        # Derive total_pages only from visible (unlocked) items to prevent inference leaks.
        # is_locked is not a Typesense filter field, so exact global count is unavailable.
        has_more = len(memories) >= per_page
        return {
            'items': memories,
            'total_pages': page + 1 if has_more else page,
            'current_page': page,
            'per_page': per_page,
        }
    except Exception as e:
        if _is_typesense_transient_error(e):
            logger.warning(
                "search_conversations upstream timeout/unavailable uid=%s query_len=%s: %s",
                uid,
                len(query or ''),
                e,
            )
            raise ConversationSearchUnavailableError('Typesense search temporarily unavailable') from e
        raise Exception(f"Failed to search conversations: {str(e)}") from e


def keyword_search_conversation_ids(
    uid: str,
    query: str,
    limit: int = 5,
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
) -> List[str]:
    """Typesense keyword search returning only conversation ids, for hybrid (keyword + vector) retrieval.

    Fail-open: any search error returns [] so callers can fall back to vector-only results.
    """
    if not query.strip():
        return []

    try:
        results = search_conversations(
            uid=uid,
            query=query,
            per_page=limit,
            include_discarded=False,
            start_date=start_date,
            end_date=end_date,
        )
        items: List[Dict[str, Any]] = results.get('items', [])
        return [str(item['id']) for item in items if item.get('id')]
    except Exception as e:
        logger.warning("keyword_search_conversation_ids failed for uid=%s, falling back to vector-only: %s", uid, e)
        return []


def merge_conversation_search_ids(keyword_ids: List[str], vector_ids: List[str]) -> List[str]:
    """Merge keyword and vector search results, keyword hits first (exact text matches), deduplicated."""
    return list(keyword_ids) + [cid for cid in vector_ids if cid not in keyword_ids]
