"""Conversation summary persistence and content-scoped retry fences."""

from database import conversations_v3_leases as leases
from database.conversations_v3_fence import permits_native_source, wake_repairs
from utils.conversations.v3.live import FINISH_WINDOW_FIELD
from utils.conversations.v3 import metrics

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from database import conversations, conversations_v3 as store
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversation_processing_result import cleared_native_visibility
from models.finalization_owner import python_owns_finalization
from utils.conversations.v3 import Conflict, policy
from utils.conversations.summary_delivery import present
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.encryption import encrypt, decrypt

_LIVE_INPUT_SCOPE = (
    'id',
    'created_at',
    'started_at',
    'v3_recording_ids',
    'kind',
    'language',
    'uses_custom_stt',
    'source',
    'data_protection_level',
    'private_cloud_sync_enabled',
)


def _live_scope(row):
    # Older fingerprints omit this input entirely and must miss even when a
    # previously applied correction has since been removed.
    return {**{key: row.get(key) for key in _LIVE_INPUT_SCOPE}, 'user_corrections': row.get('user_corrections') or []}


def _live_summary_fingerprint(row):
    evidence = {'scope': _live_scope(row), 'speech': processing_hash(row)}
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()


def read_live_summary(uid, row, *, exact=False):
    cached = row.get(policy.LIVE_SUMMARY_FIELD)
    if not isinstance(cached, dict) or not policy.live_summary_target(row):
        return None
    count, coverage, ciphertext = cached.get('segments'), cached.get('coverage'), cached.get('ciphertext')
    if (
        type(count) is not int
        or count < 1
        or not isinstance(coverage, datetime)
        or not isinstance(ciphertext, str)
        or coverage > row['finished_at']
    ):
        return None
    segments = row.get('transcript_segments') or []
    if len(segments) < count or (exact and len(segments) != count):
        return None
    covered = {**row, 'transcript_segments': segments[:count], 'finished_at': coverage}
    recording_count = cached.get('recording_count')
    if recording_count is not None:
        recording_ids = row.get('v3_recording_ids')
        if (
            not isinstance(recording_ids, list)
            or type(recording_count) is not int
            or not 0 < recording_count <= len(recording_ids)
        ):
            return None
        covered['v3_recording_ids'] = recording_ids[:recording_count]
    if cached.get('input') != _live_summary_fingerprint(covered):
        return None
    if len(segments) > count and not _strict_live_append(covered, row):
        return None
    plaintext = decrypt(ciphertext, uid)
    if plaintext == ciphertext:
        return None
    try:
        structured = json.loads(plaintext)
    except (TypeError, ValueError):
        return None
    if not isinstance(structured, dict) or not present(structured):
        return None
    return {'structured': structured, 'summary_covers_through': coverage}


def _strict_live_append(frozen, current):
    if not current or not policy.live_summary_target(current) or current['finished_at'] <= frozen['finished_at']:
        return False
    frozen_scope, current_scope = _live_scope(frozen), _live_scope(current)
    old_ids, new_ids = frozen_scope.get('v3_recording_ids'), current_scope.get('v3_recording_ids')
    if isinstance(old_ids, list) and old_ids and isinstance(new_ids, list):
        current_scope['v3_recording_ids'] = new_ids[: len(old_ids)]
    if frozen_scope != current_scope:
        return False
    before, after = frozen.get('transcript_segments') or [], current.get('transcript_segments') or []
    if not before or len(after) <= len(before) or after[: len(before)] != before:
        return False
    ends = [segment.get('end') for segment in before]
    if any(type(end) not in (int, float) or not math.isfinite(end) for end in ends):
        return False
    boundary = max(max(ends), (frozen['finished_at'] - frozen['started_at']).total_seconds())
    for segment in after[len(before) :]:
        start, end = segment.get('start'), segment.get('end')
        if (
            type(start) not in (int, float)
            or type(end) not in (int, float)
            or not math.isfinite(start)
            or not math.isfinite(end)
            or not boundary <= start <= end
            or end <= boundary
        ):
            return False
    return True


_STALE_NATIVE_SOURCE = object()


