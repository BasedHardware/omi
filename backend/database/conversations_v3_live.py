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
from utils.observability.fallback import record_fallback
from utils.conversations.v3 import metrics as v3_metrics
from utils.conversations.v3.live import (
    FINISH_FIELDS,
    FINISH_RECORDING_FIELD,
    FINISH_STAMP_FIELD,
    FINISH_WINDOW_FIELD,
    MAX_IDLE,
    active,
    finish_stamp,
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
    return live_window_lookup(uid, now=now, max_idle=max_idle, pick=pick, firestore_client=firestore_client)[0]


def live_window_lookup(
    uid: str,
    *,
    now: datetime,
    max_idle: timedelta,
    pick: Callable[[Sequence[Mapping[str, Any]], datetime], Optional[Mapping[str, Any]]],
    firestore_client: Any = None,
) -> Tuple[Optional[Mapping[str, Any]], bool]:
    """``(window, complete)``. ``complete`` is False when READ_CAP ran out before ``pick`` found one,
    so an absent window is unknown rather than proven."""
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
        if row is not None:
            return row, True
        if left <= 0:
            return None, False
    return None, True


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


def request_finish(
    uid: str, window_id: str, *, now: datetime, newer_capture: bool = False, firestore_client: Any = None
) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Store a cut on the current tail source, fenced by the live window in the same transaction.

    With ``newer_capture``, a capture that sealed after the window's last speech and that no window
    holds yet is the person's last speech, so the cut lands on it instead (``_newer_capture``).
    Returns ``(outcome, recording id, response row)``; the row is set only when the cut moved.

    The first write on the response target also stamps the Finish (``FINISH_STAMP_FIELD``, path ``tail``,
    ``newer`` or ``newer_dual``) for the one ``FINISH_TO_VISIBLE`` sample. In the stored-both case only the
    window tail, which the answer names, is stamped; the capture's request rides along unstamped.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    window_ref = collection.document(window_id)
    # The transaction body re-runs on contention and each attempt resets this, so what remains is the committed
    # attempt's. Fallback telemetry is recorded once, after the commit, never from inside the body.
    degraded: List[bool] = []
    declined: List[str] = []

    @firestore.transactional
    def commit(tx):
        degraded.clear()
        declined.clear()
        window = window_ref.get(transaction=tx, field_paths=FINISH_FIELDS).to_dict() or {}
        if not _is_finishable_window(window, now):
            return 'no_live_window', '', None
        members = window.get('v3_recording_ids') or []
        # The planner appends new contributing recordings in speech order. An
        # unavailable tail must not move the cut back to a previous recording.
        cid = members[-1] if isinstance(members, list) and members else None
        if not _valid_document_id(cid):
            return 'no_recording', '', None
        row = collection.document(cid).get(transaction=tx).to_dict() or {}
        tail_state = None
        newer = (
            _newer_capture(_recent_finish_sources(collection, tx, now), window, now, degraded=degraded)
            if newer_capture
            else None
        )
        if (
            newer is not None
            and newer[0]
            and row.get(FINISH_WINDOW_FIELD) == window_id
            and (row.get('v3_manual_end') or row.get('v3_manual_end_requested') is True)
        ):
            # An earlier tap cut this window's tail and requested the capture: the tail answers.
            newer = None
        if newer is not None:
            retry, newer_id, newer_row = newer
            if _account_deleting(client, tx, uid):
                return 'newer_recording_ineligible', '', None
            # A batch capture whose speech has not landed may hold only silence (the session's last capture
            # often does), and its request then clears at completion without a cut. So the window's own
            # tail is cut too, and the capture's request rides along. Both ledger reads come before either
            # write; every write below follows the last read.
            both = not retry and server_batch.owned(newer_row) and not _batch_speech_landed(newer_row)
            newer_state = _native_projection_state(client, tx, uid, newer_id) if both else None
            tail_state = _batch_state(client, tx, uid, cid, row) if both else None
            # The tail's write is planned (no read, no write) before the capture's, so the capture's request is
            # stamped only when the answer will name it: when the tail has nothing to cut.
            tail_plan = (
                _window_tail_plan(
                    client, tx, uid, window, window_id, cid, row, now, state=tail_state, stamp_path='newer_dual'
                )
                if both
                else None
            )
            outcome, response_row = _finish_capture(
                client,
                tx,
                collection,
                uid,
                newer_id,
                newer_row,
                now,
                state=newer_state,
                stamp_path='newer',
                stamp_request=not (tail_plan and tail_plan[1]),
            )
            if tail_plan is not None and outcome == 'recording_requested':  # the stored-both case
                tail_outcome, recording_id, patch = tail_plan
                if recording_id:
                    if patch:
                        tx.update(collection.document(cid), patch)
                    logger.info('v3 Finish cut the live window tail and requested a capture that sealed after it')
                    return 'newer_dual_' + tail_outcome, recording_id, None
                return 'newer_recording_requested', newer_id, response_row
            if response_row is not None and outcome != 'already_empty':
                if not retry:
                    logger.info('v3 Finish moved from the live window tail to a capture that sealed after it')
                return 'newer_' + outcome, newer_id, response_row
            # The newer capture was selected but declines the cut (already empty, batch unavailable or disabled,
            # or ineligible): _finish_capture wrote nothing, so the tail is cut and answers. The decline is
            # counted apart (FINISH_NEWER_DECLINED) once the transaction commits.
            declined.append(outcome)
        outcome, recording_id = _finish_window_tail(
            client, tx, uid, collection, window, window_id, cid, row, now, state=tail_state, stamp_path='tail'
        )
        return outcome, recording_id, None

    result = commit(client.transaction())
    if degraded:
        _record_newer_capture_fallback()
    if declined:
        reason = declined[0] if declined[0] in v3_metrics.FINISH_NEWER_DECLINED_REASONS else 'recording_ineligible'
        v3_metrics.safe_metric(lambda: v3_metrics.FINISH_NEWER_DECLINED.labels(reason).inc())
    return result


def _finish_window_tail(
    client,
    tx,
    uid,
    collection,
    window,
    window_id,
    cid,
    row,
    now,
    *,
    state: Optional[str] = None,
    stamp_path: Optional[str] = None,
) -> Tuple[str, str]:
    """Store the Finish on ``window_id``'s tail source ``cid``; every read is already done.

    ``state`` is the tail's native ledger state when the caller read it already (``_batch_state``).
    """
    outcome, recording_id, patch = _window_tail_plan(
        client, tx, uid, window, window_id, cid, row, now, state=state, stamp_path=stamp_path
    )
    if patch:
        tx.update(collection.document(cid), patch)
    return outcome, recording_id


def _window_tail_plan(
    client, tx, uid, window, window_id, cid, row, now, *, state: Optional[str] = None, stamp_path=None
) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """``(outcome, recording id, patch)`` for the window-tail Finish; the caller writes ``patch``.

    It reads only ``cid``'s native ledger, and only when ``state`` is not given. With ``stamp_path``, the
    first write this Finish stores on the tail (the request or the cut, not the consuming cut of an earlier
    request) carries the Finish stamp.
    """
    stamp = {FINISH_STAMP_FIELD: finish_stamp(now, stamp_path)} if stamp_path else {}
    if (
        row.get('recording') is not True
        or row.get('status') != 'completed'
        or not isinstance(row.get('finished_at'), datetime)
        # An older overlapping source must not cut through already-visible speech.
        or row['finished_at'] < window['finished_at']
        or any(row.get(key) for key in ('deleted', 'is_locked', 'sync_merged_into'))
        or row.get('data_protection_level') == 'private'
    ):
        return 'no_recording', '', None
    marked_window = row.get(FINISH_WINDOW_FIELD)
    request_pending = row.get('v3_manual_end_requested') is True
    requested_here = request_pending and marked_window == window_id
    resolved_here = row.get('v3_manual_end_requested') is False and marked_window == window_id
    if row.get('discarded'):
        return ('already_empty', cid, None) if resolved_here else ('no_recording', '', None)
    if row.get('v3_manual_end'):
        return 'already_cut', cid, None
    if (
        request_pending
        and marked_window
        and not requested_here
        and not _can_retarget_finish(row, marked_window, window_id)
    ):
        return 'request_conflict', '', None
    if server_batch.owned(row):
        if row.get('record_audio_partial') or row.get('record_upload_failed'):
            return 'batch_unavailable', '', None
        state = state or _native_projection_state(client, tx, uid, cid)
        if state == 'pending':
            if not server_batch.manual_end_marker_enabled():
                return 'batch_disabled', '', None
            if requested_here:
                return 'already_requested', cid, None
            return 'requested', cid, {'v3_manual_end_requested': True, FINISH_WINDOW_FIELD: window_id, **stamp}
        if state == 'unavailable':
            return ('already_empty', cid, None) if resolved_here else ('batch_unavailable', '', None)
        if (resolved_here or state == 'empty' or row.get('has_content') is False) and not has_finish_content(
            row, window, cid
        ):
            if requested_here:
                return 'resolved_empty', cid, {'v3_manual_end_requested': False}
            return 'already_empty', cid, None
    return (
        ('consumed' if requested_here else 'cut'),
        cid,
        {
            'v3_manual_end': True,
            'v3_pending': True,
            'v3_pending_since': row.get('v3_pending_since') or now,
            FINISH_WINDOW_FIELD: window_id,
            # A consuming cut keeps the stamp of the Finish that stored the request.
            **({} if requested_here else stamp),
        },
    )


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


# A recording-scoped Finish may not land on a capture in any of these states.
_FINISH_BLOCKERS = (
    'deleted',
    'discarded',
    'is_locked',
    'sync_merged_into',
    'record_audio_partial',
    'record_upload_failed',
)


def _newer_capture(docs, window: Mapping[str, Any], now: datetime, *, degraded: List[bool]):
    """The capture a live-window Finish cuts instead of the window tail, or None to cut the tail.

    A pendant or server-batch capture can seal after the live window's last speech while its
    transcript, and so its place in a window, is still pending. Such a capture is the person's last
    speech. It must be a sealed Listen capture newer than the window's ``finished_at``, not one of
    the window's sources, carry content (``has_content``; a projection that landed empty clears it),
    and pass the recording-Finish checks. The newest one wins, as in ``_latest_capture``; an exact tie
    keeps the tail cut. A capture an earlier recording-scoped Finish marked answers a retry, so a
    second tap never cuts the tail as well, unless that Finish resolved empty: then the window's
    speech is the last speech again. ``docs`` is the newest-first recent-source scan.

    Returns ``(retry, cid, row)`` or None. A marked capture that can no longer take a Finish (private,
    locked, deleted, ...) is None too, so the tail is cut rather than answering a 404. A tie or a full
    scan appends to ``degraded``; the caller records that once the transaction commits.
    """
    members = set(window.get('v3_recording_ids') or ())
    newer = []
    for doc in docs:
        row = doc.to_dict() or {}
        if (
            doc.id not in members
            and _is_sealed_capture(row)
            and isinstance(row.get('finished_at'), datetime)
            and row['finished_at'] > window['finished_at']
        ):
            newer.append((doc.id, row))
    oldest = (docs[-1].to_dict() or {}).get('finished_at') if docs else None
    # A full scan whose oldest row is still newer than the window may hide another newer capture.
    capped = len(docs) >= RECENT_FINISH_LIMIT and not (isinstance(oldest, datetime) and oldest <= window['finished_at'])
    marked = [
        (cid, row)
        for cid, row in newer
        if row.get(FINISH_RECORDING_FIELD)
        and not (row.get('v3_manual_end_requested') is False and not row.get('v3_manual_end'))
    ]
    last_mark = max((row['finished_at'] for _, row in marked), default=None)
    unmarked = [
        (cid, row)
        for cid, row in newer
        # Past a full scan, keep the tail cut rather than guess which capture is the newest.
        if not capped
        and not row.get(FINISH_RECORDING_FIELD)
        and row.get('has_content') is True
        and not _capture_ineligible(row, now)
        # Speech the person already finished after is behind that Finish.
        and (last_mark is None or row['finished_at'] > last_mark)
    ]
    if unmarked:
        newest = max(row['finished_at'] for _, row in unmarked)
        top = [(cid, row) for cid, row in unmarked if row['finished_at'] == newest]
        if len(top) > 1:
            degraded.append(True)
            return None
        return False, *top[0]
    if not marked:
        if capped:
            # The bounded scan may have omitted a newer capture, so keep the safe tail cut and expose the
            # degraded targeting through shared fallback telemetry once the transaction commits.
            degraded.append(True)
        return None
    cid, row = min(((cid, row) for cid, row in marked if row['finished_at'] == last_mark), key=lambda item: item[0])
    if row.get('data_protection_level') == 'private' or any(row.get(key) for key in _FINISH_BLOCKERS):
        # It can no longer take a Finish. A 404 would read as "already closed" to the app; cut the tail.
        logger.info('v3 Finish found its earlier capture no longer finishable; cutting the window tail')
        return None
    return True, cid, row


def _record_newer_capture_fallback() -> None:
    record_fallback(
        component='conversation_finalization',
        from_mode='newer_capture',
        to_mode='window_tail',
        reason='other',
        outcome='degraded',
    )


def _batch_speech_landed(row: Mapping[str, Any]) -> bool:
    """A server-batch capture's speech landed only with its projection, which rewrites ``has_content``.

    ``has_finish_content`` cannot tell for these: ``mark_new`` stamps ``v3_speech_landed_at`` when the
    recording is created and audio custody sets ``has_content`` on any committed audio, silence included.
    """
    return bool(row.get('has_content') is True and row.get('record_projection_revision'))


def _batch_state(client, tx, uid, cid, row) -> Optional[str]:
    """The tail's native ledger state when ``_finish_window_tail`` would read it, read ahead of any write."""
    if not server_batch.owned(row) or row.get('record_audio_partial') or row.get('record_upload_failed'):
        return None
    return _native_projection_state(client, tx, uid, cid)


def _account_deleting(client, tx, uid) -> bool:
    marker = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
    return account_deletion_marker_blocks_access(
        marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
    )


def _capture_ineligible(row: Mapping[str, Any], now: datetime, *, window_id: Optional[str] = None) -> bool:
    """Not one just-sealed Listen capture that Finish may cut.

    A capture with no window must be unclaimed and unmarked. The tail of a named window may be
    claimed by that window alone; its window marker is judged by the window-tail cut.
    """
    claims = row.get('claims')
    return bool(
        row.get('v3_derived')
        or row.get('source') not in {'omi', 'phone'}
        or not (row.get('external_data') or {}).get('recording_session_id')
        or row.get('recording') is not True
        or row.get('status') != 'completed'
        or not isinstance(row.get('created_at'), datetime)
        or not isinstance(row.get('started_at'), datetime)
        or not isinstance(row.get('finished_at'), datetime)
        or not now - RECENT_FINISH_AGE <= row['finished_at'] <= now
        or not row['started_at'] <= row['finished_at']
        or row.get('data_protection_level') == 'private'
        or any(row.get(key) for key in _FINISH_BLOCKERS)
        or (
            bool(claims or row.get(FINISH_WINDOW_FIELD))
            if window_id is None
            else not _claimed_only_by(claims, window_id)
        )
    )


def _claimed_only_by(claims: Any, window_id: str) -> bool:
    """The window holds a claim on the capture, and no other window does."""
    return (
        isinstance(claims, list)
        and bool(claims)
        and all(isinstance(claim, dict) and claim.get('conversation_id') == window_id for claim in claims)
    )


def _live_window_or_deleting(client, tx, collection, uid, now) -> Optional[str]:
    """Why a recording-scoped Finish must not cut now, or None. Reads only; runs before any write."""
    windows = list(
        _recent_window_query(collection, now, MAX_IDLE)
        .order_by('finished_at')
        .select(FINISH_FIELDS)
        .limit(READ_CAP)
        .stream(transaction=tx)
    )
    if len(windows) >= READ_CAP:
        return 'window_lookup_capped'
    if any(_is_finishable_window(window.to_dict() or {}, now) for window in windows):
        return 'no_live_window'  # A live window appeared before the recording cut.
    if _account_deleting(client, tx, uid):
        return 'recording_ineligible'
    return None


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
        # A speech-pause rotation writes the next capture in progress before it seals the last one;
        # only sealed captures compete.
        captures = [(cid, row) for cid, row in rows if _is_sealed_capture(row)]
        if len(captures) != 1:
            return ('recording_ambiguous' if captures else 'no_live_window'), None
        cid, row = captures[0]
        if _capture_ineligible(row, now):
            return 'recording_ineligible', None
        blocked = _live_window_or_deleting(client, tx, collection, uid, now)
        if blocked:
            return blocked, None
        return _finish_capture(client, tx, collection, uid, cid, row, now)

    return commit(client.transaction())


def _finish_capture(
    client,
    tx,
    collection,
    uid,
    cid,
    row,
    now,
    *,
    state: Optional[str] = None,
    stamp_path: Optional[str] = None,
    stamp_request: bool = True,
):
    """Store the recording-scoped Finish on capture ``cid``; every other read is already done.

    ``state`` is the capture's native ledger state when the caller read it already. With ``stamp_path``, the
    first write this Finish stores (the cut, or the request unless ``stamp_request`` is false; never the
    consuming cut of an earlier request) carries the Finish stamp.
    """
    stamp = {FINISH_STAMP_FIELD: finish_stamp(now, stamp_path)} if stamp_path else {}
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
        state = state or _native_projection_state(client, tx, uid, cid)
        if state == 'pending' and server_batch.has_retained_audio(row):
            if not server_batch.manual_end_marker_enabled():
                return 'batch_disabled', None
            if row.get('v3_manual_end_requested') is True:
                return 'already_requested', response_row
            tx.update(
                ref,
                {'v3_manual_end_requested': True, FINISH_RECORDING_FIELD: True, **(stamp if stamp_request else {})},
            )
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
            # A consuming cut keeps the stamp of the Finish that stored the request.
            **({} if row.get('v3_manual_end_requested') is True else stamp),
        },
    )
    return ('consumed' if row.get('v3_manual_end_requested') is True else 'recording_cut'), response_row


