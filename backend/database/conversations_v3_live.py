"""Indexed read of a user's recent v3 windows for GET /v1/conversations/live.

It uses the existing ``v3_derived, finished_at, started_at`` index (the derived-window
read in ``conversations_v3``), so legacy in-progress rows never enter the scan however many
exist. The field mask is unconditional and carries no transcript: the live tile needs only
its identity, title, times, state and the visibility flags.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, TypeGuard

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config import server_batch
from config.record_audio import record_identity
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversations import conversations_collection, prepare_conversation_for_read
from database.sync_ledger import sync_content_ledger_ref
from utils.conversations.v3.live import (
    FINISH_FIELDS,
    FINISH_RECORDING_FIELD,
    FINISH_WINDOW_FIELD,
    MAX_IDLE,
    active,
    has_finish_content,
)

logger = logging.getLogger(__name__)

LIVE_FIELDS = [
    'id',
    'structured',
    'user_title',
    'data_protection_level',
    'started_at',
    'created_at',
    'finished_at',
    'status',
    'tile_state',
    'v3_derived',
    'recording',
    'home_hidden',
    'deleted',
    'discarded',
    'is_locked',
    'v3_recording_ids',
    # Reliability experiment end_button_by_device: absent on every row while it is off.
    'v3_capture_device_id',
]
# The index is ascending by finished_at, so the newest window comes last and a read cannot
# stop early once it finds the open one; a reverse-order read would need a new descending
# index. The live tile is polled, so the read goes in two bands instead. An open window's
# finished_at is its latest speech, so it is almost always in the recent band, which holds
# only a few rows. The full idle window is read only when the recent band has no live
# window. READ_CAP bounds the rows one call reads across both bands; reaching it is logged.
RECENT_BAND = timedelta(minutes=10)
PAGE = 50
READ_CAP = 200
# Clock skew allowance for a window that started a moment "in the future".
START_SKEW = timedelta(minutes=5)


def _recent_window_query(collection, now, max_idle):
    return (
        collection.where(filter=FieldFilter('v3_derived', '==', True))
        .where(filter=FieldFilter('finished_at', '>=', now - max_idle))
        .where(filter=FieldFilter('started_at', '<=', now + START_SKEW))
    )


def recent_windows(
    uid: str,
    *,
    now: datetime,
    max_idle: timedelta,
    finished_before: Optional[datetime] = None,
    max_rows: int = READ_CAP,
    firestore_client: Any = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """v3 windows whose last speech is inside ``max_idle``, projected to the live fields.

    ``finished_before`` excludes windows whose last speech is at or after it, so a wider band
    does not re-read a narrower one. Returns the prepared rows and the number of
    documents read (at most ``max_rows``).
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    query = _recent_window_query(collection, now, max_idle)
    if finished_before is not None:
        query = query.where(filter=FieldFilter('finished_at', '<', finished_before))
    # Explicit, so pages run oldest to newest whatever the implicit order of the two range
    # fields; the v3 window index (finished_at ASC, started_at ASC) serves it.
    query = query.order_by('finished_at').select(LIVE_FIELDS)
    rows: List[Dict[str, Any]] = []
    read = 0
    last: Optional[Any] = None
    while read < max_rows:
        size = min(PAGE, max_rows - read)
        snapshots = list((query.start_after(last) if last is not None else query).limit(size).stream())
        read += len(snapshots)
        for snapshot in snapshots:
            row = prepare_conversation_for_read(dict(snapshot.to_dict() or {}, id=snapshot.id), uid)
            if row is not None:
                rows.append(row)
        if len(snapshots) < size:
            return rows, read
        last = snapshots[-1]
    logger.warning('v3 live read stopped at its bound of %d windows', max_rows)
    return rows, read


