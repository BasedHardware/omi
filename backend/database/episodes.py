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
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from google.cloud import firestore
from config.recorded_time import recorded_episodes_enabled
from config.episodes import MAX_EPISODE_SECONDS, episode_hard_cap_across_conversations_enabled
from utils.conversations.recorded_time import conversation_span, sync_recorded_end
from utils.conversations.fragment_visibility import is_relevance_discarded

from database import episode_receipts, episode_timeline
from database._client import get_firestore_client, run_transactional
from database.conversations import decode_transcript_segments_verified
from utils.encryption import decrypt, encrypt

CURRENT = 'current'
LAST_CLOSED = 'last_closed'
CONTENT_FIELDS = ('title', 'bullets', 'people', 'open_questions', 'provisional_items', 'moments')
MEMBERSHIP_BATCH_LIMIT = 50


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
    visited = set()
    while episode_id not in visited and len(visited) < 128:
        visited.add(episode_id)
        snapshot = _episodes(client, uid).document(episode_id).get()
        raw = snapshot.to_dict() if snapshot.exists else None
        if not raw:
            return None
        redirect = raw.get('recorded_merged_into')
        if not redirect:
            return unseal(uid, raw)
        episode_id = str(redirect)
    raise EpisodeConflict('recorded_redirect_cycle')


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
    hidden = set(raw.get('discarded_conversation_ids') or []) | set(updates.get('discarded_conversation_ids') or [])
    duplicates = set(merged.get('duplicate_conversation_ids') or [])
    activity = dict(raw.get('member_activity') or {})
    if not activity and isinstance(raw.get('last_activity_at'), datetime) and raw.get('primary_conversation_id'):
        activity[raw['primary_conversation_id']] = raw['last_activity_at']
    for cid, at in (updates.get('member_activity') or {}).items():
        if isinstance(at, datetime):
            activity[cid] = max(activity.get(cid, at), at)
    if activity or hidden:
        activity = {cid: at for cid, at in activity.items() if cid not in hidden | duplicates}
        merged['member_activity'] = activity
        merged['discarded_conversation_ids'] = sorted(hidden)
        merged['last_activity_at'] = max(activity.values(), default=merged['started_at'])
    else:
        before, after = raw.get('last_activity_at'), updates.get('last_activity_at')
        if isinstance(before, datetime) and isinstance(after, datetime):
            merged['last_activity_at'] = max(before, after)
    if isinstance(merged.get('last_activity_at'), datetime):
        merged['last_activity_at'] = _bounded_activity(
            {**merged, **{k: raw[k] for k in ('status', 'close_reason', 'last_activity_at') if k in raw}},
            merged['last_activity_at'],
        )
    excluded = hidden | set(merged.get('duplicate_conversation_ids') or [])
    for field in ('moments', 'provisional_items'):
        merged[field] = [item for item in merged.get(field) or [] if item.get('conversation_id') not in excluded]
    if hidden - set(raw.get('discarded_conversation_ids') or []):
        merged.update(title='', bullets=[], people=[], open_questions=[], summary_needs_regeneration=True)
    return merged


def _member_links(before, after, requested):
    added = set(after.get('conversation_ids') or []) - set((before or {}).get('conversation_ids') or [])
    links = [cid for cid in dict.fromkeys([*requested, *sorted(added)]) if cid and cid not in {CURRENT, LAST_CLOSED}]
    if len(links) > MEMBERSHIP_BATCH_LIMIT:
        raise EpisodeConflict('link_batch_exhausted')
    return links


def retained_bounds_changed(raw, merged):
    """Notes-only CAS updates reuse the bounds already repaired by the discard CAS."""
    before = set(raw.get('discarded_conversation_ids') or [])
    after = set(merged.get('discarded_conversation_ids') or [])
    return before != after or bool(
        after and set(raw.get('conversation_ids') or []) != set(merged.get('conversation_ids') or [])
    )


