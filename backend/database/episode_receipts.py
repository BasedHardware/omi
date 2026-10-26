"""Per-conversation receipts of episode-consumed unplaced segments.

An unplaced segment (``audio_alignment=unplaced``, sentinel ``-1`` offsets)
has no ordering cursor the notes pipeline could advance, so its id is kept
after the episode consumes it: a retry, a later repaired placement and the
conversation's finalization tail must never feed the same speech into the
running notes twice (``utils/episodes/service.py``).

The receipts belong to the conversation, not to one episode: a conversation
spans episode boundaries (an idle close, the hard cap) and its finalization
tail still dedupes against everything consumed live. They must also never
bound the episode document's size, so they live under
``users/{uid}/episode_segment_receipts/{conversation_id}``:

- the base document holds the most recent ``SHARD_SIZE`` ids, oldest first;
- older ids roll into immutable archive documents ``s/{index}`` holding at
  most ``SHARD_SIZE`` ids each, so no document grows with the conversation.

A live moment dedupes against the base document alone (its segments are
recent: the tracker buffers at most ``MAX_BUFFERED_SEGMENTS``); the
finalization tail, which replays the whole stored transcript, also reads the
archives. Receipt writes join the episode compare-and-swap transaction
(``database.episodes``), so a receipt exists exactly when the state that
consumed the segment was stored. The account-deletion purge removes the whole
``users/{uid}`` subtree with them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from database._client import get_firestore_client

# Ids per receipt document. ~2,000 uuids is ~80 KB: far under the 1 MiB
# document limit, cheap to read per moment, and 50k consumed segments shard
# into ~25 immutable archives.
SHARD_SIZE = 2_000

_BASE_COLLECTION = 'episode_segment_receipts'
_ARCHIVE_COLLECTION = 's'


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _receipts(client: Any, uid: str) -> Any:
    return client.collection('users').document(uid).collection(_BASE_COLLECTION)


def base_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return _receipts(client, uid).document(conversation_id)


def archive_ref(client: Any, uid: str, conversation_id: str, index: int) -> Any:
    return base_ref(client, uid, conversation_id).collection(_ARCHIVE_COLLECTION).document(str(index))


def get_consumed_ids(
    uid: str,
    conversation_id: str,
    *,
    all_shards: bool,
    firestore_client: Any = None,
) -> tuple[set[str], bool]:
    """The consumed ids for one conversation, and whether receipts exist yet.

    ``all_shards`` (the finalization tail) also reads the immutable archives;
    otherwise only the base document's recent window is read.
    """
    if not conversation_id:
        return set(), False
    client = _client(firestore_client)
    raw = base_ref(client, uid, conversation_id).get().to_dict() or {}
    ids = {str(value) for value in raw.get('ids') or []}
    shards = int(raw.get('shards') or 0)
    exists = bool(raw)
    if all_shards:
        for index in range(shards):
            archive = archive_ref(client, uid, conversation_id, index).get().to_dict() or {}
            ids |= {str(value) for value in archive.get('ids') or []}
    return ids, exists


def plan_write(
    existing: Optional[Mapping[str, Any]], add_ids: Iterable[str], *, now: Optional[datetime] = None
) -> tuple[dict[str, Any], list[tuple[int, list[str]]]]:
    """The base-document payload and archive writes that record ``add_ids``.

    Pure: the caller applies both inside the episode transaction. ``ids`` is
    ordered oldest-first: the stored order is preserved and new ids append in
    the order given, so only the oldest ids spill into the next archive
    indices and the base document always keeps the most recent ``SHARD_SIZE``
    window. The live tracker re-presents buffered segments (at most
    ``MAX_BUFFERED_SEGMENTS``), all far newer than that window.
    """
    at = now or datetime.now(timezone.utc)
    merged: list[str] = [str(value) for value in (existing or {}).get('ids') or []]
    seen = set(merged)
    for value in add_ids:
        text = str(value)
        if text not in seen:
            seen.add(text)
            merged.append(text)
    shards = int((existing or {}).get('shards') or 0)
    archives: list[tuple[int, list[str]]] = []
    while len(merged) > SHARD_SIZE:
        spill = len(merged) - SHARD_SIZE
        archives.append((shards, merged[:spill]))
        shards += 1
        merged = merged[spill:]
    payload: dict[str, Any] = {'ids': merged, 'shards': shards, 'updated_at': at}
    return payload, archives