def live_window(
    uid: str,
    *,
    now: datetime,
    max_idle: timedelta,
    pick: Callable[[Sequence[Mapping[str, Any]], datetime], Optional[Mapping[str, Any]]],
    firestore_client: Any = None,
) -> Optional[Mapping[str, Any]]:
    """The window ``pick`` chooses, reading the recent band first and widening only if needed."""
    left = READ_CAP
    recent = min(RECENT_BAND, max_idle)
    # The bands are disjoint, so the wider one never re-reads the recent one.
    for band, finished_before in ((recent, None), (max_idle, now - recent)):
        rows, read = recent_windows(
            uid,
            now=now,
            max_idle=band,
            finished_before=finished_before,
            max_rows=left,
            firestore_client=firestore_client,
        )
        row = pick(rows, now)
        left -= read
        if row is not None or left <= 0:
            return row
    return None


def _valid_document_id(value: Any) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value.isascii()
        and value.isprintable()
        and '/' not in value
        and value not in {'.', '..'}
        and not (value.startswith('__') and value.endswith('__'))
    )


def live_window_by_id(
    uid: str, cid: str, *, now: datetime, firestore_client: Any = None
) -> Optional[Mapping[str, Any]]:
    if not _valid_document_id(cid):
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection(conversations_collection).document(cid)
    row = ref.get(field_paths=LIVE_FIELDS).to_dict() or {}
    if not _is_finishable_window(row, now):
        return None
    return prepare_conversation_for_read({**row, 'id': cid}, uid, firestore_client=client)


def _is_finishable_window(row: Mapping[str, Any], now: datetime) -> bool:
    started = row.get('started_at')
    return bool(
        isinstance(started, datetime)
        and started <= now + START_SKEW
        and isinstance(row.get('finished_at'), datetime)
        and not row.get('is_locked')
        and active([row], now)
    )


def _native_projection_state(client, tx, uid, cid):
    """The native ledger reaches completed only after the whole record projects."""
    content, _ = record_identity(uid, cid)
    ledger = sync_content_ledger_ref(client, uid, content).get(transaction=tx).to_dict() or {}
    if not ledger:
        return 'pending'  # A closed server-batch recording has a durable admission obligation.
    if ledger.get('dispatch_protocol') != 'batch_v1' or ledger.get('job_id') != 'bp_' + content:
        return 'unavailable'
    if ledger.get('status') == 'processing':
        return 'pending'
    result = ledger.get('result') or {}
    # Completion is written only after the native binding's sibling ready checks.
    if (
        ledger.get('status') == 'completed'
        and (ledger.get('batch_pipeline') or {}).get('segment_ids')
        and not any(
            result.get(k) for k in ('reason_code', 'failed_segments', 'superseded_segments', 'deleted_output_segments')
        )
    ):
        if result.get('outcome') == 'expected_silence' or (
            result.get('no_recoverable_speech_segments')
            and (
                result.get('no_recoverable_speech_segments') == result.get('total_segments')
                or not (result.get('new_memories') or result.get('updated_memories'))
            )
        ):
            return 'empty'
        if result.get('outcome') == 'success' and cid in (
            (result.get('new_memories') or []) + (result.get('updated_memories') or [])
        ):
            return 'complete'
    return 'unavailable'


def _can_retarget_finish(row: Mapping[str, Any], previous_id: str, window_id: str) -> bool:
    """A later, unambiguous tail claim can take over a pending request."""
    ends: dict[str, datetime] = {}
    for claim in row.get('claims') or ():
        if not isinstance(claim, dict):
            return False
        cid, end = claim.get('conversation_id'), claim.get('end')
        if not isinstance(cid, str) or not isinstance(end, datetime):
            return False
        ends[cid] = max(end, ends.get(cid, end))
    if previous_id not in ends or window_id not in ends or ends[previous_id] >= ends[window_id]:
        return False
    return all(end < ends[window_id] for cid, end in ends.items() if cid != window_id)