def retained_bounds(transaction, client, uid, raw, merged):
    """Re-read recorded evidence in the discard CAS, including legacy members.

    The timeline fence serializes this shrink with live activity and attachment.
    Missing live stubs retain their known clocks; missing data is not a discard.
    """
    hidden = set(merged.get('discarded_conversation_ids') or [])
    duplicates = set(merged.get('duplicate_conversation_ids') or [])
    starts, activity = {}, {}
    for cid in merged.get('conversation_ids') or []:
        if cid in hidden | duplicates:
            continue
        member = (
            client.collection('users')
            .document(uid)
            .collection('conversations')
            .document(cid)
            .get(transaction=transaction)
            .to_dict()
        )
        if member and (is_relevance_discarded(member) or member.get('deleted') or member.get('sync_merged_into')):
            hidden.add(cid)
            continue
        evidence = dict(member) if member else None
        if evidence and not all(isinstance(evidence.get(key), datetime) for key in ('recorded_start', 'recorded_end')):
            segments = evidence.get('transcript_segments')
            if segments is not None and not isinstance(segments, list):
                evidence['transcript_segments'] = decode_transcript_segments_verified(
                    uid, segments, bool(evidence.get('transcript_segments_compressed'))
                )
            # Legacy completion is a processing clock. Only decoded speech,
            # recording receipts or the persisted member clocks prove its end.
            # Preserve the recording authority's legacy pure-WAL receipt first.
            receipt_end = sync_recorded_end(evidence, None)
            if receipt_end is not None:
                evidence['sync_recorded_end_at'] = receipt_end
            evidence['finished_at'] = None
        span = conversation_span(evidence) if evidence else None
        known = (merged.get('member_activity') or {}).get(cid)
        fact = (raw.get('recorded_members') or {}).get(cid) or {}
        fallback_start = raw['started_at'] if cid in (raw.get('conversation_ids') or []) else known
        start = span.recorded_start if span else fact.get('start', fallback_start)
        end = span.recorded_end if span else fact.get('end', known)
        if isinstance(end, datetime):
            starts[cid] = start
            activity[cid] = max(end, known) if isinstance(known, datetime) else end
    merged['discarded_conversation_ids'] = sorted(hidden)
    if starts:
        merged['started_at'] = min(starts.values())
        # Apply the cap from the retained start, while keeping explicit closes
        # and the caller's next-episode fence authoritative.
        activity = {cid: _bounded_activity(merged, at) for cid, at in activity.items()}
        merged['last_activity_at'] = max(merged['started_at'], max(activity.values()))
        if merged.get('status') == 'closed':
            merged['recorded_end'] = merged['last_activity_at']
    else:
        merged['last_activity_at'] = merged['started_at']
        if merged.get('status') == 'closed':
            merged['recorded_end'] = merged['started_at']
    merged['member_activity'] = activity
    for field in ('moments', 'provisional_items'):
        merged[field] = [
            item for item in merged.get(field) or [] if item.get('conversation_id') not in hidden | duplicates
        ]
    if hidden - set(raw.get('discarded_conversation_ids') or []):
        merged.update(title='', bullets=[], people=[], open_questions=[], summary_needs_regeneration=True)
    return merged


def _check_membership(transaction, client, uid, episode_id, conversation_ids):
    """Check ownership in the same read phase as the link write, on every writer."""
    for cid in dict.fromkeys(conversation_ids):
        if not cid or cid in {CURRENT, LAST_CLOSED}:
            continue
        owner_id = _link_target(client, uid, cid, transaction)
        if owner_id and owner_id != episode_id:
            owner = _episodes(client, uid).document(owner_id).get(transaction=transaction).to_dict() or {}
            # A provisional boundary may detach first; an extant member cannot move.
            if cid in (owner.get('conversation_ids') or []):
                raise EpisodeConflict('conversation_already_owned')


def _bounded_activity(episode, at):
    start = episode.get('started_at')
    if episode_hard_cap_across_conversations_enabled() and isinstance(start, datetime):
        at = min(at, start + timedelta(seconds=MAX_EPISODE_SECONDS))
    if episode.get('status') == 'closed' and episode.get('close_reason') not in {'gap', 'idle'}:
        end = episode_timeline.recorded_end(episode)
        if isinstance(end, datetime):
            at = min(at, end)
    return at


@firestore.transactional
def _record_activity(
    transaction: Any, client: Any, uid: str, episode_id: str, conversation_id: str, at: datetime
) -> Optional[datetime]:
    if recorded_episodes_enabled():
        _links(client, uid).document('recorded_timeline').get(transaction=transaction)
    ref = _episodes(client, uid).document(episode_id)
    raw = ref.get(transaction=transaction).to_dict() or {}
    if (
        raw.get('status') != 'live'
        or conversation_id not in (raw.get('conversation_ids') or [])
        or conversation_id in (raw.get('duplicate_conversation_ids') or [])
    ):
        return None
    conversation = (
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .document(conversation_id)
        .get(transaction=transaction)
        .to_dict()
        or {}
    )
    if is_relevance_discarded(conversation) or any(conversation.get(key) for key in ('deleted', 'sync_merged_into')):
        return None
    last = raw.get('last_activity_at')
    member_at = _bounded_activity(raw, at)
    activity = max(last, member_at) if isinstance(last, datetime) else member_at
    members = dict(raw.get('member_activity') or {})
    prior_member = members.get(conversation_id)
    members[conversation_id] = max(prior_member, member_at) if isinstance(prior_member, datetime) else member_at
    if activity != last or members != raw.get('member_activity'):
        if recorded_episodes_enabled() and activity != last:
            fence = episode_timeline.check_window(transaction, client, uid, {**raw, 'last_activity_at': activity})
            if fence:
                transaction.set(fence[0], {'version': fence[1]})
        # This clock must not invalidate the notes state_version.
        transaction.update(ref, {'last_activity_at': activity, 'member_activity': members})
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