def admit_native_summary(uid, cid, token, revision, *, firestore_client=None):
    """Check a foreground native source before paid work; persist any stale rearm."""
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'summary-' + cid)

    repairs = []

    @firestore.transactional
    def admit(tx):
        repairs.clear()
        snapshot = ref.get(transaction=tx)
        lease = held.get(transaction=tx).to_dict() or {}
        row = snapshot.to_dict() or {}
        return bool(
            snapshot.exists
            and snapshot.update_time == revision
            and python_owns_finalization(row)
            and lease.get('token') == token
            and lease.get('until')
            and lease['until'] > datetime.now(timezone.utc)
            and row.get(policy.NATIVE_MANUAL_BINDING)
            and permits_native_source(tx, client, uid, row, repairs=repairs)
        )

    result = admit(client.transaction())
    wake_repairs(uid, repairs)
    return result


def store_summary(uid, cid, token, revision, structured, covers, *, live_input=None, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref, held = store.user_conversations(client, uid).document(cid), leases.lease_ref(client, uid, 'summary-' + cid)
    live_cache = None
    patch = {}
    if live_input is not None:
        if not present(structured):
            raise Conflict('summary_empty')
        live_cache = {
            'input': _live_summary_fingerprint(live_input),
            **({'recording_count': len(live_input['v3_recording_ids'])} if live_input.get('v3_recording_ids') else {}),
            'coverage': covers,
            'segments': len(live_input['transcript_segments']),
            'ciphertext': encrypt(json.dumps(structured, default=str), uid),
        }
    else:
        patch = conversations._prepare_conversation_for_write(  # pyright: ignore[reportPrivateUsage] -- reuse the authoritative encryption codec
            {'structured': structured}, uid, 'enhanced', allow_offload=False
        )

    repairs = []

    @firestore.transactional
    def persist(tx):
        repairs.clear()
        snapshot = ref.get(transaction=tx)
        deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            raise Conflict('account_deletion')
        lease = held.get(transaction=tx).to_dict() or {}
        current = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or not python_owns_finalization(current)
            or current.get('deleted')
            or current.get('is_locked')
            or lease.get('token') != token
            or not lease.get('until')
            or lease['until'] <= datetime.now(timezone.utc)
        ):
            raise Conflict('summary_source_changed')
        if live_input is not None:
            if not policy.live_summary_target(current) or (
                snapshot.update_time != revision
                and not _strict_live_append(live_input, store.decode_row(uid, snapshot))
            ):
                raise Conflict('summary_source_changed')
            tx.update(ref, {policy.LIVE_SUMMARY_FIELD: live_cache})
            return False
        if snapshot.update_time != revision:
            raise Conflict('summary_source_changed')
        if not permits_native_source(tx, client, uid, current, repairs=repairs):
            return _STALE_NATIVE_SOURCE
        if current.get('title_locked'):
            patch['structured']['title'] = (current.get('structured') or {}).get('title', '')
            patch['structured']['emoji'] = (current.get('structured') or {}).get('emoji', '')
        # The scoped reconcile may time out while its outline is still running.
        # A successful scoped reconcile can also have locked the card before notes are written.
        # Finish either explicit Open path here while retaining any other owed processing.
        was_unlocked = current.get('v3_unlocked')
        open_lock = (
            {
                'status': 'completed',
                'v3_unlocked': False,
                'v3_open_locked': True,
                'v3_process_pending': bool(was_unlocked or current.get('v3_process_pending')),
            }
            if current.get('v3_derived')
            and (was_unlocked or (current.get('v3_open_locked') and current.get('status') == 'processing'))
            else {}
        )
        settled = current.get('v3_derived') and (bool(open_lock) or current.get('status') != 'in_progress')
        has_notes = present(structured)
        visibility_receipt = policy.native_manual_notes_receipt(current) if settled and has_notes else None
        clearing = cleared_native_visibility(current, has_notes=has_notes)
        # On-open notes are a notes write too: a row whose background notes failed and the user then
        # opened owes the same single created delivery once it is visible and completed.
        armed = bool(
            settled
            and not clearing
            and policy.created_eligible(
                {**current, **open_lock, 'v3_notes_written': True, 'v3_process_failed': False, 'tile_state': 'done'}
            )
        )
        tx.update(
            ref,
            {
                **patch,
                **open_lock,
                'summary_covers_through': covers,
                **({'tile_state': 'done', 'v3_process_failed': False, 'summary_retryable': False} if settled else {}),
                **(
                    {'title_locked': True}
                    if current.get('v3_derived') and not current.get('home_hidden') and patch['structured'].get('title')
                    else {}
                ),
                **({'v3_notes_written': True} if settled else {}),
                **({policy.NATIVE_MANUAL_NOTES_VISIBILITY: visibility_receipt} if visibility_receipt else {}),
                **({'v3_created_pending': True} if armed else {}),
                **clearing,
            },
        )
        return armed

    result = persist(client.transaction())
    wake_repairs(uid, repairs)
    if result is _STALE_NATIVE_SOURCE:
        raise Conflict('summary_source_changed')
    return result


