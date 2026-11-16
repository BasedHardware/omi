"""Fenced live admission and repair of post-gap live members. Metadata only."""

from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from typing import Any, Mapping

from google.cloud import firestore

from config import episode_live_members as live
from config.episodes import CLOSE_GAP_SECONDS, MAX_EPISODE_SECONDS, MAX_MOMENTS, MAX_PROVISIONAL_ITEMS
from database import episodes, episode_timeline, episode_batch_pending
from database.transcript_pointer import run_preloaded_transactional
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.conversations.recorded_time import admitted_start, conversation_span


def _remove_member(transaction: Any, root: Any, owner: Mapping[str, Any], cid: str, start: datetime) -> dict[str, Any]:
    """Read retained clocks before any writes; never remove a recording document."""
    if len(owner.get('conversation_ids') or []) > episodes.MEMBERSHIP_BATCH_LIMIT:
        raise episodes.EpisodeConflict('live_member_repair_read_budget')
    result = dict(owner)
    for key in (
        'conversation_ids',
        'recovered_conversation_ids',
        'discarded_conversation_ids',
        'duplicate_conversation_ids',
    ):
        result[key] = [member for member in owner.get(key) or [] if member != cid]
    for key in (
        'member_activity',
        'recorded_members',
        'parallel_content_spans',
        'pending_boundary',
        'applied',
        'applied_segment_ids',
    ):
        if key in owner:
            result[key] = {member: value for member, value in (owner.get(key) or {}).items() if member != cid}
    for key in ('moments', 'provisional_items'):
        result[key] = [item for item in owner.get(key) or [] if item.get('conversation_id') != cid]
    ends = []
    for member in result['conversation_ids']:
        row: dict[str, Any] = (
            root.collection('conversations').document(member).get(transaction=transaction).to_dict() or {}
        )
        if any(row.get(k) for k in ('deleted', 'sync_merged_into')) or is_relevance_discarded(row):
            continue
        span = conversation_span(row)
        end = span.recorded_end if span else (result.get('member_activity') or {}).get(member)
        if isinstance(end, datetime):
            ends.append(end)
    result.update(
        last_activity_at=max(owner['started_at'], min(start, max(ends, default=owner['started_at']))),
        home_needs_prepare=True,
        summary_needs_regeneration=True,
        state_version=int(owner.get('state_version') or 0) + 1,
    )
    result['recorded_end'] = result['last_activity_at']
    if result.get('primary_conversation_id') == cid:
        result['primary_conversation_id'] = next(iter(result['conversation_ids']), None)
    return result


