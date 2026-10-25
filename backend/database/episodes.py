"""Episode overlay storage: ``users/{uid}/episodes`` plus ``users/{uid}/episode_links``.

An episode document never holds transcript: it lists conversation ids and the
compact running state. Everything derived from speech (topic, bullets, people,
open questions, provisional items, moment headings) is sealed with the user's
key in one ``content`` field; timing, status and ids stay queryable.

``episode_links/current`` points at the open episode and
``episode_links/{conversation_id}`` maps a conversation to its episode, so
every read is a document get: no collection query and no composite index.
The account-deletion purge removes the whole ``users/{uid}`` subtree.

Consumed unplaced-segment ids live in their own sharded per-conversation
documents (``database.episode_receipts``), never in the episode document, and
are written inside the episode transactions below so a receipt exists exactly
when the state that consumed the segment was stored.

Writes are compare-and-swap on ``state_version`` inside a transaction. The
model call that produces a state happens outside the transaction; a lost race
returns ``EpisodeConflict`` and the caller decides whether to retry.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from google.cloud import firestore

from database import episode_receipts
from database._client import get_firestore_client, run_transactional
from utils.encryption import decrypt, encrypt

CURRENT = 'current'
LAST_CLOSED = 'last_closed'
CONTENT_FIELDS = ('title', 'bullets', 'people', 'open_questions', 'provisional_items', 'moments')
_LINK_BATCH_LIMIT = 50


class EpisodeConflict(RuntimeError):
    """The open episode or its state version changed since the caller read it."""


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _episodes(client: Any, uid: str) -> Any:
    return client.collection('users').document(uid).collection('episodes')


def _links(client: Any, uid: str) -> Any:
    return client.collection('users').document(uid).collection('episode_links')


def new_episode_id() -> str:
    return uuid.uuid4().hex


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    raise TypeError(type(value).__name__)


def seal(uid: str, episode: Mapping[str, Any]) -> dict[str, Any]:
    """Move speech-derived fields into the encrypted ``content`` blob."""
    stored = {key: value for key, value in episode.items() if key not in CONTENT_FIELDS}
    content = {key: episode.get(key) for key in CONTENT_FIELDS if key in episode}
    stored['content'] = encrypt(json.dumps(content, ensure_ascii=False, default=_json_default), uid)
    return stored


def unseal(uid: str, raw: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    episode = {key: value for key, value in raw.items() if key != 'content'}
    blob = raw.get('content')
    content: dict[str, Any] = {}
    if isinstance(blob, str) and blob:
        content = json.loads(decrypt(blob, uid))
    for key in CONTENT_FIELDS:
        episode[key] = content.get(key) if content.get(key) is not None else ('' if key == 'title' else [])
    return episode


def get_episode(uid: str, episode_id: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    client = _client(firestore_client)
    snapshot = _episodes(client, uid).document(episode_id).get()
    return unseal(uid, snapshot.to_dict()) if snapshot.exists else None


def _link_target(client: Any, uid: str, key: str, transaction: Any = None) -> Optional[str]:
    snapshot = _links(client, uid).document(key).get(transaction=transaction)
    data = snapshot.to_dict() if snapshot.exists else None
    value = (data or {}).get('episode_id')
    return value if isinstance(value, str) and value else None


def get_current_episode(uid: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    client = _client(firestore_client)
    episode_id = _link_target(client, uid, CURRENT)
    return get_episode(uid, episode_id, firestore_client=client) if episode_id else None


def get_last_closed_episode(uid: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    """A discoverable recap even if its conversation's finalizer has not completed."""
    client = _client(firestore_client)
    episode_id = _link_target(client, uid, LAST_CLOSED)
    return get_episode(uid, episode_id, firestore_client=client) if episode_id else None


def get_episode_for_conversation(
    uid: str, conversation_id: str, *, firestore_client: Any = None
) -> Optional[dict[str, Any]]:
    if not conversation_id or conversation_id in {CURRENT, LAST_CLOSED}:
        return None
    client = _client(firestore_client)
    episode_id = _link_target(client, uid, conversation_id)
    return get_episode(uid, episode_id, firestore_client=client) if episode_id else None


def _closed_fields(reason: str, closed_at: datetime) -> dict[str, Any]:
    return {'status': 'closed', 'close_reason': reason, 'closed_at': closed_at}