# The card fields let a completed, visible window answer with the card it already shows.
CARD_FIELDS = ['structured', 'user_title', 'starred']
NAMED_FINISH_FIELDS = list(dict.fromkeys([*RECENT_FINISH_FIELDS, *FINISH_FIELDS, *CARD_FIELDS]))
_NAMED_OUTCOMES = {
    'cut': 'named_recording_cut',
    'recording_cut': 'named_recording_cut',
    'requested': 'named_recording_requested',
    'recording_requested': 'named_recording_requested',
}


def _is_listen_capture(row: Mapping[str, Any]) -> bool:
    return bool(
        not row.get('v3_derived')
        and row.get('source') in {'omi', 'phone'}
        and (row.get('external_data') or {}).get('recording_session_id')
    )


def _is_sealed_capture(row: Mapping[str, Any]) -> bool:
    return _is_listen_capture(row) and row.get('status') == 'completed' and row.get('recording') is True


def _window_unfit(window: Mapping[str, Any]) -> bool:
    return bool(
        not window.get('v3_derived')
        or any(window.get(key) for key in ('deleted', 'discarded', 'is_locked', 'sync_merged_into'))
        or window.get('data_protection_level') == 'private'
        or not isinstance(window.get('started_at'), datetime)
        or not isinstance(window.get('finished_at'), datetime)
    )