def place(
    uid: str,
    cid: str,
    *,
    template: Mapping[str, Any],
    firestore_client: Any,
    admission: bool = False,
    pending_at: datetime | None = None,
    deadline_floor: datetime | None = None,
) -> dict[str, Any] | str | None:
    """Return None for legacy placement, or committed owner with a rehome receipt.

    The member, current pointer, episode and timeline fence share a transaction.
    A close/assignment winner makes the other callback retry from fresh state.
    Only a still-capturing member beyond a silence boundary may change owners.
    """
    client = firestore_client

    @firestore.transactional
    def commit(transaction: Any) -> dict[str, Any] | str | None:
        root = client.collection('users').document(uid)
        collection = root.collection('episodes')
        links = root.collection('episode_links')
        row: dict[str, Any] = (
            root.collection('conversations').document(cid).get(transaction=transaction).to_dict() or {}
        )
        if admission and (row.get('record_audio_closed') or row.get('server_batch_audio_closed')):
            return 'closed'
        if (
            not live.capturing(row)
            or row.get('private_cloud_sync_enabled') is not True
            or row.get('uses_custom_stt')
            or row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}
            or is_relevance_discarded(row)
        ):
            raise episodes.EpisodeConflict('live_member_capture_changed')
        members = episodes.read_memberships(transaction, client, uid, [cid], admit_conversation_id=cid)
        linked = members[cid][1].get('episode_id') or row.get('episode_id')
        owner = (
            episodes.unseal(uid, collection.document(linked).get(transaction=transaction).to_dict()) if linked else None
        )
        if linked and (not owner or cid not in (owner.get('conversation_ids') or [])):
            raise episodes.EpisodeConflict('live_member_owner_changed')
        boundary = owner.get('closed_at') if owner else None
        if owner and (
            owner.get('status') == 'live'
            or owner.get('close_reason') not in {'gap', 'idle'}
            or not isinstance(boundary, datetime)
        ):
            return {**owner, '_live_member_rehomed': False}
        # Re-read all clocks in the ownership transaction, including every retry.
        if owner is not None:
            capture = live.capture_start(row, now=datetime.now(timezone.utc))
        else:
            start = admitted_start(row)
            if start is None:
                return None  # Preserve the existing admission caller's no-start behavior.
            capture = live.CaptureStart(lower=start, upper=start)
        refusal = capture.refusal
        if (
            not refusal
            and isinstance(boundary, datetime)
            and capture.lower is not None
            and capture.upper is not None
            and capture.lower < boundary <= capture.upper
        ):
            refusal = 'disagreement'
        if refusal:
            if owner:
                return {**owner, '_live_member_rehomed': False, '_live_member_clock_refusal': refusal}
            raise episodes.EpisodeConflict('live_member_capture_clock_' + refusal)
        start = capture.lower
        if start is None:
            raise episodes.EpisodeConflict('live_member_capture_clock_missing')
        if owner and isinstance(boundary, datetime) and start < boundary:
            return {**owner, '_live_member_rehomed': False}
        fence = links.document('recorded_timeline')
        fence_row = fence.get(transaction=transaction).to_dict() or {}
        current = links.document('current').get(transaction=transaction).to_dict() or {}
        current_id = current.get('episode_id')
        current_owner = (
            episodes.unseal(uid, collection.document(current_id).get(transaction=transaction).to_dict())
            if current_id
            else None
        )
        rows: list[dict[str, Any]] = episode_timeline.recorded_candidates(
            uid, start, start, firestore_client=client, transaction=transaction
        )
        removed = _remove_member(transaction, root, owner, cid, start) if owner else None
        if removed:
            rows = [removed if candidate['id'] == removed['id'] else candidate for candidate in rows]
        previous: dict[str, Any] | None = None
        target: dict[str, Any] | None = (
            current_owner if current_owner and current_owner.get('status') == 'live' else None
        )
        if target and start < target['started_at']:
            if (target['started_at'] - start).total_seconds() >= CLOSE_GAP_SECONDS or (
                target['last_activity_at'] - start
            ).total_seconds() > MAX_EPISODE_SECONDS:
                # Keep an uncertain legacy membership; a new admission retries
                # rather than falling back into the closed predecessor.
                if owner:
                    return {**owner, '_live_member_rehomed': False}
                raise episodes.EpisodeConflict('live_member_successor_out_of_window')
            target = {**target, 'started_at': start}
        if target:
            end = min(
                target['last_activity_at'] + timedelta(seconds=CLOSE_GAP_SECONDS),
                target['started_at'] + timedelta(seconds=MAX_EPISODE_SECONDS),
            )
            if start >= end:
                previous = {
                    **target,
                    'status': 'closed',
                    'close_reason': (
                        'hard_cap' if end == target['started_at'] + timedelta(seconds=MAX_EPISODE_SECONDS) else 'gap'
                    ),
                    'closed_at': end,
                    'recorded_end': target['last_activity_at'],
                    'state_version': int(target.get('state_version') or 0) + 1,
                    'home_needs_prepare': True,
                    'summary_needs_regeneration': True,
                    'pending_boundary': {},
                    'provisional_items': [
                        {**item, 'status': 'dropped'} if item.get('status') == 'provisional' else item
                        for item in target.get('provisional_items') or []
                    ],
                }
                rows = [previous if candidate['id'] == previous['id'] else candidate for candidate in rows]
                target = None
        if (
            target is None
            and owner is None
            and any(
                candidate.get('status') != 'live'
                and isinstance(candidate.get('closed_at'), datetime)
                and candidate['started_at'] <= start < candidate['closed_at']
                for candidate in rows
            )
        ):
            return None  # Truly overlapping historical audio keeps recorded-time ownership.
        if target is None:
            # Do not reopen a closed occasion. A new capture at or beyond its
            # gap boundary opens the next live episode, independent of arrival.
            target = {
                **template,
                'id': str(uuid5(NAMESPACE_URL, f'live-episode:{uid}:{cid}:{start.isoformat()}')),
                'status': 'live',
                'close_reason': None,
                'closed_at': None,
                'started_at': start,
                'last_activity_at': start,
                'conversation_ids': [],
                'member_activity': {},
                'state_version': 0,
            }
        activity = start
        audio_end = row.get('server_batch_audio_end')
        if isinstance(audio_end, (int, float)) and not isinstance(audio_end, bool):
            try:
                activity = max(start, min(datetime.now(timezone.utc), datetime.fromtimestamp(audio_end, timezone.utc)))
            except (ValueError, OverflowError, OSError):
                pass
        activity = min(activity, target['started_at'] + timedelta(seconds=MAX_EPISODE_SECONDS))
        result: dict[str, Any] = {
            **target,
            'conversation_ids': list(dict.fromkeys([*(target.get('conversation_ids') or []), cid])),
            'member_activity': {**(target.get('member_activity') or {}), cid: activity},
            'last_activity_at': max(activity, target['last_activity_at']),
            'state_version': int(target.get('state_version') or 0) + 1,
            'home_needs_prepare': True,
        }
        if removed and owner is not None:
            if cid in (owner.get('recovered_conversation_ids') or []):
                result['recovered_conversation_ids'] = list(
                    dict.fromkeys([*(target.get('recovered_conversation_ids') or []), cid])
                )
            for key in ('moments', 'provisional_items'):
                carried = [item for item in owner.get(key) or [] if item.get('conversation_id') == cid]
                if carried:
                    result[key] = list({item['id']: item for item in [*(target.get(key) or []), *carried]}.values())
                    if len(result[key]) > (MAX_MOMENTS if key == 'moments' else MAX_PROVISIONAL_ITEMS):
                        raise episodes.EpisodeConflict('live_member_carry_capacity')
            for key in ('applied', 'applied_segment_ids'):
                if cid in (owner.get(key) or {}):
                    result[key] = {**(target.get(key) or {}), cid: owner[key][cid]}
        source = row.get('source')
        result['sources'] = list(dict.fromkeys([*(target.get('sources') or []), *([source] if source else [])]))
        # Validate the proposed topology, including the predecessor after detach.
        # An optimization-off re-query must not validate against its old window.
        lo, hi = result['started_at'], result['last_activity_at']
        for candidate in rows:
            a, b = candidate['started_at'], episode_timeline.recorded_end(candidate)
            if candidate['id'] != result['id'] and isinstance(b, datetime):
                if lo == a or (lo < b and a < hi) or (lo == hi and a <= lo < b):
                    raise episodes.EpisodeConflict('recorded_window_overlap')
        pending_patch = episode_batch_pending.read_patch(
            transaction, client, uid, cid, pending_at, deadline_floor=deadline_floor
        )
        # All reads above; topology, reverse links and Home invalidation commit together.
        if removed:
            transaction.set(collection.document(removed['id']), episodes.seal(uid, removed))
        if previous:
            transaction.set(collection.document(previous['id']), episodes.seal(uid, previous))
            transaction.set(links.document('last_closed'), {'episode_id': previous['id']})
        transaction.set(collection.document(result['id']), episodes.seal(uid, result))
        episodes.write_memberships(transaction, client, uid, result['id'], members, datetime.now(timezone.utc))
        if pending_patch:
            transaction.update(root.collection('conversations').document(cid), pending_patch)
        transaction.set(
            links.document('current'), {'episode_id': result['id'], 'updated_at': datetime.now(timezone.utc)}
        )
        transaction.set(fence, {'version': int(fence_row.get('version') or 0) + 1})
        return {**result, '_live_member_rehomed': removed is not None, '_live_member_closed_episode': previous}

    return run_preloaded_transactional(client, commit, transient=True)
