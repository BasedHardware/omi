"""Metadata-only recorded-time lookup and serialized historical attachment."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.episodes import MAX_EPISODE_SECONDS, CLOSE_GAP_SECONDS
from database._client import get_firestore_client, run_transactional
from database import episodes, episode_attach_memo, episode_batch_pending, transcript_pointer
from utils.conversations.episode_attach_key import content_key, memo_eligible
from config.episode_attach import content_gate_enabled, optimizations_enabled
from utils.conversations.recorded_time import conversation_span

PAGE_LIMIT = 128
# Optional F decisions need a complete small window; hitting this limit keeps the control join.
F_JOIN_CANDIDATE_LIMIT = 2
FIELDS = (
    'started_at',
    'recorded_end',
    'closed_at',
    'last_activity_at',
    'status',
    'close_reason',
    'state_version',
    'recorded_merged_into',
    'recorded_members',
    'discarded_conversation_ids',
)


def recorded_candidates(
    uid: str,
    started: datetime,
    finished: datetime,
    *,
    firestore_client: Any = None,
    transaction: Any = None,
    candidate_limit: int = PAGE_LIMIT,
) -> list[dict[str, Any]]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    # Single-field range: uses Firestore's automatic started_at index.
    query = (
        client.collection('users')
        .document(uid)
        .collection('episodes')
        .where(
            filter=FieldFilter('started_at', '>=', started - timedelta(seconds=MAX_EPISODE_SECONDS + CLOSE_GAP_SECONDS))
        )
        .where(filter=FieldFilter('started_at', '<=', finished + timedelta(seconds=CLOSE_GAP_SECONDS)))
        .order_by(
            'started_at',
            direction=firestore.Query.DESCENDING if candidate_limit != PAGE_LIMIT else firestore.Query.ASCENDING,
        )
        .select(FIELDS)
        .limit(candidate_limit)
    )
    rows = [dict(doc.to_dict(), id=doc.id) for doc in query.stream(transaction=transaction)]
    if len(rows) >= candidate_limit:
        raise episodes.EpisodeConflict('recorded_window_incomplete')
    return [row for row in rows if not row.get('recorded_merged_into')]


def recorded_end(episode):
    """Explicit closes own their recorded window; quiet padding is not speech."""
    if episode.get('status') == 'closed' and episode.get('close_reason') not in {'gap', 'idle'}:
        return episode.get('recorded_end') or episode.get('closed_at') or episode.get('last_activity_at')
    return episode.get('last_activity_at')


def check_window(transaction, client, uid, episode, *, rows=None, fence_row=None, candidate_limit=PAGE_LIMIT):
    """Serialize live writes with recorded attachment; reject overlapping windows."""
    if not optimizations_enabled():
        rows, fence_row = None, None
    lo, hi = episode.get('started_at'), recorded_end(episode)
    if not isinstance(lo, datetime) or not isinstance(hi, datetime):
        return
    fence = client.collection('users').document(uid).collection('episode_links').document('recorded_timeline')
    if fence_row is None:
        fence_row = fence.get(transaction=transaction).to_dict() or {}
    if rows is None:
        rows = recorded_candidates(
            uid, lo, hi, firestore_client=client, transaction=transaction, candidate_limit=candidate_limit
        )
    for row in rows:
        a, b = row.get('started_at'), recorded_end(row)
        if row['id'] != episode['id'] and isinstance(a, datetime) and isinstance(b, datetime):
            if lo == a or (lo < b and a < hi) or (lo == hi and a <= lo < b):
                raise episodes.EpisodeConflict('recorded_window_overlap')
    return fence, int(fence_row.get('version') or 0) + 1


def _attach_recorded_window(
    uid: str,
    conversation_id: str,
    source: str | None,
    started: datetime,
    finished: datetime,
    *,
    choose: Callable,
    new_episode: dict[str, Any],
    firestore_client: Any = None,
    expected_episode_id: str | None = None,
    transaction: Any = None,
    candidates: Callable | None = None,
    fence_row: Any = None,
    pending_at: datetime | None = None,
    deadline_floor: datetime | None = None,
    detach_from: str | None = None,
) -> dict[str, Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()

    def attach(transaction):
        root = client.collection('users').document(uid)
        links = root.collection('episode_links')
        fence = links.document('recorded_timeline')
        revision = fence_row if fence_row is not None else (fence.get(transaction=transaction).to_dict() or {})
        member = links.document(conversation_id)
        member_row = member.get(transaction=transaction).to_dict() or {}
        members = episodes.read_memberships(
            transaction, client, uid, [conversation_id], admit_conversation_id=conversation_id
        )
        pending_patch = episode_batch_pending.read_patch(
            transaction, client, uid, conversation_id, pending_at, deadline_floor=deadline_floor
        )
        rows = (candidates or recorded_candidates)(
            uid, started, finished, firestore_client=client, transaction=transaction
        )
        selected = choose(rows, started, started)
        # A conversation belongs to the episode it started in, even past a cap.
        owner_id = member_row.get('episode_id')
        if detach_from and owner_id == detach_from:
            owner_id = None
        existing = None
        if owner_id:
            snapshot = root.collection('episodes').document(owner_id).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
            if existing is None:
                raise episodes.EpisodeConflict('recorded_owner_missing')
            if expected_episode_id is not None and existing.get('id') != expected_episode_id:
                raise episodes.EpisodeConflict('recorded_owner_changed')
            if started >= existing['started_at'] + timedelta(seconds=MAX_EPISODE_SECONDS):
                return {**existing, '_window_end': finished}
        if existing is None and selected:
            snapshot = root.collection('episodes').document(selected['id']).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
        if expected_episode_id is not None and (existing or {}).get('id') != expected_episode_id:
            raise episodes.EpisodeConflict('recorded_owner_changed')
        lo = min(existing['started_at'], started) if existing else started
        window_end = min(finished, lo + timedelta(seconds=MAX_EPISODE_SECONDS))
        if existing and existing.get('status') != 'live' and existing.get('close_reason') not in {'gap', 'idle'}:
            boundary_end = recorded_end(existing)
            if not isinstance(boundary_end, datetime):
                raise episodes.EpisodeConflict('recorded_owner_missing_end')
            window_end = min(window_end, boundary_end)
        if existing is None or existing.get('status') == 'live' or existing.get('close_reason') in {'gap', 'idle'}:
            # A late prefix that would overflow an existing capped occasion
            # ends at that occasion; it must not create an overlapping 4h row.
            following = [
                row['started_at'] for row in rows if row['id'] != (existing or {}).get('id') and row['started_at'] > lo
            ]
            if following:
                window_end = min(window_end, min(following))
        if window_end < started or (window_end == started and finished > started):
            raise episodes.EpisodeConflict('recorded_window_no_progress')
        if existing:
            result = dict(existing)
            result['conversation_ids'] = list(
                dict.fromkeys([*(existing.get('conversation_ids') or []), conversation_id])
            )
            result['recovered_conversation_ids'] = list(
                dict.fromkeys([*(existing.get('recovered_conversation_ids') or []), conversation_id])
            )
            result['sources'] = list(dict.fromkeys([*(existing.get('sources') or []), *([source] if source else [])]))
            if (
                source
                and existing.get('sources')
                and source not in (existing.get('sources') or [])
                and existing.get('conversation_ids')
                and started < existing['last_activity_at']
                and finished > existing['started_at']
            ):
                # Preserve the parallel-content decision before membership and
                # sources make the finalizer look like a same-member continue.
                result['parallel_content_spans'] = {
                    **(existing.get('parallel_content_spans') or {}),
                    conversation_id: {'start': existing['started_at'], 'end': existing['last_activity_at']},
                }
            result['started_at'] = min(existing['started_at'], started)
            result['last_activity_at'] = max(existing['last_activity_at'], window_end)
            result['member_activity'] = {**(existing.get('member_activity') or {}), conversation_id: window_end}
            if existing.get('recorded_members') is not None:
                facts = dict(existing['recorded_members'])
                prior = facts.get(conversation_id) or {}
                facts[conversation_id] = {
                    'start': min(prior.get('start') or started, started),
                    'end': max(prior.get('end') or finished, finished),
                    'source': source or prior.get('source'),
                }
                result['recorded_members'] = facts
            if result.get('status') != 'live':
                if result.get('close_reason') in {'gap', 'idle'}:
                    result['closed_at'] = result['last_activity_at']
                if window_end < finished and result.get('close_reason') in {'gap', 'idle'}:
                    result['close_reason'] = (
                        'hard_cap' if window_end == lo + timedelta(seconds=MAX_EPISODE_SECONDS) else 'boundary'
                    )
                result['recorded_end'] = result['last_activity_at']
            result['state_version'] = int(existing.get('state_version') or 0) + 1
        else:
            result = dict(new_episode)
            result.update(
                id=str(uuid5(NAMESPACE_URL, f'recorded-episode:{uid}:{conversation_id}:{started.isoformat()}')),
                status='closed',
                close_reason=(
                    ('hard_cap' if window_end == lo + timedelta(seconds=MAX_EPISODE_SECONDS) else 'boundary')
                    if window_end < finished
                    else 'gap'
                ),
                closed_at=window_end,
                started_at=started,
                last_activity_at=window_end,
                state_version=1,
                conversation_ids=[conversation_id],
                member_activity={conversation_id: window_end},
                recovered_conversation_ids=[conversation_id],
            )
        if existing and episodes.retained_bounds_changed(existing, result):
            result = episodes.retained_bounds(transaction, client, uid, existing, result)
        check_window(transaction, client, uid, result, rows=rows, fence_row=revision)
        transaction.set(root.collection('episodes').document(result['id']), episodes.seal(uid, result))
        episodes.write_memberships(transaction, client, uid, result['id'], members, datetime.now(timezone.utc))
        if pending_patch:
            transaction.update(root.collection('conversations').document(conversation_id), pending_patch)
        transaction.set(fence, {'version': int(revision.get('version') or 0) + 1})
        # Never modify current/last_closed navigation pointers for late audio.
        return {**result, '_window_end': window_end}

    if transaction is not None:
        return attach(transaction)
    return run_transactional(client, firestore.transactional(attach), transient=True)


def attach_existing_recorded(
    uid, conversation_id, source, started, finished, *, episode_id, choose, firestore_client=None
):
    """Claim the occasion proved by relevance, or fail before any write.

    No new episode, repartition, notes generation or live navigation change.
    Membership and the conversation's reverse field share the timeline CAS.
    """
    return _attach_recorded_window(
        uid,
        conversation_id,
        source,
        started,
        finished,
        choose=choose,
        new_episode={},
        expected_episode_id=episode_id,
        firestore_client=firestore_client,
    )


def _detach_plan(transaction, client, uid, conversation_id, episode_id):
    """Read a movable provisional membership and return ``(ref, updated_owner)``.

    Reads only, so the caller can apply the write after its own read phase. The
    live path owns a live episode's membership, and the current pointer is never
    a provisional owner, so both are refused.
    """
    root = client.collection('users').document(uid)
    links = root.collection('episode_links')
    member = links.document(conversation_id).get(transaction=transaction).to_dict() or {}
    if member.get('episode_id') != episode_id:
        return None
    ref = root.collection('episodes').document(episode_id)
    owner = episodes.unseal(uid, ref.get(transaction=transaction).to_dict())
    if owner is None or conversation_id not in (owner.get('conversation_ids') or []):
        return None
    if owner.get('status') == 'live':
        return None
    current = links.document('current').get(transaction=transaction).to_dict() or {}
    if current.get('episode_id') == episode_id:
        return None
    row = root.collection('conversations').document(conversation_id).get(transaction=transaction).to_dict() or {}
    if (
        not row.get('episode_transcription_pending_at')
        or row.get('record_projection_revision')
        or row.get('transcript_segments')
    ):
        return None
    remaining = [cid for cid in owner.get('conversation_ids') or [] if cid != conversation_id]
    if not remaining:
        return None
    facts = {cid: fact for cid, fact in (owner.get('recorded_members') or {}).items() if cid != conversation_id}
    result = {
        **owner,
        'conversation_ids': remaining,
        'member_activity': {
            cid: at for cid, at in (owner.get('member_activity') or {}).items() if cid != conversation_id
        },
        'recorded_members': facts,
        'recovered_conversation_ids': [
            cid for cid in owner.get('recovered_conversation_ids') or [] if cid != conversation_id
        ],
        'discarded_conversation_ids': [
            cid for cid in owner.get('discarded_conversation_ids') or [] if cid != conversation_id
        ],
        'parallel_content_spans': {
            cid: at for cid, at in (owner.get('parallel_content_spans') or {}).items() if cid != conversation_id
        },
        'state_version': int(owner.get('state_version') or 0) + 1,
    }
    if facts:
        result['started_at'] = min(fact['start'] for fact in facts.values())
        result['last_activity_at'] = max(fact['end'] for fact in facts.values())
    if result.get('primary_conversation_id') == conversation_id:
        result['primary_conversation_id'] = remaining[0]
    return ref, result


def attach_recorded(
    uid: str,
    conversation_id: str,
    source: str | None,
    started: datetime,
    finished: datetime,
    *,
    choose: Callable,
    new_episode: dict[str, Any],
    firestore_client: Any = None,
    attach_row: Any = None,
    pending_at: datetime | None = None,
    deadline_floor: datetime | None = None,
    detach_from: str | None = None,
    admission: bool = False,
) -> dict[str, Any] | str:
    """Place a capture once. Its owner never changes when the capture spans a cap.

    The episode's recorded window stops at four hours or the next occasion;
    the next episode starts only with a different conversation.
    """
    if finished < started or (finished - started).total_seconds() > MAX_EPISODE_SECONDS * PAGE_LIMIT:
        raise episodes.EpisodeConflict('recorded_capture_window_exhausted')
    from database import episode_recorded_components

    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def attach(transaction):
        # Both attachment strategies share one read phase and one fence. Cache
        # only inside this callback: Firestore retries must issue fresh queries.
        fence = client.collection('users').document(uid).collection('episode_links').document('recorded_timeline')
        revision = fence.get(transaction=transaction).to_dict() or {}
        # Read the old provisional membership before any write. The write lands
        # after the attach, so a failed attach leaves the member where it was.
        detach = _detach_plan(transaction, client, uid, conversation_id, detach_from) if detach_from else None
        # Metadata-only close attachment has not recovered/finalized transcript
        # evidence. Do not stamp (or reset) its completed sync-attach memo.
        key = (
            content_key(attach_row)
            if pending_at is None and content_gate_enabled() and attach_row and memo_eligible(attach_row)
            else None
        )
        span = conversation_span(attach_row) if key else None
        if key and (
            span is None
            or (span.recorded_start, span.recorded_end) != (started, finished)
            or getattr(attach_row.get('source'), 'value', attach_row.get('source')) != source
        ):
            key = None
        if key:
            current = client.collection('users').document(uid).collection('conversations').document(conversation_id)
            if episode_attach_memo.current_key(uid, current.get(transaction=transaction).to_dict()) != key:
                key = None
        cached = []

        def candidates(uid, lo, hi, **kwargs):
            # Preserve the canonical expansion read sequence. Only the fallback
            # strategy reuses these rows after canonical attachment declines.
            rows = recorded_candidates(uid, lo, hi, **kwargs)
            if optimizations_enabled():
                cached.append((lo, hi, rows))
            return rows

        def reuse_candidates(uid, lo, hi, **kwargs):
            for a, b, rows in cached if optimizations_enabled() else []:
                if a <= lo and hi <= b:
                    return rows
            return candidates(uid, lo, hi, **kwargs)

        canonical = episode_recorded_components.attach(
            uid,
            conversation_id,
            source,
            started,
            finished,
            candidates=candidates,
            template=new_episode,
            choose=choose,
            firestore_client=client,
            page_limit=PAGE_LIMIT,
            transaction=transaction,
            fence_row=revision,
            pending_at=pending_at,
            deadline_floor=deadline_floor,
            detach_from=detach_from,
            admission=admission,
        )
        if isinstance(canonical, str):
            return canonical
        if canonical is not None:
            episode_attach_memo.stamp(transaction, client, uid, conversation_id, key, canonical['id'])
            if detach and canonical['id'] != detach_from:
                transaction.set(detach[0], episodes.seal(uid, detach[1]))
            return canonical
        result = _attach_recorded_window(
            uid,
            conversation_id,
            source,
            started,
            finished,
            choose=choose,
            new_episode=new_episode,
            firestore_client=client,
            transaction=transaction,
            candidates=reuse_candidates,
            fence_row=revision,
            pending_at=pending_at,
            deadline_floor=deadline_floor,
            detach_from=detach_from,
        )
        result.pop('_window_end')
        episode_attach_memo.stamp(transaction, client, uid, conversation_id, key, result['id'])
        if detach and result['id'] != detach_from:
            transaction.set(detach[0], episodes.seal(uid, detach[1]))
        return {**result, '_recorded_windows': [result]}

    return transcript_pointer.run_preloaded_transactional(client, attach, transient=True)


def detach_recorded(
    uid: str,
    conversation_id: str,
    *,
    episode_id: str,
    firestore_client: Any = None,
) -> bool:
    """Remove an admission-time provisional member from the episode it joined.

    Only the admission attach's provisional membership may be detached: the
    member must still be pending transcription with no projected transcript, and
    the episode must keep at least one other member. A transcribed member never
    moves, and an episode is never left empty. The recorded-timeline fence
    serializes this with every other membership writer, so a concurrent attach
    either wins the link first (and this returns False) or sees the removal.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def detach(transaction):
        root = client.collection('users').document(uid)
        links = root.collection('episode_links')
        fence = links.document('recorded_timeline')
        revision = fence.get(transaction=transaction).to_dict() or {}
        plan = _detach_plan(transaction, client, uid, conversation_id, episode_id)
        if plan is None:
            return False
        member = links.document(conversation_id).get(transaction=transaction).to_dict() or {}
        ref, result = plan
        transaction.set(ref, episodes.seal(uid, result))
        transaction.update(root.collection('conversations').document(conversation_id), {'episode_id': None})
        transaction.set(
            links.document(conversation_id),
            {
                'episode_id': None,
                'episode_ids': [eid for eid in member.get('episode_ids') or [] if eid != episode_id],
                'updated_at': datetime.now(timezone.utc),
            },
        )
        transaction.set(fence, {'version': int(revision.get('version') or 0) + 1})
        return True

    return run_transactional(client, detach, transient=True)


