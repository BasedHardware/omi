"""Episode overlay storage: ``users/{uid}/episodes`` plus ``users/{uid}/episode_links``.

An episode document never holds transcript: it lists conversation ids and the
compact running state. Everything derived from speech (topic, bullets, people,
open questions, provisional items, moment headings) is sealed with the user's
key in one ``content`` field; timing, status and ids stay queryable.

``episode_links/current`` points at the open episode and
``episode_links/{conversation_id}`` maps a conversation to its episode, so
every read is a document get: no collection query and no composite index.
The account-deletion purge removes the whole ``users/{uid}`` subtree.

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

from database._client import get_firestore_client, run_transactional
from utils.encryption import decrypt, encrypt

CURRENT = 'current'
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


def get_episode_for_conversation(
    uid: str, conversation_id: str, *, firestore_client: Any = None
) -> Optional[dict[str, Any]]:
    if not conversation_id or conversation_id == CURRENT:
        return None
    client = _client(firestore_client)
    episode_id = _link_target(client, uid, conversation_id)
    return get_episode(uid, episode_id, firestore_client=client) if episode_id else None


def _closed_fields(reason: str, closed_at: datetime) -> dict[str, Any]:
    return {'status': 'closed', 'close_reason': reason, 'closed_at': closed_at}


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
) -> dict[str, Any]:
    pointer = _links(client, uid).document(CURRENT)
    current_id = _link_target(client, uid, CURRENT, transaction)
    current_ref = _episodes(client, uid).document(current_id) if current_id else None
    current_raw = None
    if current_ref is not None:
        snapshot = current_ref.get(transaction=transaction)
        current_raw = snapshot.to_dict() if snapshot.exists else None
    if current_id != expected_episode_id:
        raise EpisodeConflict('current_episode_changed')
    if expected_episode_id is not None:
        if not current_raw or current_raw.get('state_version') != expected_version:
            raise EpisodeConflict('state_version_changed')
    now = datetime.now(timezone.utc)
    links = [cid for cid in dict.fromkeys(link_conversation_ids) if cid and cid != CURRENT][:_LINK_BATCH_LIMIT]
    if new_episode is not None:
        if current_ref is not None and current_raw and current_raw.get('status') == 'live':
            transaction.update(current_ref, _closed_fields(close_reason or 'gap', closed_at or now))
        episode_id = str(new_episode['id'])
        stored = seal(uid, {**new_episode, 'state_version': 1})
        transaction.set(_episodes(client, uid).document(episode_id), stored)
        transaction.set(pointer, {'episode_id': episode_id, 'updated_at': now})
        result = {**new_episode, 'state_version': 1}
    else:
        if current_ref is None or current_raw is None:
            raise EpisodeConflict('no_open_episode')
        merged = {**(unseal(uid, current_raw) or {}), **updates}
        merged['state_version'] = int(current_raw.get('state_version') or 0) + 1
        transaction.set(current_ref, seal(uid, merged))
        episode_id = current_id
        result = merged
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
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Either update the open episode (CAS) or close it and open ``new_episode``. Returns the stored state."""
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
) -> Optional[dict[str, Any]]:
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    current_id = _link_target(client, uid, CURRENT, transaction)
    if not raw or raw.get('status') != 'live':
        return None
    merged = {**(unseal(uid, raw) or {}), **extra, **_closed_fields(reason, closed_at)}
    merged['state_version'] = int(raw.get('state_version') or 0) + 1
    transaction.set(ref, seal(uid, merged))
    if current_id == episode_id:
        transaction.set(_links(client, uid).document(CURRENT), {'episode_id': None, 'updated_at': closed_at})
    return merged


def close_episode(
    uid: str,
    episode_id: str,
    reason: str,
    *,
    closed_at: Optional[datetime] = None,
    extra: Optional[Mapping[str, Any]] = None,
    firestore_client: Any = None,
) -> Optional[dict[str, Any]]:
    """Close a live episode once. Returns the closed state, or None when it was not live."""
    client = _client(firestore_client)
    return run_transactional(
        client, _close, client, uid, episode_id, reason, closed_at or datetime.now(timezone.utc), dict(extra or {})
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
) -> dict[str, Any]:
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    if not raw or raw.get('state_version') != expected_version:
        raise EpisodeConflict('state_version_changed')
    merged = {**(unseal(uid, raw) or {}), **updates}
    merged['state_version'] = expected_version + 1
    transaction.set(ref, seal(uid, merged))
    now = datetime.now(timezone.utc)
    for conversation_id in [cid for cid in dict.fromkeys(link_conversation_ids) if cid and cid != CURRENT]:
        transaction.set(_links(client, uid).document(conversation_id), {'episode_id': episode_id, 'updated_at': now})
    return merged


def update_episode(
    uid: str,
    episode_id: str,
    *,
    expected_version: int,
    updates: Mapping[str, Any],
    link_conversation_ids: Sequence[str] = (),
    firestore_client: Any = None,
) -> dict[str, Any]:
    """CAS update of any episode (open or closed). Raises ``EpisodeConflict`` on a lost race."""
    client = _client(firestore_client)
    return run_transactional(
        client, _update, client, uid, episode_id, expected_version, dict(updates), list(link_conversation_ids)
    )
