import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlsplit
from uuid import UUID

import typesense

from utils.share_links import accepted_share_hosts, share_base_url

logger = logging.getLogger(__name__)


class ConversationSearchUnavailableError(Exception):
    """Raised when Typesense is unreachable or times out (transient upstream failure)."""


_EXACT_CONVERSATION_PATH_PREFIX = '/conversations/'


def _canonical_conversation_uuid(value: str) -> Optional[str]:
    """Return a normalized UUID only when ``value`` is a complete canonical UUID."""
    if len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    if str(parsed) != value.lower():
        return None
    return str(parsed)


def parse_exact_conversation_reference(query: str) -> Optional[str]:
    """Extract a canonical conversation UUID from an ID or Omi share URL.

    Exact references intentionally accept only the two values Omi presents to users: a UUID or an
    HTTPS URL on the configured share host (default ``h.omi.me``) with the exact
    ``/conversations/<uuid>`` path. Anything else remains a natural-language query so partial IDs
    and lookalike URLs cannot turn search into document probing.
    """
    value = query.strip() if query else ''
    if exact_id := _canonical_conversation_uuid(value):
        return exact_id

    try:
        parsed = urlsplit(value)
    except ValueError:
        return None

    host = (parsed.hostname or '').lower()
    try:
        configured = urlsplit(share_base_url())
        port = parsed.port
        configured_port = configured.port
    except ValueError:
        return None
    configured_host = (configured.hostname or '').lower()
    if host == configured_host:
        expected_port = configured_port
        expected_path_prefix = f'{configured.path.rstrip("/")}{_EXACT_CONVERSATION_PATH_PREFIX}'
    elif host == 'h.omi.me':
        expected_port = None
        expected_path_prefix = _EXACT_CONVERSATION_PATH_PREFIX
    else:
        return None
    if (
        parsed.scheme.lower() != 'https'
        or host not in accepted_share_hosts()
        or parsed.username is not None
        or parsed.password is not None
        or port != expected_port
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(expected_path_prefix)
    ):
        return None

    return _canonical_conversation_uuid(parsed.path[len(expected_path_prefix) :])


def clamp_conversation_search_pagination(page: Optional[int], per_page: Optional[int]) -> tuple[int, int]:
    """Clamp the unbounded search request pagination at the shared search boundary."""
    return max(1, page or 1), max(1, min(per_page or 10, 250))


def conversation_matches_date_range(
    conversation: Dict[str, Any], start_date: Optional[int] = None, end_date: Optional[int] = None
) -> bool:
    """Apply the same ``created_at`` timestamp filters to an exact hydrated conversation."""
    if start_date is None and end_date is None:
        return True

    created_at = conversation.get('created_at')
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        timestamp = created_at.timestamp()
    elif isinstance(created_at, (int, float)):
        timestamp = float(created_at)
    elif isinstance(created_at, str):
        try:
            parsed = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamp = parsed.timestamp()
        except ValueError:
            return False
    else:
        return False

    return (start_date is None or timestamp >= start_date) and (end_date is None or timestamp <= end_date)


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


def conversation_matches_speaker(conversation: Dict[str, Any], speaker_id: Optional[str]) -> bool:
    """Whether a hydrated Firestore conversation has at least one segment from the requested speaker.

    speaker_id == 'user' means the account owner (segment.is_user), any other value is a person id
    (segment.person_id). Falsy speaker_id means "no speaker filter" and matches everything.
    """
    if not speaker_id:
        return True
    segments = conversation.get('transcript_segments') or []
    if not isinstance(segments, list):
        return False
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if speaker_id == 'user':
            if segment.get('is_user'):
                return True
        elif segment.get('person_id') == speaker_id:
            return True
    return False


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
    page, per_page = clamp_conversation_search_pagination(page, per_page)
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

        # No speaker clause is added to filter_by on purpose. transcript_segments is not part of the
        # Typesense `conversations` schema (the Firestore -> Typesense sync only carries
        # userId/created_at/discarded/started_at/finished_at/structured.*), so
        # `transcript_segments.is_user` / `.person_id` made Typesense reject the whole query with
        # 400 "Could not find a filter field named ... in the schema" and 500 every speaker-filtered
        # search. The filter is applied by conversation_matches_speaker after the router hydrates the
        # Firestore documents, which do carry transcript_segments; here speaker_id only widens the
        # browse (see has_filter_only_browse above).

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