def request_finish(uid: str, window_id: str, *, now: datetime, firestore_client: Any = None) -> Tuple[str, str]:
    """Store a cut on the current tail source, fenced by the live window in the same transaction."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    window_ref = collection.document(window_id)

    @firestore.transactional
    def commit(tx):
        window = window_ref.get(transaction=tx, field_paths=FINISH_FIELDS).to_dict() or {}
        if not _is_finishable_window(window, now):
            return 'no_live_window', ''
        members = window.get('v3_recording_ids') or []
        # The planner appends new contributing recordings in speech order. An
        # unavailable tail must not move the cut back to a previous recording.
        cid = members[-1] if isinstance(members, list) and members else None
        if not _valid_document_id(cid):
            return 'no_recording', ''
        ref = collection.document(cid)
        row = ref.get(transaction=tx).to_dict() or {}
        if (
            row.get('recording') is not True
            or row.get('status') != 'completed'
            or not isinstance(row.get('finished_at'), datetime)
            # An older overlapping source must not cut through already-visible speech.
            or row['finished_at'] < window['finished_at']
            or any(row.get(key) for key in ('deleted', 'is_locked', 'sync_merged_into'))
            or row.get('data_protection_level') == 'private'
        ):
            return 'no_recording', ''
        marked_window = row.get(FINISH_WINDOW_FIELD)
        request_pending = row.get('v3_manual_end_requested') is True
        requested_here = request_pending and marked_window == window_id
        resolved_here = row.get('v3_manual_end_requested') is False and marked_window == window_id
        if row.get('discarded'):
            return ('already_empty', cid) if resolved_here else ('no_recording', '')
        if row.get('v3_manual_end'):
            return 'already_cut', cid
        if (
            request_pending
            and marked_window
            and not requested_here
            and not _can_retarget_finish(row, marked_window, window_id)
        ):
            return 'request_conflict', ''
        if server_batch.owned(row):
            if row.get('record_audio_partial') or row.get('record_upload_failed'):
                return 'batch_unavailable', ''
            state = _native_projection_state(client, tx, uid, cid)
            if state == 'pending':
                if not server_batch.manual_end_marker_enabled():
                    return 'batch_disabled', ''
                if requested_here:
                    return 'already_requested', cid
                tx.update(ref, {'v3_manual_end_requested': True, FINISH_WINDOW_FIELD: window_id})
                return 'requested', cid
            if state == 'unavailable':
                return ('already_empty', cid) if resolved_here else ('batch_unavailable', '')
            if (resolved_here or state == 'empty' or row.get('has_content') is False) and not has_finish_content(
                row, window, cid
            ):
                if requested_here:
                    tx.update(ref, {'v3_manual_end_requested': False})
                    return 'resolved_empty', cid
                return 'already_empty', cid
        tx.update(
            ref,
            {
                'v3_manual_end': True,
                'v3_pending': True,
                'v3_pending_since': row.get('v3_pending_since') or now,
                FINISH_WINDOW_FIELD: window_id,
            },
        )
        return ('consumed' if requested_here else 'cut'), cid

    return commit(client.transaction())


RECENT_FINISH_AGE = timedelta(minutes=5)
RECENT_FINISH_LIMIT = 8
RECENT_FINISH_FIELDS = [
    'created_at',
    'started_at',
    'finished_at',
    'status',
    'source',
    'recording',
    'data_protection_level',
    'v3_derived',
    'deleted',
    'discarded',
    'is_locked',
    'sync_merged_into',
    'claims',
    'v3_pending',
    'v3_pending_since',
    'v3_manual_end',
    'v3_manual_end_requested',
    FINISH_WINDOW_FIELD,
    FINISH_RECORDING_FIELD,
    'has_content',
    'v3_speech_landed_at',
    'record_projection_revision',
    'record_lane_owner',
    'server_batch_only',
    'record_audio_partial',
    'record_upload_failed',
    'external_data.recording_session_id',
    'external_data.server_batch_only',
    'server_batch_audio_start',
    'server_batch_audio_end',
]


def _recent_finish_sources(collection, tx, now):
    return list(
        collection.where(filter=FieldFilter('finished_at', '>=', now - RECENT_FINISH_AGE))
        .order_by('finished_at', direction=firestore.Query.DESCENDING)
        .select(RECENT_FINISH_FIELDS)
        .limit(RECENT_FINISH_LIMIT)
        .stream(transaction=tx)
    )


def request_recording_finish(uid: str, *, now: datetime, firestore_client: Any = None):
    """Finish one just-sealed Listen source before it has a derived window."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)

    @firestore.transactional
    def commit(tx):
        docs = _recent_finish_sources(collection, tx, now)
        if len(docs) >= RECENT_FINISH_LIMIT:
            return 'recording_lookup_capped', None
        rows = [(doc.id, doc.to_dict() or {}) for doc in docs]
        captures = [
            (cid, row)
            for cid, row in rows
            if not row.get('v3_derived')
            and row.get('source') in {'omi', 'phone'}
            and (row.get('external_data') or {}).get('recording_session_id')
        ]
        if len(captures) != 1:
            return ('recording_ambiguous' if captures else 'no_live_window'), None
        cid, row = captures[0]
        if (
            row.get('recording') is not True
            or row.get('status') != 'completed'
            or not isinstance(row.get('created_at'), datetime)
            or not isinstance(row.get('started_at'), datetime)
            or not isinstance(row.get('finished_at'), datetime)
            or not now - RECENT_FINISH_AGE <= row['finished_at'] <= now
            or not row['started_at'] <= row['finished_at']
            or row.get('data_protection_level') == 'private'
            or any(
                row.get(key)
                for key in (
                    'claims',
                    'deleted',
                    'discarded',
                    'is_locked',
                    'sync_merged_into',
                    'record_audio_partial',
                    'record_upload_failed',
                    FINISH_WINDOW_FIELD,
                )
            )
        ):
            return 'recording_ineligible', None
        windows = list(
            _recent_window_query(collection, now, MAX_IDLE)
            .order_by('finished_at')
            .select(FINISH_FIELDS)
            .limit(READ_CAP)
            .stream(transaction=tx)
        )
        if len(windows) >= READ_CAP:
            return 'window_lookup_capped', None
        if any(_is_finishable_window(window.to_dict() or {}, now) for window in windows):
            return 'no_live_window', None  # A live window appeared before the recording cut.
        marker = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
        ):
            return 'recording_ineligible', None
        response_row = {key: row[key] for key in ('created_at', 'started_at', 'finished_at', 'source', 'recording')}
        response_row.update(id=cid, structured={})
        if row.get(FINISH_RECORDING_FIELD):
            if row.get('v3_manual_end'):
                return 'already_cut', response_row
            if row.get('v3_manual_end_requested') is False:
                return 'already_empty', response_row
        elif row.get('v3_manual_end') or row.get('v3_manual_end_requested'):
            return 'recording_ineligible', None

        ref = collection.document(cid)
        if server_batch.owned(row):
            state = _native_projection_state(client, tx, uid, cid)
            if state == 'pending' and server_batch.has_retained_audio(row):
                if not server_batch.manual_end_marker_enabled():
                    return 'batch_disabled', None
                if row.get('v3_manual_end_requested') is True:
                    return 'already_requested', response_row
                tx.update(ref, {'v3_manual_end_requested': True, FINISH_RECORDING_FIELD: True})
                return 'recording_requested', response_row
            if state not in {'complete', 'empty'}:
                return 'batch_unavailable', None
            if not has_finish_content(row, {}, cid):
                if row.get('v3_manual_end_requested') is True:
                    tx.update(ref, {'v3_manual_end_requested': False})
                    return 'resolved_empty', response_row
                return 'already_empty', response_row
        elif not (row.get('v3_pending') and has_finish_content(row, {}, cid)):
            return 'recording_ineligible', None

        tx.update(
            ref,
            {
                'v3_manual_end': True,
                'v3_pending': True,
                'v3_pending_since': row.get('v3_pending_since') or now,
                FINISH_RECORDING_FIELD: True,
            },
        )
        return ('consumed' if row.get('v3_manual_end_requested') is True else 'recording_cut'), response_row

    return commit(client.transaction())