def _window_tail(window: Mapping[str, Any]) -> Optional[str]:
    members = window.get('v3_recording_ids') or []
    cid = members[-1] if isinstance(members, list) and members else None
    return cid if _valid_document_id(cid) else None


def _latest_capture(docs, cid, row):
    """The capture the person just finished: ``cid``, or a capture that sealed after it.

    A newer capture can feed a window that never goes live (hidden under the word floor), so the
    app still names the earlier window. ``docs`` is the newest-first recent-source scan. Returns
    ``(cid, row)`` or a decline outcome string when the newest capture cannot be told apart.
    """
    rows = [(doc.id, doc.to_dict() or {}) for doc in docs]
    captures = [
        (rid, source)
        for rid, source in rows
        # Only a sealed capture supersedes: a speech-pause rotation writes the next capture in
        # progress (stamped with a later clock) before it seals the one the person finished.
        if _is_sealed_capture(source)
        # Dropped or absorbed captures carry no speech the person could be finishing.
        and not any(source.get(key) for key in ('deleted', 'discarded', 'sync_merged_into'))
    ]
    later = [
        (rid, source)
        for rid, source in captures
        if rid != cid and isinstance(source.get('finished_at'), datetime) and source['finished_at'] > row['finished_at']
    ]
    if not later:
        # The scan is newest first. Full, and without the named capture, a newer one may lie past it.
        if len(docs) >= RECENT_FINISH_LIMIT and all(rid != cid for rid, _ in rows):
            return 'recording_lookup_capped'
        return cid, row
    newest = max(source['finished_at'] for _, source in later)
    top = [(rid, source) for rid, source in later if source['finished_at'] == newest]
    return top[0] if len(top) == 1 else 'recording_ambiguous'


