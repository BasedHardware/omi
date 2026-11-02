"""Pure metadata window state and ordering for the legacy memory list."""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List


class MemoryListIndexState:
    """Dual metadata prefixes owned by one synchronous read operation.

    Retain snapshots (including Firestore's implicit name tiebreaker) so outer
    compatibility/category expansions seek beyond prior work. Never share this
    state across requests, users, clients, or retries; it contains no content.
    """

    def __init__(self, uid: str) -> None:
        self.uid = uid
        self.client: Any = None
        self.windows: Dict[str, List[Any]] = {}
        self.exhausted: set[str] = set()


def memory_passes_list_visibility(memory: Dict[str, Any], *, include_invalidated: bool) -> bool:
    """Return whether a historical memory row should appear in list/read results.

    Product rule: exclude user-rejected rows (``user_review is False``) and, unless
    ``include_invalidated``, exclude superseded/retracted rows (``invalid_at`` set).

    This cannot be expressed as a Firestore ``where`` without changing results for
    legacy documents: inequality / ``not-in`` / ``!=`` exclude docs missing the
    field, while ``== None`` only matches an explicit null — not a missing field.
    Missing ``user_review`` and missing ``invalid_at`` both mean "still visible"
    (see #4498). Closest safe query: omit those predicates and filter here.
    """
    return memory.get('user_review') is not False and (include_invalidated or memory.get('invalid_at') is None)


def _memory_list_sort_key(memory: Dict[str, Any]) -> tuple[float, str]:
    value = memory.get('updated_at') or memory.get('created_at')
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            value = None
    if not isinstance(value, datetime):
        timestamp = float('-inf')
    else:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        timestamp = value.timestamp()
    return (-timestamp, str(memory.get('id') or ''))


def merge_memory_list_index_docs(
    candidate_docs: List[Any],
    *,
    include_invalidated: bool,
    typed_doc: Callable[[Any], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for doc in candidate_docs:
        payload = typed_doc(doc)
        doc_id = getattr(doc, 'id', None) or payload.get('id')
        if not isinstance(doc_id, str) or not doc_id:
            continue
        payload.setdefault('id', doc_id)
        by_id.setdefault(doc_id, payload)
    return sorted(
        (
            memory
            for memory in by_id.values()
            if memory_passes_list_visibility(memory, include_invalidated=include_invalidated)
        ),
        key=_memory_list_sort_key,
    )