def read_memberships(transaction, client, uid, conversation_ids, *, admit_conversation_id=None):
    ids = [cid for cid in dict.fromkeys(conversation_ids) if cid and cid not in {CURRENT, LAST_CLOSED}]
    if len(ids) > MEMBERSHIP_BATCH_LIMIT:
        raise EpisodeConflict('membership_batch_exhausted')
    root = client.collection('users').document(uid)
    members = {}
    for cid in ids:
        snapshot = root.collection('conversations').document(cid).get(transaction=transaction)
        row = snapshot.to_dict() or {}
        if cid == admit_conversation_id and (
            is_relevance_discarded(row) or row.get('deleted') or row.get('sync_merged_into')
        ):
            raise EpisodeConflict('conversation_hidden')
        members[cid] = (
            snapshot.exists,
            _links(client, uid).document(cid).get(transaction=transaction).to_dict() or {},
        )
    return members


def write_memberships(transaction, client, uid, episode_id, members, arrival_at):
    """The reverse field and overlay link commit with the same membership CAS.

    Missing live stubs are not fabricated: their create transaction adopts the
    already-written link. Captures crossing a cap keep their starting owner; the
    storage guard rejects another extant owner before these writes.
    """
    for cid, (exists, previous) in members.items():
        ids = list(
            dict.fromkeys(
                [
                    *(previous.get('episode_ids') or []),
                    *([previous['episode_id']] if previous.get('episode_id') else []),
                    episode_id,
                ]
            )
        )
        transaction.set(
            _links(client, uid).document(cid), {'episode_id': episode_id, 'episode_ids': ids, 'updated_at': arrival_at}
        )
        if exists:
            transaction.update(
                client.collection('users').document(uid).collection('conversations').document(cid),
                {'episode_id': episode_id},
            )


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
    timeline_ref = _links(client, uid).document('recorded_timeline')
    timeline_enabled = recorded_episodes_enabled()
    timeline_row = (timeline_ref.get(transaction=transaction).to_dict() or {}) if timeline_enabled else {}
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
    if new_episode is None and (current_ref is None or current_raw is None):
        raise EpisodeConflict('no_open_episode')
    target = (
        _merge_state({}, new_episode)
        if new_episode is not None
        else _merge_state(unseal(uid, current_raw) or {}, updates)
    )
    if new_episode is None and retained_bounds_changed(current_raw, target):
        target = retained_bounds(transaction, client, uid, current_raw, target)
    links = _member_links(None if new_episode is not None else current_raw, target, link_conversation_ids)
    _check_membership(transaction, client, uid, target['id'], [*links, *(target.get('conversation_ids') or [])])
    members = read_memberships(transaction, client, uid, links)
    if recorded_episodes_enabled():
        episode_timeline.check_window(transaction, client, uid, target)
    if new_episode is not None:
        if current_ref is not None and current_raw and current_raw.get('status') == 'live':
            transaction.update(current_ref, _closed_fields(close_reason or 'gap', closed_at or now))
            transaction.set(_links(client, uid).document(LAST_CLOSED), {'episode_id': current_id, 'updated_at': now})
        episode_id = str(new_episode['id'])
        stored = seal(uid, {**target, 'state_version': 1})
        transaction.set(_episodes(client, uid).document(episode_id), stored)
        transaction.set(pointer, {'episode_id': episode_id, 'updated_at': now})
        result = {**target, 'state_version': 1}
    else:
        if current_ref is None or current_raw is None:
            raise EpisodeConflict('no_open_episode')
        merged = target
        _drop_legacy_receipts(merged, segment_receipts)
        merged['state_version'] = int(current_raw.get('state_version') or 0) + 1
        transaction.set(current_ref, seal(uid, merged))
        episode_id = current_id
        result = merged
    _write_receipts(transaction, client, uid, segment_receipts, receipts_raw, now)
    if timeline_enabled:
        transaction.set(timeline_ref, {'version': int(timeline_row.get('version') or 0) + 1})
    write_memberships(transaction, client, uid, episode_id, members, now)
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
        transient=True,
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
    if recorded_episodes_enabled():
        _links(client, uid).document('recorded_timeline').get(transaction=transaction)
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
    links = _member_links(raw, merged, link_conversation_ids)
    _check_membership(transaction, client, uid, episode_id, [*links, *(merged.get('conversation_ids') or [])])
    members = read_memberships(transaction, client, uid, links)
    if recorded_episodes_enabled():
        fence = episode_timeline.check_window(transaction, client, uid, merged)
        if fence:
            transaction.set(fence[0], {'version': fence[1]})
    transaction.set(ref, seal(uid, merged))
    transaction.set(_links(client, uid).document(CURRENT), {'episode_id': episode_id, 'updated_at': now})
    # The recap must not advertise a live episode as the last closed one.
    transaction.set(_links(client, uid).document(LAST_CLOSED), {'episode_id': None, 'updated_at': now})
    write_memberships(transaction, client, uid, episode_id, members, now)
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
    if recorded_episodes_enabled():
        _links(client, uid).document('recorded_timeline').get(transaction=transaction)
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    current_id = _link_target(client, uid, CURRENT, transaction)
    if not raw or raw.get('status') != 'live':
        return None
    if reason == 'idle' and expected_activity_at is not None and raw.get('last_activity_at') != expected_activity_at:
        return None  # Speech won the race with a lazy reader's stale idle decision.
    merged = {**(unseal(uid, raw) or {}), **extra, **_closed_fields(reason, closed_at)}
    # Finalize arrival is bookkeeping. Recorded ownership ends at retained member evidence.
    ends = []
    hidden = set(raw.get('discarded_conversation_ids') or []) | set(raw.get('duplicate_conversation_ids') or [])
    for cid in raw.get('conversation_ids') or []:
        member = (
            client.collection('users')
            .document(uid)
            .collection('conversations')
            .document(cid)
            .get(transaction=transaction)
            .to_dict()
            or {}
        )
        if (
            cid in hidden
            or is_relevance_discarded(member)
            or any(member.get(k) for k in ('deleted', 'sync_merged_into'))
        ):
            continue
        span = conversation_span(member)
        end = span.recorded_end if span else (raw.get('member_activity') or {}).get(cid)
        if isinstance(end, datetime):
            ends.append(end)
    end = max(ends, default=raw.get('last_activity_at') or raw['started_at'])
    end = max(raw['started_at'], _bounded_activity(raw, end))
    if recorded_episodes_enabled():
        rows = episode_timeline.recorded_candidates(
            uid, raw['started_at'], end, firestore_client=client, transaction=transaction
        )
        following = [r['started_at'] for r in rows if r['id'] != episode_id and r['started_at'] > raw['started_at']]
        if following:
            end = min(end, min(following))
        merged['recorded_end'] = end
        fence = episode_timeline.check_window(transaction, client, uid, merged, rows=rows)
        if fence:
            transaction.set(fence[0], {'version': fence[1]})
    else:
        merged['recorded_end'] = end
    merged['last_activity_at'] = end
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
    if recorded_episodes_enabled():
        _links(client, uid).document('recorded_timeline').get(transaction=transaction)
    ref = _episodes(client, uid).document(episode_id)
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() if snapshot.exists else None
    receipts_raw = _read_receipts(transaction, client, uid, segment_receipts)
    if not raw or raw.get('state_version') != expected_version:
        raise EpisodeConflict('state_version_changed')
    merged = _merge_state(unseal(uid, raw) or {}, updates)
    if retained_bounds_changed(raw, merged):
        merged = retained_bounds(transaction, client, uid, raw, merged)
    _drop_legacy_receipts(merged, segment_receipts)
    merged['state_version'] = expected_version + 1
    links = _member_links(raw, merged, link_conversation_ids)
    _check_membership(transaction, client, uid, episode_id, [*links, *(merged.get('conversation_ids') or [])])
    members = read_memberships(transaction, client, uid, links)
    if recorded_episodes_enabled():
        fence = episode_timeline.check_window(transaction, client, uid, merged)
        if fence:
            transaction.set(fence[0], {'version': fence[1]})
    transaction.set(ref, seal(uid, merged))
    now = datetime.now(timezone.utc)
    _write_receipts(transaction, client, uid, segment_receipts, receipts_raw, now)
    write_memberships(transaction, client, uid, episode_id, members, now)
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
        transient=True,
    )