def request_named_finish(
    uid: str, named_id: str, *, now: datetime, firestore_client: Any = None, strict: bool = False
) -> Tuple[str, Optional[Dict[str, Any]], str]:
    """Finish the just-sealed capture a Finish named after its window left the live set.

    The app names the window it was showing. A pendant capture that seals at a speech pause can
    end that window before the tap lands, so the name no longer resolves to a live window. The
    named id is either that window (its tail source is the capture) or the capture itself. A
    capture that sealed after it is what the person just finished, so it wins. Only a capture
    sealed within ``RECENT_FINISH_AGE`` that passes the recording-Finish checks is cut, only
    while no other window is live, and a completed window already on Home is left as it is.
    ``strict`` refuses (``named_superseded``) instead of moving to a newer capture and its window: the
    caller asked for exactly the named target. Returns ``(outcome, response row, recording id)``.
    """
    if not _valid_document_id(named_id):
        return 'named_not_finishable', None, ''
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)

    @firestore.transactional
    def commit(tx):
        def read(doc_id, fields):
            return collection.document(doc_id).get(transaction=tx, field_paths=fields).to_dict() or {}

        named = read(named_id, NAMED_FINISH_FIELDS)
        window_id, window, cid, row = None, None, named_id, named
        if named.get('v3_derived'):
            cid = _window_tail(named)
            if _window_unfit(named) or cid is None:
                return 'named_not_finishable', None, ''
            window_id, window, row = named_id, named, read(cid, RECENT_FINISH_FIELDS)
        if not _is_listen_capture(row) or not isinstance(row.get('finished_at'), datetime):
            return 'named_not_finishable', None, ''
        latest = _latest_capture(_recent_finish_sources(collection, tx, now), cid, row)
        if isinstance(latest, str):
            return latest, None, ''
        refusal = 'named_not_finishable'
        if latest[0] != cid and strict:
            return 'named_superseded', None, ''
        if latest[0] != cid:
            cid, row = latest
            refusal = 'named_superseded'
            owners = {
                claim.get('conversation_id') if isinstance(claim, dict) else None for claim in row.get('claims') or ()
            }
            window_id, window = None, None
            if owners:
                window_id = next(iter(owners)) if len(owners) == 1 else None
                window = read(window_id, NAMED_FINISH_FIELDS) if _valid_document_id(window_id) else {}
                if _window_unfit(window) or _window_tail(window) != cid:
                    return refusal, None, ''
            logger.info('v3 named Finish moved to a capture that sealed after the named one')
        if _capture_ineligible(row, now, window_id=window_id):
            return refusal, None, ''
        if window is not None and window_id and window.get('status') == 'completed' and not window.get('home_hidden'):
            # Already on Home with its notes: a cut would only regenerate them. Answer with the card.
            return 'already_visible', {**window, 'id': window_id}, cid
        blocked = _live_window_or_deleting(client, tx, collection, uid, now)
        if blocked:
            return blocked, None, ''
        if window is None or not window_id:
            outcome, response_row = _finish_capture(client, tx, collection, uid, cid, row, now)
            return _NAMED_OUTCOMES.get(outcome, outcome), response_row, cid if response_row else ''
        outcome, recording_id = _finish_window_tail(client, tx, uid, collection, window, window_id, cid, row, now)
        if not recording_id:
            return outcome, None, ''
        return _NAMED_OUTCOMES.get(outcome, outcome), _window_response(window_id, window), recording_id

    outcome, response_row, recording_id = commit(client.transaction())
    if outcome == 'already_visible' and response_row is not None:
        # The same read projection the live tile uses, after the transaction: the app replaces the
        # card it shows with this row, so title, overview and starring must match it.
        card = prepare_conversation_for_read(response_row, uid, firestore_client=client)
        if card is None:
            return 'named_not_finishable', None, ''
        response_row = {**_window_response(card['id'], card), **card}
    return outcome, response_row, recording_id


def _window_response(window_id: str, window: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        'id': window_id,
        'created_at': window.get('created_at') or window['started_at'],
        'started_at': window['started_at'],
        'finished_at': window['finished_at'],
        'v3_recording_ids': window.get('v3_recording_ids'),
        'structured': {},
    }