def settle_processing(
    uid,
    cid,
    token,
    revision,
    covers,
    *,
    skipped=False,
    notes=False,
    content_hash=None,
    word_floor_outcomes: tuple[bool, bool] | None = None,
    firestore_client=None,
):
    """Settle one processing attempt; `notes` marks a completed notes write (arms the created delivery).

    A settle is not a failure, so it clears the content-scoped attempt budget: the budget counts
    consecutive failures, and a later pass on unchanged content must start from zero instead of
    inheriting attempts that already succeeded. Returns True when this settle armed the
    conversation-created delivery obligation.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'summary-' + cid)

    repairs = []

    @firestore.transactional
    def settle(tx):
        repairs.clear()
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('processing_source_changed')
        if not row or not python_owns_finalization(row):
            return False, False, None, False
        if not skipped and not row.get('deleted') and not permits_native_source(tx, client, uid, row, repairs=repairs):
            return _STALE_NATIVE_SOURCE
        if not skipped and not row.get('deleted') and row.get('sync_content_revision') != revision:
            decoded = store.decode_row(uid, snapshot)
            if not content_hash or processing_hash(decoded) != content_hash:
                raise Conflict('processing_source_changed')
        written = bool(notes and not skipped and not row.get('deleted'))
        armed = written and policy.created_eligible(
            {**row, 'v3_notes_written': True, 'v3_process_failed': False, 'v3_process_pending': False}
        )
        settled = (
            not skipped
            and not row.get('deleted')
            and row.get('status') == 'completed'
            and row.get('v3_process_pending') is True
        )
        manual_visibility = None
        if (
            settled
            and row.get('v3_derived')
            and row.get('manual_end')
            and not row.get('backfilled')
            and not row.get('discarded')
            and not row.get('v3_manual_end_home_counted')
        ):
            # Same row filters as the Home feed (database/home_feed._visible) for a derived row.
            visible = (
                not row.get('sync_merged_into')
                and not is_relevance_discarded(row)
                and conversations.is_visible_conversation(row, hide_home=True, presentation=True)
            )
            kind = row.get('kind') if row.get('kind') in metrics.MANUAL_END_KINDS else 'other'
            manual_visibility = ('visible' if visible else 'hidden', kind)
        tx.update(
            ref,
            {
                'v3_process_pending': False,
                'v3_process_attempts': 0,
                'tile_state': 'done',
                'v3_process_failed': False,
                'v3_process_failure_reason': None,
                'summary_retryable': False,
                **({'summary_covers_through': covers} if not skipped and not row.get('deleted') else {}),
                **(
                    {'title_locked': True}
                    if not skipped and not row.get('home_hidden') and (row.get('structured') or {}).get('title')
                    else {}
                ),
                **({'v3_notes_written': True} if written else {}),
                **({'v3_created_pending': True} if armed else {}),
                # First settlement only: a late rewrite re-settles the same row and must not count again.
                **({'v3_manual_end_home_counted': True} if manual_visibility is not None else {}),
            },
        )
        return armed, settled, manual_visibility, manual_visibility is not None and row.get(FINISH_WINDOW_FIELD) == cid

    result = settle(client.transaction())
    wake_repairs(uid, repairs)
    if result is _STALE_NATIVE_SOURCE:
        raise Conflict('processing_source_changed')
    armed, settled, manual_visibility, finish_settled = result
    if manual_visibility is not None:
        metrics.MANUAL_END_HOME.labels(*manual_visibility).inc()
    if finish_settled:
        metrics.FINISH_NO_POINTER.labels('settled').inc()
    if settled and word_floor_outcomes is not None:
        metrics.observe_word_floor(*word_floor_outcomes)
    return armed


CREATED_CLAIM = timedelta(minutes=5)
CREATED_MAX_ATTEMPTS = 5
CREATED_PAGE = 8


def pending_created(uid, *, firestore_client=None):
    """Owed conversation-created deliveries for one owner (collection-scoped, bounded)."""
    client = firestore_client or store.get_firestore_client()
    query = store.user_conversations(client, uid).where(filter=FieldFilter('v3_created_pending', '==', True))
    ids = []
    page = query
    while True:
        page_size = CREATED_PAGE - len(ids)
        snapshots = list(page.limit(page_size).stream())
        ids.extend(snapshot.id for snapshot in snapshots if python_owns_finalization(snapshot.to_dict() or {}))
        if len(ids) >= CREATED_PAGE or len(snapshots) < page_size:
            return ids
        # A full page including parked deliveries can hide Python work behind it.
        page = query.start_after(snapshots[-1])


def claim_created(uid, cid, *, firestore_client=None):
    """Claim one owed delivery for a bounded lease; returns the attempt number or None.

    A row that stopped qualifying (deleted, hidden, locked, discarded, already delivered) drops the
    obligation instead of delivering. A live claim held by another worker is left alone.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)

    @firestore.transactional
    def claim(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if not snapshot.exists or not python_owns_finalization(row) or not row.get('v3_created_pending'):
            return None
        now = datetime.now(timezone.utc)
        if not policy.created_eligible(row):
            tx.update(ref, {'v3_created_pending': False, 'v3_created_claim_until': None})
            return None
        if row.get('v3_created_claim_until') and row['v3_created_claim_until'] > now:
            return None
        attempt = int(row.get('v3_created_attempts') or 0) + 1
        if attempt > CREATED_MAX_ATTEMPTS + 1:
            # The final delivery attempt drops failures itself; this bounds a row whose read or
            # claim keeps failing outside the delivery so it never cycles the owner's wakes forever.
            tx.update(ref, {'v3_created_pending': False, 'v3_created_claim_until': None})
            return None
        tx.update(ref, {'v3_created_attempts': attempt, 'v3_created_claim_until': now + CREATED_CLAIM})
        return attempt

    return claim(client.transaction())


def finish_created(uid, cid, attempt, *, delivered, dropped=False, firestore_client=None):
    """Record the delivery, drop an obligation the row no longer qualifies for, or release the claim.

    Fenced by the attempt number so a superseded claimant cannot settle a successor's attempt.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)

    @firestore.transactional
    def finish(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or not python_owns_finalization(row)
            or int(row.get('v3_created_attempts') or 0) != attempt
        ):
            return False
        if delivered:
            tx.update(
                ref,
                {
                    'v3_created_pending': False,
                    'v3_created_claim_until': None,
                    'v3_created_delivered_at': datetime.now(timezone.utc),
                },
            )
        elif dropped:
            tx.update(ref, {'v3_created_pending': False, 'v3_created_claim_until': None})
        else:
            tx.update(ref, {'v3_created_claim_until': None})
        return True

    return finish(client.transaction())


def processing_hash(row):
    return hashlib.sha256(
        json.dumps(
            {
                'segments': (row or {}).get('transcript_segments') or [],
                'manual_end': bool((row or {}).get('manual_end')),
                'kind': (row or {}).get('kind') or 'conversation',
                **(
                    {policy.NATIVE_MANUAL_BINDING: row[policy.NATIVE_MANUAL_BINDING]}
                    if row and row.get(policy.NATIVE_MANUAL_BINDING)
                    else {}
                ),
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


class _Terminal:
    """Falsy outcome: the row's processing obligation is already terminally failed.

    Falsy so a caller that only asks "did this pass begin?" still stops, while the push path can
    tell a settled terminal row from an unavailable one and acknowledge it instead of raising.
    """

    def __bool__(self):
        return False


TERMINAL = _Terminal()


def begin_processing(uid, row, token, *, force=False, firestore_client=None):
    """Claim one processing pass: True when it began, TERMINAL when the row is already exhausted.

    False means the row cannot be processed right now (missing, deleted or locked). The budget
    counts consecutive attempts on one content fingerprint: `settle_processing` clears it on
    success, so only a run of failures can reach the terminal outcome.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(row['id'])
    held = leases.lease_ref(client, uid, 'summary-' + row['id'])
    fingerprint = processing_hash(row)

    repairs = []

    @firestore.transactional
    def begin(tx):
        repairs.clear()
        current = ref.get(transaction=tx).to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or lease.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(
            timezone.utc
        ):
            raise Conflict('lease_lost')
        if not current or not python_owns_finalization(current) or current.get('deleted') or current.get('is_locked'):
            return False
        if (
            policy.NATIVE_MANUAL_BINDING in row
            and row.get(policy.NATIVE_MANUAL_BINDING) != current.get(policy.NATIVE_MANUAL_BINDING)
            or not permits_native_source(tx, client, uid, current, repairs=repairs)
        ):
            return False
        attempts = (
            current.get('v3_process_attempts', 0)
            if not force and current.get('v3_process_fingerprint') == fingerprint
            else 0
        )
        if attempts >= 2:
            tx.update(ref, failure_patch(retryable=bool(row.get('transcript_segments')), reason='attempts_exhausted'))
            return 'failed' if not current.get('v3_process_failed') else 'terminal'
        tx.update(
            ref,
            {
                'v3_process_fingerprint': fingerprint,
                'v3_process_attempts': attempts + 1,
                'v3_process_failed': False,
                'v3_process_failure_reason': None,
                'summary_retryable': False,
                'tile_state': 'writing',
                'status': 'processing',
                'v3_process_pending': True,
            },
        )
        return True

    result = begin(client.transaction())
    wake_repairs(uid, repairs)
    if result == 'failed':
        metrics.terminal_failure('attempts_exhausted')
    if result in ('failed', 'terminal'):
        return TERMINAL
    return result is True


def failure_patch(*, retryable=True, reason='processing'):
    return {
        'status': 'completed',
        'tile_state': 'failed',
        'summary_retryable': retryable,
        'v3_process_pending': False,
        'v3_process_failed': True,
        'v3_process_failure_reason': reason,
    }


def fail_processing(uid, cid, token, revision, *, content_hash=None, retryable=True, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'summary-' + cid)

    repairs = []

    @firestore.transactional
    def fail(tx):
        repairs.clear()
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        if not row or not python_owns_finalization(row) or row.get('deleted'):
            return False
        if row.get('is_locked'):
            tx.update(ref, {'v3_process_pending': False, 'tile_state': 'done', 'v3_process_failed': False})
            return False
        if not permits_native_source(tx, client, uid, row, repairs=repairs):
            return _STALE_NATIVE_SOURCE
        if row.get('sync_content_revision') != revision:
            if not content_hash or processing_hash(store.decode_row(uid, snapshot)) != content_hash:
                raise Conflict('processing_source_changed')
        tx.update(ref, failure_patch(retryable=retryable))
        return not row.get('v3_process_failed')

    changed = fail(client.transaction())
    wake_repairs(uid, repairs)
    if changed is _STALE_NATIVE_SOURCE:
        raise Conflict('processing_source_changed')
    if changed:
        metrics.terminal_failure('processing')
    return changed


def settle_backfill_processing(uid, cid, *, failed, max_attempts, firestore_client=None):
    """Clear the backfill notes marker once the live processing writer settled the row.

    A raised attempt parks the row (never left on the live sweep's v3_process_pending) and retries
    on the next backfill drain; after max_attempts it fails like a live exhausted row.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)

    @firestore.transactional
    def settle(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if not snapshot.exists or not python_owns_finalization(row) or not row.get('v3_backfill_process_pending'):
            return 'absent'
        if not failed and not row.get('v3_process_pending'):
            tx.update(ref, {'v3_backfill_process_pending': False})
            # The live writers settled it: notes written, or a terminal failure (attempts exhausted).
            return 'failed' if row.get('v3_process_failed') else 'settled'
        attempts = int(row.get('v3_backfill_attempts') or 0) + 1
        if attempts >= max_attempts:
            tx.update(
                ref,
                {
                    **failure_patch(retryable=bool(row.get('transcript_segments'))),
                    'v3_backfill_process_pending': False,
                    'v3_backfill_attempts': attempts,
                },
            )
            return 'failed'
        tx.update(ref, {'v3_process_pending': False, 'v3_backfill_attempts': attempts})
        return 'retry'

    return settle(client.transaction())