def _merge_state(raw: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    """A notes CAS must not overwrite speech retained while its model call ran."""
    merged = {**raw, **updates}
    before, after = raw.get('last_activity_at'), updates.get('last_activity_at')
    if isinstance(before, datetime) and isinstance(after, datetime):
        merged['last_activity_at'] = max(before, after)
    return merged


@firestore.transactional
def _record_activity(
    transaction: Any, client: Any, uid: str, episode_id: str, conversation_id: str, at: datetime
) -> Optional[datetime]:
    ref = _episodes(client, uid).document(episode_id)
    raw = ref.get(transaction=transaction).to_dict() or {}
    if raw.get('status') != 'live' or conversation_id not in (raw.get('conversation_ids') or []):
        return None
    last = raw.get('last_activity_at')
    activity = max(last, at) if isinstance(last, datetime) else at
    if activity != last:
        # This clock has its own transaction. It must not invalidate notes state_version.
        transaction.update(ref, {'last_activity_at': activity})
    return activity


def record_activity(
    uid: str, episode_id: str, conversation_id: str, at: datetime, *, firestore_client: Any = None
) -> Optional[datetime]:
    client = _client(firestore_client)
    return run_transactional(client, _record_activity, client, uid, episode_id, conversation_id, at)


def _receipt_conversations(segment_receipts: Optional[Mapping[str, Sequence[str]]]) -> list[str]:
    """The conversations whose receipts this transaction touches (link names are not conversations)."""
    return [cid for cid in dict.fromkeys(segment_receipts or {}) if cid and cid not in {CURRENT, LAST_CLOSED}]


def _read_receipts(
    transaction: Any, client: Any, uid: str, segment_receipts: Optional[Mapping[str, Sequence[str]]]
) -> dict[str, Optional[dict[str, Any]]]:
    """Transactional read of each conversation's receipt base document (read phase)."""
    if not segment_receipts:
        return {}
    return {
        conversation_id: episode_receipts.base_ref(client, uid, conversation_id).get(transaction=transaction).to_dict()
        for conversation_id in _receipt_conversations(segment_receipts)
    }


def _write_receipts(
    transaction: Any,
    client: Any,
    uid: str,
    segment_receipts: Optional[Mapping[str, Sequence[str]]],
    existing: Mapping[str, Optional[dict[str, Any]]],
    now: datetime,
) -> None:
    """Record consumed ids in the same transaction as the episode state (write phase)."""
    for conversation_id in _receipt_conversations(segment_receipts or {}):
        payload, archives = episode_receipts.plan_write(
            existing.get(conversation_id), (segment_receipts or {})[conversation_id], now=now
        )
        transaction.set(episode_receipts.base_ref(client, uid, conversation_id), payload)
        for index, ids in archives:
            transaction.set(episode_receipts.archive_ref(client, uid, conversation_id, index), {'ids': ids})


def _drop_legacy_receipts(merged: dict[str, Any], segment_receipts: Optional[Mapping[str, Sequence[str]]]) -> None:
    """Remove the pre-receipts in-document id lists this write migrated to their own documents."""
    legacy = merged.get('applied_segment_ids')
    if not segment_receipts or not isinstance(legacy, dict):
        return
    remaining = {cid: ids for cid, ids in legacy.items() if cid not in segment_receipts}
    if remaining:
        merged['applied_segment_ids'] = remaining
    else:
        merged.pop('applied_segment_ids', None)


@firestore.transactional
def _commit(
    transaction: Any,
    client: Any,
    uid: str,
    expected_episode_id: Optional[str],
    expected_version: Optional[int],
    close_reason: Optional[str],
    closed_at: Optional[datetime],
    new_episode: Optional[Mapping[str, Any]],
    updates: Mapping[str, Any],
    link_conversation_ids: Sequence[str],
    segment_receipts: Optional[Mapping[str, Sequence[str]]] = None,
) -> dict[str, Any]:
    pointer = _links(client, uid).document(CURRENT)
    current_id = _link_target(client, uid, CURRENT, transaction)
    current_ref = _episodes(client, uid).document(current_id) if current_id else None
    current_raw = None
    if current_ref is not None:
        snapshot = current_ref.get(transaction=transaction)
        current_raw = snapshot.to_dict() if snapshot.exists else None
    receipts_raw = _read_receipts(transaction, client, uid, segment_receipts)
    if current_id != expected_episode_id:
        raise EpisodeConflict('current_episode_changed')
    if expected_episode_id is not None:
        if not current_raw or current_raw.get('state_version') != expected_version:
            raise EpisodeConflict('state_version_changed')
    now = datetime.now(timezone.utc)
    links = [cid for cid in dict.fromkeys(link_conversation_ids) if cid and cid not in {CURRENT, LAST_CLOSED}][
        :_LINK_BATCH_LIMIT
    ]
    if new_episode is not None:
        if current_ref is not None and current_raw and current_raw.get('status') == 'live':
            transaction.update(current_ref, _closed_fields(close_reason or 'gap', closed_at or now))
            transaction.set(_links(client, uid).document(LAST_CLOSED), {'episode_id': current_id, 'updated_at': now})
        episode_id = str(new_episode['id'])
        stored = seal(uid, {**new_episode, 'state_version': 1})
        transaction.set(_episodes(client, uid).document(episode_id), stored)
        transaction.set(pointer, {'episode_id': episode_id, 'updated_at': now})
        result = {**new_episode, 'state_version': 1}
    else:
        if current_ref is None or current_raw is None:
            raise EpisodeConflict('no_open_episode')
        merged = _merge_state(unseal(uid, current_raw) or {}, updates)
        _drop_legacy_receipts(merged, segment_receipts)
        merged['state_version'] = int(current_raw.get('state_version') or 0) + 1
        transaction.set(current_ref, seal(uid, merged))
        episode_id = current_id
        result = merged
    _write_receipts(transaction, client, uid, segment_receipts, receipts_raw, now)
    for conversation_id in links:
        transaction.set(_links(client, uid).document(conversation_id), {'episode_id': episode_id, 'updated_at': now})
    return result


def commit_moment(
    uid: str,
    *,
    expected_episode_id: Optional[str],
    expected_version: Optional[int],
    new_episode: Optional[Mapping[str, Any]] = None,
    updates: Optional[Mapping[str, Any]] = None,
    close_reason: Optional[str] = None,
    closed_at: Optional[datetime] = None,
    link_conversation_ids: Sequence[str] = (),
    segment_receipts: Optional[Mapping[str, Sequence[str]]] = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Either update the open episode (CAS) or close it and open ``new_episode``. Returns the stored state.

    ``segment_receipts`` records consumed unplaced-segment ids per conversation in the
    same transaction, so a receipt exists exactly when the state that consumed it does.
    """
    client = _client(firestore_client)
    return run_transactional(
        client,
        _commit,
        client,
        uid,
        expected_episode_id,
        expected_version,
        close_reason,
        closed_at,
        new_episode,
        dict(updates or {}),
        list(link_conversation_ids),
        dict(segment_receipts or {}) or None,
    )


@firestore.transactional
def _reopen(
    transaction: Any,
    client: Any,
    uid: str,
    episode_id: str,
    expected_version: int,
    updates: Mapping[str, Any],
    link_conversation_ids: Sequence[str],
) -> Optional[dict[str, Any]]:
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    if not raw or raw.get('status') != 'closed':
        return None
    if int(raw.get('state_version') or 0) != expected_version:
        raise EpisodeConflict('state_version_changed')
    if _link_target(client, uid, CURRENT, transaction):
        return None  # A newer episode went live: the closed one stays closed.
    last_closed_id = _link_target(client, uid, LAST_CLOSED, transaction)
    if last_closed_id != episode_id:
        return None  # A newer episode opened and closed since the read: only the latest reopens.
    now = datetime.now(timezone.utc)
    merged = _merge_state(
        unseal(uid, raw) or {},
        {
            **updates,
            'status': 'live',
            'closed_at': None,
            'close_reason': None,
            'closing_conversation_id': None,
            'wrap_up_requested_at': None,
        },
    )
    merged['state_version'] = int(raw.get('state_version') or 0) + 1
    transaction.set(ref, seal(uid, merged))
    transaction.set(_links(client, uid).document(CURRENT), {'episode_id': episode_id, 'updated_at': now})
    # The recap must not advertise a live episode as the last closed one.
    transaction.set(_links(client, uid).document(LAST_CLOSED), {'episode_id': None, 'updated_at': now})
    for conversation_id in [
        cid for cid in dict.fromkeys(link_conversation_ids) if cid and cid not in {CURRENT, LAST_CLOSED}
    ]:
        transaction.set(_links(client, uid).document(conversation_id), {'episode_id': episode_id, 'updated_at': now})
    return merged


def reopen_episode(
    uid: str,
    episode_id: str,
    *,
    expected_version: int,
    updates: Optional[Mapping[str, Any]] = None,
    link_conversation_ids: Sequence[str] = (),
    firestore_client: Any = None,
) -> Optional[dict[str, Any]]:
    """Reopen a closed episode as the current one. Returns the live state, or None.

    None means the episode is no longer closed, its state version moved on
    (``EpisodeConflict`` is raised for that), or another episode is already
    current: the caller then attaches without reopening. Only the episode-join
    path for a late sync capture reopens; every other close stays final.
    """
    client = _client(firestore_client)
    return run_transactional(
        client,
        _reopen,
        client,
        uid,
        episode_id,
        expected_version,
        dict(updates or {}),
        list(link_conversation_ids),
    )


@firestore.transactional
def _close(
    transaction: Any,
    client: Any,
    uid: str,
    episode_id: str,
    reason: str,
    closed_at: datetime,
    extra: Mapping[str, Any],
    expected_activity_at: Optional[datetime],
) -> Optional[dict[str, Any]]:
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    current_id = _link_target(client, uid, CURRENT, transaction)
    if not raw or raw.get('status') != 'live':
        return None
    if reason == 'idle' and expected_activity_at is not None and raw.get('last_activity_at') != expected_activity_at:
        return None  # Speech won the race with a lazy reader's stale idle decision.
    merged = {**(unseal(uid, raw) or {}), **extra, **_closed_fields(reason, closed_at)}
    merged['state_version'] = int(raw.get('state_version') or 0) + 1
    transaction.set(ref, seal(uid, merged))
    if current_id == episode_id:
        transaction.set(_links(client, uid).document(CURRENT), {'episode_id': None, 'updated_at': closed_at})
        transaction.set(_links(client, uid).document(LAST_CLOSED), {'episode_id': episode_id, 'updated_at': closed_at})
    return merged


def close_episode(
    uid: str,
    episode_id: str,
    reason: str,
    *,
    closed_at: Optional[datetime] = None,
    extra: Optional[Mapping[str, Any]] = None,
    expected_activity_at: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Optional[dict[str, Any]]:
    """Close a live episode once. Returns the closed state, or None when it was not live."""
    client = _client(firestore_client)
    return run_transactional(
        client,
        _close,
        client,
        uid,
        episode_id,
        reason,
        closed_at or datetime.now(timezone.utc),
        dict(extra or {}),
        expected_activity_at,
    )


@firestore.transactional
def _update(
    transaction: Any,
    client: Any,
    uid: str,
    episode_id: str,
    expected_version: int,
    updates: Mapping[str, Any],
    link_conversation_ids: Sequence[str],
    segment_receipts: Optional[Mapping[str, Sequence[str]]] = None,
) -> dict[str, Any]:
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    receipts_raw = _read_receipts(transaction, client, uid, segment_receipts)
    if not raw or raw.get('state_version') != expected_version:
        raise EpisodeConflict('state_version_changed')
    merged = _merge_state(unseal(uid, raw) or {}, updates)
    _drop_legacy_receipts(merged, segment_receipts)
    merged['state_version'] = expected_version + 1
    transaction.set(ref, seal(uid, merged))
    now = datetime.now(timezone.utc)
    _write_receipts(transaction, client, uid, segment_receipts, receipts_raw, now)
    for conversation_id in [
        cid for cid in dict.fromkeys(link_conversation_ids) if cid and cid not in {CURRENT, LAST_CLOSED}
    ]:
        transaction.set(_links(client, uid).document(conversation_id), {'episode_id': episode_id, 'updated_at': now})
    return merged


def update_episode(
    uid: str,
    episode_id: str,
    *,
    expected_version: int,
    updates: Mapping[str, Any],
    link_conversation_ids: Sequence[str] = (),
    segment_receipts: Optional[Mapping[str, Sequence[str]]] = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """CAS update of any episode (open or closed). Raises ``EpisodeConflict`` on a lost race.

    ``segment_receipts`` records consumed unplaced-segment ids per conversation in the
    same transaction, so a receipt exists exactly when the state that consumed it does.
    """
    client = _client(firestore_client)
    return run_transactional(
        client,
        _update,
        client,
        uid,
        episode_id,
        expected_version,
        dict(updates),
        list(link_conversation_ids),
        dict(segment_receipts or {}) or None,
    )
