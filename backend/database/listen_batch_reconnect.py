"""One fenced producer at a time; socket drain never closes the logical archive.

The parent conversation is the transaction conflict boundary shared with normal
finalization and deletion. No job, generation, transcript or billing is changed.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.cloud import firestore

from config import listen_reconnect as config
from config.occasion_conversations import OCCASION_MAX_SPAN_SECONDS
from config.server_batch import owned, has_audio
from database._client import get_firestore_client, run_transactional
from database.batch_pipeline_privacy import assert_batch_write_allowed
from models.conversation_continuity import calendar_continuity_window, continuation_timeout, resumable_continuation
from utils.conversations.lifecycle_clocks import speech_clock


def _refs(client, uid, cid, sid):
    user = client.collection('users').document(uid)
    return user.collection('conversations').document(cid), user.collection('recording_sessions').document(sid)


def _open(row):
    return bool(
        owned(row)
        and row.get('status') == 'in_progress'
        and not row.get('server_batch_audio_closed')
        and not any(row.get(k) for k in ('deleted', 'discarded', 'is_locked', 'deferred', 'finalization_job_id'))
    )


def _boundary(row, now, zone_name):
    start = config.utc(row.get('started_at'))
    try:
        zone = ZoneInfo(zone_name or 'UTC')
    except (ValueError, ZoneInfoNotFoundError):
        zone = ZoneInfo('UTC')
    if start is None:
        return now
    midnight = datetime.combine(start.astimezone(zone).date() + timedelta(days=1), datetime.min.time(), zone)
    end = min(start + timedelta(seconds=OCCASION_MAX_SPAN_SECONDS), midnight)
    context = (row.get('external_data') or {}).get('calendar_meeting_context') or {}
    window = calendar_continuity_window(context)
    if window:
        end = min(end, window[1])
    return end


def claim(
    uid: str,
    conversation_id: str,
    recording_session_id: str,
    *,
    token: str,
    origin_id: str,
    source: str,
    device_id: str,
    now: datetime,
    timeout: int,
    firestore_client: Any = None,
) -> str:
    if not config.enabled():
        return 'disabled'
    client = firestore_client if firestore_client is not None else get_firestore_client()
    row_ref, session_ref = _refs(client, uid, conversation_id, recording_session_id)

    @firestore.transactional
    def commit(tx):
        snapshots = {}
        assert_batch_write_allowed(client, tx, uid, conversation_ids=(conversation_id,), snapshots=snapshots)
        row = snapshots.get('conversations', {}).get(conversation_id) or {}
        session = session_ref.get(transaction=tx).to_dict() or {}
        state = config.producer(row)
        if not _open(row) or not row.get('private_cloud_sync_enabled') or row.get('uses_custom_stt'):
            return 'refused'
        if (
            session.get('uid') != uid
            or session.get('conversation_id') != conversation_id
            or session.get('lifecycle_phase') != 'in_progress'
        ):
            return 'refused'
        external = row.get('external_data') or {}
        origin = state.get('origin_id') or external.get('recording_origin_id') or row.get('id')
        if not origin_id or not device_id or origin != origin_id:
            return 'refused'
        if not resumable_continuation(row, source=source, device_id=device_id, arrival_at=now, timeout=timeout):
            return 'expired'
        boundary = _boundary(row, now, (snapshots.get('user') or {}).get('time_zone'))
        if boundary <= now or state.get('phase') == 'ended':
            return 'expired'
        if state.get('phase') == 'disconnected':
            end = config.utc(state.get('deadline_at'))
            if end is None or now >= end:
                return 'expired'
        if state.get('phase') == 'active' and state.get('token') != token:
            # Expiry is permission to try a new producer, never evidence of drain.
            lease = config.utc(state.get('lease_expires_at'))
            if lease is None or lease > now:
                return 'busy'
        lease = now + timedelta(seconds=config.LEASE_SECONDS)
        tx.update(
            row_ref,
            {
                'external_data.recording_session_id': recording_session_id,
                config.FIELD: {
                    'version': 1,
                    'token': token,
                    'origin_id': origin_id,
                    'recording_session_id': recording_session_id,
                    'phase': 'active',
                    'lease_expires_at': lease,
                    'boundary_at': boundary,
                    'drained': False,
                },
            },
        )
        tx.update(session_ref, {'lease_expires_at': lease, 'listen_producer_token': token, 'updated_at': now})
        return 'claimed'

    return run_transactional(client, commit)


def renew(uid, conversation_id, recording_session_id, token, *, now, firestore_client=None) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    row_ref, session_ref = _refs(client, uid, conversation_id, recording_session_id)

    @firestore.transactional
    def commit(tx):
        row = row_ref.get(transaction=tx).to_dict() or {}
        session = session_ref.get(transaction=tx).to_dict() or {}
        if not _open(row) or not config.write_owned(row, token) or session.get('listen_producer_token') != token:
            return False
        lease = now + timedelta(seconds=config.LEASE_SECONDS)
        tx.update(row_ref, {f'{config.FIELD}.lease_expires_at': lease})
        tx.update(session_ref, {'lease_expires_at': lease, 'updated_at': now})
        return True

    return run_transactional(client, commit)


def disconnect(
    uid,
    conversation_id,
    recording_session_id,
    token,
    *,
    disconnected_at,
    now,
    timeout,
    terminal=False,
    firestore_client=None,
) -> str:
    """Caller has sealed/drained its archive. Replays cannot extend the deadline."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    row_ref, session_ref = _refs(client, uid, conversation_id, recording_session_id)

    @firestore.transactional
    def commit(tx):
        snapshots = {}
        assert_batch_write_allowed(client, tx, uid, conversation_ids=(conversation_id,), snapshots=snapshots)
        row = snapshots.get('conversations', {}).get(conversation_id) or {}
        session = session_ref.get(transaction=tx).to_dict() or {}
        state = config.producer(row)
        if not _open(row) or state.get('token') != token or session.get('listen_producer_token') != token:
            return 'fenced'
        if state.get('phase') != 'active':
            if terminal and state.get('phase') == 'disconnected':
                tx.update(row_ref, {config.FIELD: {**state, 'phase': 'ended', 'deadline_at': now}})
                return 'ended'
            return 'held' if state.get('phase') == 'disconnected' else 'ended'
        finish = speech_clock(uid, row)
        if finish is None:
            return 'fenced'
        quiet = finish + timedelta(seconds=continuation_timeout(row, timeout))
        end = min(disconnected_at + timedelta(seconds=config.grace_seconds()), quiet, state['boundary_at'])
        if terminal or not has_audio(row):
            end = now
        phase = 'ended' if terminal or end <= now else 'disconnected'
        tx.update(row_ref, {config.FIELD: {**state, 'phase': phase, 'deadline_at': end, 'drained': True}})
        tx.update(session_ref, {'lease_expires_at': now, 'updated_at': now})
        return 'held' if phase == 'disconnected' else 'ended'

    return run_transactional(client, commit)


def end_disabled_hold(uid, conversation_id, *, now, firestore_client=None) -> bool:
    """Retire an already drained hold without taking over its producer or terminal data.

    The caller rearms the existing quiet outbox due now. A crash before rearming
    still has the previously indexed wake (at most 120 seconds after drain).
    """
    if config.enabled():
        return False
    client = firestore_client if firestore_client is not None else get_firestore_client()
    row_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        snapshots = {}
        assert_batch_write_allowed(client, tx, uid, conversation_ids=(conversation_id,), snapshots=snapshots)
        row = snapshots.get('conversations', {}).get(conversation_id) or {}
        state = config.producer(row)
        if not _open(row) or state.get('phase') != 'disconnected' or state.get('drained') is not True:
            return False
        tx.update(row_ref, {config.FIELD: {**state, 'phase': 'ended', 'deadline_at': now}})
        return True

    return run_transactional(client, commit)