def member_episodes(uid: str, conversation_id: str, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    """Only the canonical owner; a capture crossing a cap never gains another membership."""
    owner = episodes.get_episode_for_conversation(uid, conversation_id, firestore_client=firestore_client)
    return [owner] if owner else []


def resume_recorded(uid, episode_id, at, *, expected_version, choose: Callable, firestore_client=None):
    """Only fresh live speech can resume a silence-closed recorded occasion.

    A sync intake never calls this. The current-pointer and timeline fences
    prevent a concurrent live open from being overwritten by the resume.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def resume(transaction):
        root = client.collection('users').document(uid)
        links = root.collection('episode_links')
        fence = links.document('recorded_timeline')
        fence_row = fence.get(transaction=transaction).to_dict() or {}
        current = links.document('current').get(transaction=transaction).to_dict() or {}
        ref = root.collection('episodes').document(episode_id)
        owner = episodes.unseal(uid, ref.get(transaction=transaction).to_dict())
        if (
            current.get('episode_id')
            or not owner
            or owner.get('status') != 'closed'
            or owner.get('close_reason') not in {'gap', 'idle'}
        ):
            return None
        if owner.get('state_version') != expected_version:
            raise episodes.EpisodeConflict('state_version_changed')
        if choose([owner], at, at) is None:
            return None
        last_closed = links.document('last_closed').get(transaction=transaction).to_dict() or {}
        result = {
            **owner,
            'status': 'live',
            'closed_at': None,
            'close_reason': None,
            'closing_conversation_id': None,
            'wrap_up_requested_at': None,
            'state_version': expected_version + 1,
        }
        transaction.set(ref, episodes.seal(uid, result))
        transaction.set(links.document('current'), {'episode_id': episode_id, 'updated_at': datetime.now(timezone.utc)})
        if last_closed.get('episode_id') == episode_id:
            transaction.set(links.document('last_closed'), {'episode_id': None})
        transaction.set(fence, {'version': int(fence_row.get('version') or 0) + 1})
        return result

    return run_transactional(client, resume, transient=True)


def between(uid: str, start: datetime, end: datetime, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    """Complete ordered time-index scan using the automatic started_at index.

    Paginate rather than silently dropping episodes after PAGE_LIMIT. Only the
    selected overlapping rows are decrypted by the service. No composite index.
    """
    if end < start:
        raise ValueError('episode window end precedes start')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection('episodes')
        .where(filter=FieldFilter('started_at', '>=', start - timedelta(seconds=MAX_EPISODE_SECONDS)))
        .where(filter=FieldFilter('started_at', '<=', end))
        .order_by('started_at')
        .select(FIELDS)
        .limit(PAGE_LIMIT)
    )
    result = []
    while True:
        page = list(query.stream())
        result.extend(
            dict(doc.to_dict(), id=doc.id) for doc in page if not (doc.to_dict() or {}).get('recorded_merged_into')
        )
        if len(page) < PAGE_LIMIT:
            return result
        query = query.start_after(page[-1])


def repointed_members(episode, donor_id, survivor_id):
    """Transfer recorded evidence with a conversation absorption, in the same CAS."""
    members = episode.get('recorded_members')
    if members is None or donor_id not in members:
        return {}
    members = dict(members)
    donor = members.pop(donor_id)
    survivor = members.get(survivor_id, donor)
    members[survivor_id] = {
        **donor,
        **survivor,
        'start': min(donor['start'], survivor['start']),
        'end': max(donor['end'], survivor['end']),
    }
    return {'recorded_members': members}
