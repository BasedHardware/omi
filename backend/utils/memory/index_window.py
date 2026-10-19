"""One page of historical index work per ordering, owned by a cursor request."""

from typing import Any

from database import memories
from database._client import get_firestore_client
from utils.memory.index_window_cursor import decode_cursor, encode_cursor, query_scope


class MemoryIndexWindowLimit(Exception):
    """A resumable raw window ended before the visible page filled."""


def read_index_window_slots(
    history: Any, uid: str, kind: str, limit: int, cursor: str, budget: Any, device_scope_request: Any
):
    database = history._db_client if history._db_client is not None else get_firestore_client()
    collection = database.collection('users').document(uid).collection('memories')
    field = 'updated_at' if kind == 'updated' else 'created_at'
    docs = memories._stream_memory_list_index_window(
        collection, field, limit, uid=uid, cursor=cursor, full_documents=True, budget=budget
    )
    payloads = []
    positions = []
    for doc in docs:
        raw = memories._typed_doc(doc)
        raw['id'] = doc.id
        payloads.append(raw)
        positions.append((raw[field], doc.id))
    slots = history._adapt_scan_payloads(
        uid, payloads, positions, device_scope_request=device_scope_request, drop_updated_at_present=kind == 'created'
    )
    return slots, len(docs) < limit


def position_cursor(uid: str, kind: str, position: tuple) -> str:
    field = 'updated_at' if kind == 'updated' else 'created_at'
    return encode_cursor(position[0], position[1], query_scope({'uid': uid, 'order': field}))


def validate_window_cursors(state: Any, uid: str) -> None:
    for keyset, field in ((state.historical_updated_scan, 'updated_at'), (state.historical_created_scan, 'created_at')):
        if keyset is not None and keyset.index_window_cursor is not None:
            decode_cursor(keyset.index_window_cursor, query_scope({'uid': uid, 'order': field}))
