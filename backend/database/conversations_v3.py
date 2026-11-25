"""Bounded v3 reads and transaction-fenced leases/claims.

Only lifecycle calls commit_projection. Speech uses the existing conversation
codec; cached outlines are encrypted. Nothing is cleared after a lost race.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from google.api_core.exceptions import DeadlineExceeded, InvalidArgument
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import home_visibility_index
from database._client import firestore_failure_reason, get_firestore_client
from database.transcript_pointer import TranscriptBlobAbsent, TranscriptShredded
from database import conversations, conversations_v3_leases as leases
from database.conversations_v3_undo_removals import removal_ref
from database.home_feed_fields import COMMIT_STAMPED_FIELDS
from database.account_deletion_marker import account_deletion_blocks_user_work, account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from models.finalization_owner import ENGINE_FIELD, EPOCH_FIELD, python_owns_finalization
from utils.encryption import encrypt, decrypt
from utils.home_feed.projection import stamp as stamp_home_display
from config.record_wal_duplicate import has_retained_custody
from config.conversations_v3 import boundary_seconds, stretch_cohesion_enabled
from utils.conversations.v3 import Conflict, policy, preview_wakes, request_log_trace_id
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, OPEN_LOOP_EXTRACTIONS_FIELD

logger = logging.getLogger(__name__)

LIMIT = 128


# The live closure's derived rows. A pending recording's own claimants are all needed (a replan of the
# recording must see every row that owns its lines), and one long recording can own hundreds of short
# windows, so the bound is on rows and on their stored speech rather than a small row count.
# Both are env-tunable without a code change (an env edit rolls a new revision);
# CONVERSATIONS_V3_CLOSURE_BY_CLAIMS=off restores the time query around every loaded recording (the closure
# before claims-driven loading). Sources are bounded too: every commit batch rewrites each loaded source, and
# a transaction writes at most 500 documents.
def _env_int(name, default):
    try:
        value = int(os.getenv(name, ''))
    except ValueError:
        return default
    return value if value > 0 else default


DERIVED_LIMIT = _env_int('CONVERSATIONS_V3_DERIVED_LIMIT', 1024)
DERIVED_BYTES = _env_int('CONVERSATIONS_V3_DERIVED_BYTES', 16 * 1024 * 1024)
SOURCE_LIMIT = _env_int('CONVERSATIONS_V3_SOURCE_LIMIT', 400)
CLAIM_READ_CHUNK = 100


def closure_by_claims():
    return os.getenv('CONVERSATIONS_V3_CLOSURE_BY_CLAIMS', 'on').strip().lower() != 'off'


# The backfill holds its own builder lease (and outline cache) so a running backfill never makes the
# owner's live builder busy; the two passes touch disjoint documents and both are revision-fenced.
BACKFILL_LEASE = 'backfill-builder'


def user_conversations(client, uid):
    return client.collection('users').document(uid).collection('conversations')


def merge_donors_have_tasks(uid, donor_ids, *, firestore_client=None, transaction=None):
    """Preserve standalone task links by checking the donor IDs without loading item content."""
    client = firestore_client or get_firestore_client()
    tasks = client.collection('users').document(uid).collection('action_items')
    donors = sorted(set(donor_ids))
    # Firestore allows up to 30 disjuncts in one in-filter.
    for start in range(0, len(donors), 30):
        query = (
            tasks.where(filter=FieldFilter('conversation_id', 'in', donors[start : start + 30]))
            .select(('conversation_id',))
            .limit(1)
        )
        matches = query.stream() if transaction is None else query.stream(transaction=transaction)
        if next(iter(matches), None) is not None:
            return True
    return False


def decode_row(uid, snapshot, *, data=None) -> dict[str, Any] | None:
    data = (snapshot.to_dict() or {}) if data is None else data
    if not snapshot.exists:
        return None
    data.setdefault('id', snapshot.id)
    segments = conversations.decode_transcript_segments_verified(
        uid, data.get('transcript_segments') or [], bool(data.get('transcript_segments_compressed'))
    )
    data = conversations.prepare_conversation_for_read(data, uid)
    if data is None:
        raise Conflict('recording_decode_unavailable')
    # The strict decode only proves the stored transcript is readable. Projection reads the hydrated
    # segments, which carry manual speaker corrections and the recurring-voice privacy filter.
    if not isinstance(data.get('transcript_segments'), list):
        data['transcript_segments'] = segments
    data['_v3_revision'] = snapshot.update_time
    return data


# A source recording whose revision moved during a pass may still be committed against when only its
# speech moved (appended segments, audio files, status, pending/manual-end markers). Any change to
# these fields (deletion, merge, privacy, lock, claims, identity) keeps the strict source_changed fence.
SOURCE_FENCE_FIELDS = (
    'recording',
    'deleted',
    'deleted_spans',
    'sync_merged_into',
    'data_protection_level',
    'is_locked',
    'started_at',
    'claims',
    'v3_derived',
)


def source_fence(raw):
    return {key: (raw or {}).get(key) for key in SOURCE_FENCE_FIELDS}


def recording_input(uid, snapshot):
    if not snapshot.exists:
        return None
    raw = snapshot.to_dict() or {}
    if raw.get('data_protection_level') != 'private' and raw.get('started_at'):
        try:
            row = decode_row(uid, snapshot)
        except (ValueError, TypeError, FileNotFoundError, TranscriptBlobAbsent, TranscriptShredded, Conflict):
            row = None
        if row is not None:
            row['_v3_fence'] = source_fence(raw)
            return row
    return {
        **raw,
        'id': snapshot.id,
        '_v3_revision': snapshot.update_time,
        '_v3_unreadable': True,
        '_v3_fence': source_fence(raw),
    }


def speech_moved(recording, current):
    """True when a loaded source recording changed only by receiving more speech."""
    fence = recording.get('_v3_fence')
    return bool(
        fence is not None
        and current
        and not recording.get('_v3_derive')
        # A live re-derive replans sealed sources only; any change during its pass is a conflict.
        and not recording.get('_v3_rederive_live')
        and not recording.get('deleted')
        and not recording.get('sync_merged_into')
        and current.get('recording')
        and source_fence(current) == fence
    )


def speech_end(row):
    """Late text on a completed recording appends segments without moving finished_at."""
    end = row.get('finished_at') or row['started_at']
    for segment in row.get('transcript_segments') or []:
        try:
            end = max(end, row['started_at'] + timedelta(seconds=float(segment.get('end') or 0)))
        except (TypeError, ValueError):
            continue
    return end


def adoptable(uid, ids, *, firestore_client=None):
    """Derived rows that already own a planned id but were outside the loaded closure.

    Only live derived rows qualify: a deleted or tombstoned target keeps raising, so a rebuild can
    never resurrect a window the user deleted.
    """
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    found = {}
    for cid in ids:
        snapshot = coll.document(cid).get()
        raw = snapshot.to_dict() or {} if snapshot.exists else {}
        if not raw.get('v3_derived') or raw.get('deleted') or raw.get('recording'):
            continue
        tombstone = client.collection('users').document(uid).collection('deleted_conversations').document(cid).get()
        if tombstone.exists:
            continue
        row = decode_row(uid, snapshot)
        if row:
            found[cid] = row
    return found


def save_outline(uid, token, fingerprint, entries, *, key='builder', preview=None, firestore_client=None):
    """Keep a paid outline even when this pass's projection commit later conflicts."""
    client = firestore_client or get_firestore_client()
    ref = leases.lease_ref(client, uid, key)

    @firestore.transactional
    def save(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or row.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(
            timezone.utc
        ):
            raise Conflict('lease_lost')
        cache = json.loads(decrypt(row['outline_cache'], uid)) if row.get('outline_cache') else []
        cache = [c for c in cache if c.get('fingerprint') != fingerprint]
        cache.append({'fingerprint': fingerprint, 'entries': entries, **(preview or {})})
        tx.update(ref, {'outline_cache': encrypt(json.dumps(cache[-128:], default=str), uid)})

    save(client.transaction())


BLOCKED_BACKOFF_MAX = timedelta(hours=1)


def record_blocked(uid, token, reason, *, firestore_client=None):
    """Deterministic conflicts back off per owner instead of retrying through the shared queue.

    Fenced by the builder token: a stale pass must not park an owner after a successor committed.
    """
    client = firestore_client or get_firestore_client()
    ref = leases.lease_ref(client, uid, 'builder')

    @firestore.transactional
    def park(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        now = datetime.now(timezone.utc)
        if row.get('token') != token or row.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= now:
            return False
        count = int(row.get('v3_blocked_count') or 0) + 1
        delay = min(BLOCKED_BACKOFF_MAX, timedelta(minutes=5) * (2 ** min(count - 1, 6)))
        tx.update(ref, {'v3_blocked_count': count, 'v3_blocked_reason': reason, 'v3_backoff_until': now + delay})
        return True

    return park(client.transaction())


def backoff_until(uid, *, firestore_client=None):
    return backoff_state(uid, firestore_client=firestore_client)[0]


def backoff_state(uid, *, firestore_client=None):
    """(v3_backoff_until, v3_blocked_reason) from the owner's builder lease doc."""
    client = firestore_client or get_firestore_client()
    row = leases.lease_ref(client, uid, 'builder').get().to_dict() or {}
    return row.get('v3_backoff_until'), row.get('v3_blocked_reason')


def load(uid, *, conversation_id=None, firestore_client=None):
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid):
        raise Conflict('account_deletion')
    coll = user_conversations(client, uid)
    silence_gap = timedelta(seconds=boundary_seconds(cohesion=stretch_cohesion_enabled())[0])
    margin = max(timedelta(minutes=20), silence_gap)
    opened = decode_row(uid, coll.document(conversation_id).get()) if conversation_id else None
    if conversation_id:
        ids = (opened or {}).get('v3_recording_ids') or []
        pending = [coll.document(rid).get() for rid in ids]
    else:
        pending = list(
            coll.where(filter=FieldFilter('v3_pending', '==', True)).order_by('v3_pending_since').limit(33).stream()
        )
    pending = pending[:32] if not conversation_id else pending
    recordings, unreadable = {}, {}
    for doc in pending:
        row = recording_input(uid, doc)
        if row and row.get('_v3_unreadable'):
            unreadable[doc.id] = row
        elif row:
            recordings[doc.id] = row
    if recordings and not conversation_id:
        # Pending obligation order is not capture order (late sync can be older).
        latest = max(recordings.values(), key=lambda r: r['started_at'])
        following = next(
            (
                doc
                for doc in coll.where(filter=FieldFilter('v3_pending', '==', True))
                .where(filter=FieldFilter('started_at', '>=', latest['started_at']))
                .order_by('started_at')
                .limit(33)
                .stream()
                if doc.id not in recordings
            ),
            None,
        )
        if following and latest.get('finished_at'):
            next_start = (following.to_dict() or {}).get('started_at')
            if next_start and next_start - latest['finished_at'] < silence_gap:
                latest['_v3_page_continues'] = True
    state = leases.lease_ref(client, uid, 'builder').get().to_dict() or {}
    cache = json.loads(decrypt(state['outline_cache'], uid)) if state.get('outline_cache') else []
    if not recordings and not state.get('open_id') and not state.get('unlocked_ids') and not opened:
        return unreadable, {}, cache
    existing = {}
    if opened:
        existing[opened['id']] = opened
    elif state.get('open_id') and not conversation_id:
        opened = decode_row(uid, coll.document(state['open_id']).get())
        if opened:
            existing[opened['id']] = opened
    queried = set()
    by_claims = closure_by_claims()
    loaded_bytes = sum(_encoded_bytes(row.get('transcript_segments') or []) for row in existing.values())

    def add(row):
        # Checked per document, so an overflowing closure stops reading and decoding at the bound.
        nonlocal loaded_bytes
        previous = existing.get(row['id'])
        loaded_bytes += _encoded_bytes(row.get('transcript_segments') or [])
        if previous is not None:
            loaded_bytes -= _encoded_bytes(previous.get('transcript_segments') or [])
        existing[row['id']] = row
        if len(existing) > DERIVED_LIMIT or loaded_bytes > DERIVED_BYTES:
            raise Conflict('v3_derived_budget')

    if not conversation_id:
        unlocked_ids = set(state.get('unlocked_ids') or ()) - existing.keys()
        if len(unlocked_ids) > DERIVED_LIMIT:
            raise Conflict('v3_derived_budget')
        ordered_unlocked = sorted(unlocked_ids)
        for start in range(0, len(ordered_unlocked), CLAIM_READ_CHUNK):
            ids = ordered_unlocked[start : start + CLAIM_READ_CHUNK]
            for snapshot in client.get_all([coll.document(cid) for cid in ids]):
                raw = snapshot.to_dict() or {} if snapshot.exists else {}
                if not raw.get('v3_unlocked') or raw.get('deleted'):
                    continue
                try:
                    row = decode_row(uid, snapshot)
                except (TranscriptBlobAbsent, TranscriptShredded) as error:
                    # Keep the published owner in place when its transcript is unavailable.
                    raise Conflict('recording_decode_unavailable') from error
                if row:
                    add(row)

    missing = set()
    # Follow linked recordings until the closure converges. Each round adds at least one recording and
    # derived rows stay bounded by DERIVED_LIMIT; a fixed hop depth failed the same owner on every retry.
    for _round in range(LIMIT + 1):
        ids = {rid for row in existing.values() for rid in row.get('v3_recording_ids') or []}
        ids.update(
            p['recording_id']
            for row in existing.values()
            for p in row.get('recording_pieces') or []
            if p['recording_id'] != row['id']
        )
        unseen = ids - recordings.keys() - unreadable.keys() - missing
        # Every source read counts, missing ones included, and the bound is checked before reading.
        if len(recordings) + len(unreadable) + len(missing) + len(unseen) > SOURCE_LIMIT:
            raise Conflict('v3_source_closure_budget')
        for rid in unseen:
            row = recording_input(uid, coll.document(rid).get())
            if not row:
                missing.add(rid)
            elif row.get('_v3_unreadable'):
                unreadable[rid] = row
            else:
                recordings[rid] = row
        fresh = [r for rid, r in recordings.items() if rid not in queried and r and r.get('started_at')]
        if not fresh:
            break
        # Every row a loaded recording's claims name owns some of its lines: load those exactly, by id.
        claimed: set[str] = set()
        for r in fresh if by_claims else ():
            for c in r.get('claims') or []:
                cid = c.get('conversation_id') if isinstance(c, dict) else None
                if isinstance(cid, str) and cid not in existing:
                    claimed.add(cid)
        # Refuse before reading when the ids alone overflow, and read in chunks so a byte overflow stops early.
        if len(existing) + len(claimed) > DERIVED_LIMIT:
            raise Conflict('v3_derived_budget')
        ordered = sorted(claimed)
        for start in range(0, len(ordered), CLAIM_READ_CHUNK):
            chunk = ordered[start : start + CLAIM_READ_CHUNK]
            for snapshot in client.get_all([coll.document(cid) for cid in chunk]):
                raw = snapshot.to_dict() or {} if snapshot.exists else {}
                if raw.get('v3_derived'):
                    row = decode_row(uid, snapshot)
                    if row:
                        add(row)
        # Only a recording that can still be replanned needs its neighbours by time: a pending one (new
        # speech), one an open window holds, or one with speech and no claims. A settled recording's lines
        # all belong to the rows its claims name; a time query around it chained through the owner's whole
        # contiguous history and parked heavy owners on v3_derived_budget.
        open_sources = {
            rid
            for row in existing.values()
            if row.get('status') == 'in_progress' or row.get('v3_unlocked')
            for rid in row.get('v3_recording_ids') or []
        }
        # Query disjoint affected source windows separately: historical sync must
        # not scan every conversation between its recorded day and today's live row.
        intervals = []
        for row in sorted(fresh, key=lambda r: r['started_at']):
            settled = row.get('claims') or not row.get('transcript_segments')
            if by_claims and settled and not row.get('v3_pending') and row['id'] not in open_sources:
                continue
            left = row['started_at'] - margin
            right = min(speech_end(row), datetime.now(timezone.utc) + timedelta(minutes=5)) + margin
            if intervals and left <= intervals[-1][1]:
                intervals[-1] = (intervals[-1][0], max(intervals[-1][1], right))
            else:
                intervals.append((left, right))
        for left, right in intervals:
            snapshots = (
                coll.where(filter=FieldFilter('v3_derived', '==', True))
                .where(filter=FieldFilter('finished_at', '>=', left))
                .where(filter=FieldFilter('started_at', '<=', right))
                .limit(DERIVED_LIMIT + 1)
                .stream()
            )
            for count, doc in enumerate(snapshots, 1):
                if count > DERIVED_LIMIT:
                    raise Conflict('v3_derived_budget')
                row = decode_row(uid, doc)
                if row:
                    add(row)
        queried.update(row['id'] for row in fresh)
    else:
        raise Conflict('v3_source_closure_budget')
    preview_sources = {
        rid
        for row in existing.values()
        if row.get('v3_unlocked') and not row.get('deleted')
        for rid in row.get('v3_recording_ids') or ()
    }
    for rid in preview_sources & unreadable.keys():
        # Fail closed when an otherwise eligible source temporarily cannot be
        # decoded. Replanning without it could clear the preview's index and wake.
        if policy.builder_eligible({**unreadable[rid], '_v3_unreadable': False}):
            raise Conflict('recording_decode_unavailable')
    _mark_successor_pending(coll, recordings)
    return {**recordings, **unreadable}, existing, cache


def _mark_successor_pending(coll, recordings):
    """Keep the latest stretch open while the recording after a rotation is captured or transcribed.

    Batch recordings get no transcript until they seal. Only a recording that listen rotation
    sealed carries the cap stamp; every other stretch keeps the plain five-minute rule.
    """
    spoken = [r for r in recordings.values() if r.get('transcript_segments') and r.get('started_at')]
    if not spoken:
        return
    latest = max(spoken, key=speech_end)
    cap = latest.get(policy.ROTATION_CAP_FIELD)
    if latest.get('_v3_page_continues') or type(cap) not in (int, float) or not 0 < cap <= 3600:
        return
    silence_gap = timedelta(seconds=boundary_seconds(cohesion=stretch_cohesion_enabled())[0])
    end, now = speech_end(latest), datetime.now(timezone.utc)
    query = (
        coll.where(filter=FieldFilter('started_at', '>', latest['started_at']))
        .order_by('started_at')
        .select(SUCCESSOR_FIELDS)
    )
    for doc in query.limit(8).stream():
        raw = doc.to_dict() or {}
        start = raw.get('started_at')
        if not start or start - end >= silence_gap:
            return
        if (
            doc.id != latest['id']
            and raw.get('recording') is True
            and not raw.get('deleted')
            and not raw.get('sync_merged_into')
            and raw.get('data_protection_level') != 'private'
            and policy.awaiting_transcript(raw, now, cap)
        ):
            latest['_v3_page_continues'] = True
            return


SUCCESSOR_FIELDS = [
    'started_at',
    'created_at',
    'finished_at',
    'status',
    'recording',
    'deleted',
    'sync_merged_into',
    'data_protection_level',
]


def unique_claims(claims):
    """Identical claims (same conversation, same span) are one claim; order of first appearance is kept."""
    return list({(c.get('conversation_id'), c.get('start'), c.get('end')): c for c in claims}.values())


# Firestore's per-document limit is 1 MiB ("... exceeds the maximum allowed size"); a commit request is
# separately capped ("Request payload size exceeds the limit: N bytes").
DOCUMENT_TOO_LARGE = 'exceeds the maximum allowed size'
REQUEST_TOO_LARGE = 'Request payload size exceeds the limit'
# Derived-row bytes per transaction, and every write in it (rows, source claim updates, lease): batches
# split on whichever fills first, so the source rewrites each batch repeats count against the request.
BATCH_ROW_BYTES = 2 * 1024 * 1024
BATCH_WRITE_BYTES = 8 * 1024 * 1024
# Documents one transaction writes: its rows, every loaded source's claim update and the lease. Kept under
# Firestore's 500-write commit cap now that a closure can hold hundreds of short windows.
BATCH_MAX_WRITES = 450


def size_error(error):
    """'document' or 'request' when a Firestore InvalidArgument is a size limit, else None."""
    text = str(error)
    if DOCUMENT_TOO_LARGE in text:
        return 'document'
    if REQUEST_TOO_LARGE in text:
        return 'request'
    return None


def fixed_write_bytes(recordings, rows, encrypted_cache):
    """Estimated bytes every batch writes besides its rows: each source's claim update and the lease."""
    total = _encoded_bytes(encrypted_cache)
    for rid, recording in recordings.items():
        spans = sum(
            len(row.get('_v3_claims', {}).get(rid) or [None]) for row in rows if rid in row.get('v3_recording_ids', [])
        )
        claims = unique_claims(recording.get('claims') or [])
        total += _encoded_bytes(claims) + spans * 120 + 200
        if recording.get('_v3_derive'):
            total += _encoded_bytes(backfill_conversion(recording))
    return total


def _encoded_bytes(value):
    return len(json.dumps(value, default=str).encode())


def log_largest_write(staged, *, batch, batches):
    """Name the largest document the failed transaction staged: kind and estimated bytes, never ids or content."""
    sizes: list[tuple[str, int, int | None]] = [
        ('derived_row', _encoded_bytes(row), None) for row in staged.get('rows') or []
    ]
    for current, update in (staged.get('recordings') or {}).values():
        merged = {**current, **update}
        sizes.append(('recording', _encoded_bytes(merged), len(merged.get('claims') or [])))
    if staged.get('lease') is not None:
        sizes.append(('builder_lease', _encoded_bytes({**staged['lease'][0], **staged['lease'][1]}), None))
    if not sizes:
        return
    kind, size, claims = max(sizes, key=lambda item: item[1])
    logger.warning(
        'v3 projection write too large kind=%s bytes=%d claims=%s batch=%d batches=%d staged_total_bytes=%d',
        kind,
        size,
        claims if claims is not None else '-',
        batch,
        batches,
        sum(item[1] for item in sizes),
    )


def mark_pending(uid, cid, *, manual_end=False, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = user_conversations(client, uid).document(cid)

    @firestore.transactional
    def mark(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if not row.get('recording') or row.get('deleted'):
            return False
        # The landing time (SPEECH_LANDED_FIELD) is stamped by the transaction that commits the speech,
        # not here: a reconcile can run between that commit and this re-arm.
        update = {'v3_pending': True, 'v3_pending_since': row.get('v3_pending_since') or datetime.now(timezone.utc)}
        if manual_end:
            update['v3_manual_end'] = True
        tx.update(ref, update)
        return True

    return mark(client.transaction())


def promote_manual_end(uid, cid, *, firestore_client=None):
    """Turn a stored manual-end request into the cut. True when this call wrote it.

    Called once the whole recording will land as one transcript. It does not mark the recording
    pending when no speech has landed: the transcript write that follows owns that wake, so a
    recording with no speech costs no reconcile.
    """
    client = firestore_client or get_firestore_client()
    ref = user_conversations(client, uid).document(cid)

    @firestore.transactional
    def promote(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if (
            not row.get('recording')
            or not row.get('v3_manual_end_requested')
            # The cut is materialised from finished_at; without it the marker would be inert.
            or not row.get('finished_at')
            or row.get('v3_manual_end')
            or row.get('deleted')
            or row.get('discarded')
        ):
            return False
        update: dict[str, Any] = {'v3_manual_end': True}
        if row.get('v3_speech_landed_at') is not None:
            # Speech already landed, so its reconcile may have run without the cut. Leave the
            # recording pending: the sweep re-enqueues an owner whose pending is older than ten minutes.
            update.update(v3_pending=True, v3_pending_since=row.get('v3_pending_since') or datetime.now(timezone.utc))
        tx.update(ref, update)
        return True

    return promote(client.transaction())


def _projection_snapshots(client, coll, tx, ids, *, batch_reads):
    if not batch_reads:
        for cid in ids:
            yield cid, coll.document(cid).get(transaction=tx)
        return
    for start in range(0, len(ids), CLAIM_READ_CHUNK):
        chunk = ids[start : start + CLAIM_READ_CHUNK]
        # BatchGet can return snapshots out of order, including missing documents.
        snapshots = {
            snapshot.reference.id: snapshot
            for snapshot in client.get_all([coll.document(cid) for cid in chunk], transaction=tx)
        }
        for cid in chunk:
            yield cid, snapshots[cid]


def commit_projection(
    uid,
    token,
    recordings,
    existing,
    rows,
    cache,
    *,
    clear_pending=True,
    remove=(),
    retire=None,
    key='builder',
    firestore_client=None,
):
    """Commit derived rows and source claims; returns the ids of source recordings that kept moving.

    ``retire`` (live re-derive only) maps a row id to the soft-retirement patch the final batch applies:
    its claims leave every loaded recording with the same commit that writes the rows absorbing them.

    A recording that only received more speech during the pass does not fail the commit (a live
    wearer would otherwise starve every pass): the windows planned from the loaded snapshot commit,
    its claims merge onto the re-read document and it stays v3_pending so the next pass reads the
    new speech. Derived rows and any other source change keep the strict source_changed fence.
    """
    client = firestore_client or get_firestore_client()
    retire = dict(retire or {})
    moved = set()
    coll = user_conversations(client, uid)
    held = leases.lease_ref(client, uid, key)
    open_ids = [r['id'] for r in rows if r['status'] == 'in_progress' and not r.get('deleted')]
    if len(open_ids) > 1:
        raise Conflict('multiple_open_conversations')
    planned_unlocked = {r['id'] for r in rows if r.get('v3_unlocked') and not r.get('deleted')}
    deferred_wakes = preview_wakes(rows, recordings) if key == 'builder' else {}
    # One merge per pass, with all donor redirects in the survivor's batch.
    all_absorbed = [cid for row in rows for cid in row.get('_v3_absorbed', ())]
    absorption_writes = 2 * len(all_absorbed)  # Redirect and task-link marker per donor.
    if all_absorbed:
        if len(recordings) + absorption_writes + 2 > BATCH_MAX_WRITES:
            raise Conflict('request_too_large')
        planned_ids = {row['id'] for row in rows}
        if (
            key != 'builder'
            or remove
            or not set(all_absorbed) <= existing.keys() - planned_ids
            or len(all_absorbed) != len(set(all_absorbed))
        ):
            raise Conflict('source_changed')
    retired = {cid for cid, patch in retire.items() if patch.get('sync_merged_into')}
    failure_transitions = {
        r['id']: r.get('v3_process_failed') and not (existing.get(r['id']) or {}).get('v3_process_failed') for r in rows
    }
    prepared = []
    for row in rows:
        clean = {k: v for k, v in row.items() if not k.startswith('_v3_') and k != 'updated_at'}
        # A prior row carries its stored open-loop extractions as the protected blob (the read
        # path never decodes them); the codec accepts only the decoded object.
        blob = clean.pop(OPEN_LOOP_EXTRACTIONS_FIELD, None)
        marker = clean.pop(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, None)
        level = clean.get('data_protection_level') or 'standard'
        encoded = conversations._prepare_conversation_for_write(  # pyright: ignore[reportPrivateUsage] -- reuse the authoritative encryption codec
            clean, uid, level, allow_offload=True
        )
        if blob:
            prior_level = (existing.get(row['id']) or {}).get('data_protection_level') or 'standard'
            if marker and prior_level == level:
                encoded[OPEN_LOOP_EXTRACTIONS_FIELD] = blob
                encoded[OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD] = marker
            else:
                retained = conversations.decode_open_loop_extractions(uid, blob, bool(marker))
                encoded.update(
                    conversations._prepare_conversation_for_write(  # pyright: ignore[reportPrivateUsage]
                        {OPEN_LOOP_EXTRACTIONS_FIELD: retained}, uid, level
                    )
                )
        prepared.append(home_visibility_index.stamp(encoded))
    encrypted_cache = encrypt(json.dumps(cache, default=str), uid)
    batch_reads = os.getenv('CONVERSATIONS_V3_BATCH_COMMIT_READS', 'on').strip().lower() != 'off'
    # What the current transaction attempt writes, kept by reference and sized only after a failure.
    staged = {}

    @firestore.transactional
    def commit(tx, batch_rows, batch_prepared, final):
        observed = {}
        staged.clear()
        staged.update(
            rows=[row for raw, row in zip(batch_rows, batch_prepared) if not raw.get('deleted')], recordings={}
        )
        now = datetime.now(timezone.utc)
        lease = held.get(transaction=tx).to_dict() or {}
        deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            raise Conflict('account_deletion')
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= now:
            raise Conflict('lease_lost')
        # Firestore requires every read before every write, including tombstones.
        inputs = {**recordings, **existing}
        for rid, snapshot in _projection_snapshots(client, coll, tx, list(inputs), batch_reads=batch_reads):
            row = inputs[rid]
            current = snapshot.to_dict() or {} if snapshot.exists else None
            if not snapshot.exists or snapshot.update_time != row['_v3_revision']:
                if rid in existing or rid not in recordings or not speech_moved(row, current):
                    raise Conflict('source_changed')
                moved.add(rid)
            observed[rid] = current or {}
        absorbed = {cid: row['id'] for row in batch_rows for cid in row.get('_v3_absorbed', ())}
        touched = {*(row['id'] for row in batch_rows), *absorbed}
        if final:
            touched.update((*retire, *remove))
        if any(has_retained_custody(observed.get(cid)) for cid in touched):
            raise Conflict('source_changed')
        if absorbed and merge_donors_have_tasks(uid, absorbed, firestore_client=client, transaction=tx):
            raise Conflict('source_changed')
        if retired and merge_donors_have_tasks(uid, retired, firestore_client=client, transaction=tx):
            raise Conflict('rederive_live_donor_tasks')
        for cid in [*(row['id'] for row in batch_rows), *absorbed, *(retire if final else ())]:
            tombstone = (
                client.collection('users')
                .document(uid)
                .collection('deleted_conversations')
                .document(cid)
                .get(transaction=tx)
            )
            if tombstone.exists:
                raise Conflict('target_deleted')
        new_ids = {r['id'] for r in batch_rows} - existing.keys()
        for cid in new_ids:
            if coll.document(cid).get(transaction=tx).exists:
                raise Conflict('target_exists')
        if final:
            for cid in remove:
                # Only a backfill re-derive retires a copy, and only its own backfilled rows.
                if not (existing.get(cid) or {}).get('backfilled'):
                    raise Conflict('remove_not_backfilled')
        from database.recurring_voice_privacy import filter_processing_write

        user = client.collection('users').document(uid)
        for row in batch_prepared:
            filter_processing_write(tx, user, row)
        for raw, row in zip(batch_rows, batch_prepared):
            if raw.get('deleted'):
                continue
            if final and row['id'] in retire:
                # A live re-derive survivor's bridge list lands with the bridges it names.
                row = {**row, **retire[row['id']]}
            tx.set(coll.document(row['id']), row)
        for cid, survivor in absorbed.items():
            tx.update(
                coll.document(cid),
                {
                    'deleted': True,
                    'discarded': True,
                    'home_hidden': True,
                    home_visibility_index.FIELD: False,
                    'summary_due_at': None,
                    'sync_merged_into': survivor,
                    'v3_claims_transferred_to': survivor,
                    'v3_refined': True,
                    'sync_content_revision': int(existing[cid].get('sync_content_revision') or 0) + 1,
                },
            )
            tx.set(removal_ref(user, cid), {'absorbed_by_refinement': True})
        if final:
            for cid in remove:
                tx.delete(coll.document(cid))
            written = {r['id'] for r in batch_rows}
            for cid, patch in retire.items():
                if cid not in written:
                    tx.update(coll.document(cid), patch)
                if cid in retired:
                    tx.set(removal_ref(user, cid), {'retired_by_repair': True})
        replaced = {r['id'] for r in batch_rows} | set(absorbed) | (set(remove) | retired if final else set())
        for rid, recording in recordings.items():
            if recording.get('deleted') or recording.get('sync_merged_into'):
                tx.update(coll.document(rid), {'v3_pending': False, 'v3_pending_since': None})
                continue
            if rid in moved:
                # Merge onto the re-read document; never write the stale snapshot's view of a live source.
                claims = [c for c in observed[rid].get('claims') or [] if c['conversation_id'] not in replaced]
                for row in batch_rows:
                    if rid not in row.get('v3_recording_ids', []) or row.get('deleted'):
                        continue
                    spans = row.get('_v3_claims', {}).get(
                        rid, [{'start': row['started_at'], 'end': row['finished_at']}]
                    )
                    claims.extend({'conversation_id': row['id'], **span} for span in spans)
                # The new speech is still owed to the next pass; leave purge decisions to that pass.
                update = {
                    'claims': unique_claims(claims),
                    'v3_pending': True,
                    'v3_pending_since': observed[rid].get('v3_pending_since')
                    or recording.get('v3_pending_since')
                    or datetime.now(timezone.utc),
                }
                staged['recordings'][rid] = (observed[rid], update)
                tx.update(coll.document(rid), update)
                continue
            claims = [c for c in recording.get('claims') or [] if c['conversation_id'] not in replaced]
            for row in batch_rows:
                if rid not in row.get('v3_recording_ids', []) or row.get('deleted'):
                    continue
                spans = row.get('_v3_claims', {}).get(rid, [{'start': row['started_at'], 'end': row['finished_at']}])
                claims.extend({'conversation_id': row['id'], **span} for span in spans)
            # Identical copies (left by an earlier duplicate plan) collapse, so a bloated source shrinks
            # on its next commit instead of failing every pass at the document limit.
            claims = unique_claims(claims)
            wake_at = deferred_wakes.get(rid) if final or not clear_pending else None
            existing_pending_at = recording.get('v3_pending_since')
            if not clear_pending and wake_at is not None and recording.get('v3_pending'):
                wake_at = min(wake_at, existing_pending_at or wake_at)
            update = {
                'claims': claims,
                # A backfill conversion hides its donor as a recording in the first batch; until the
                # final batch commits, it keeps a durable obligation so an interrupted run is rebuilt
                # by the ordinary builder (backfill's loader skips recordings).
                'v3_pending': (
                    rid in deferred_wakes
                    if final and clear_pending
                    else bool(wake_at or recording.get('v3_pending') or (recording.get('_v3_derive') and not final))
                ),
                'v3_pending_since': (
                    wake_at
                    if final and clear_pending
                    else wake_at
                    or existing_pending_at
                    or (datetime.now(timezone.utc) if recording.get('_v3_derive') and not final else None)
                ),
                'v3_audio_purge_pending': bool(recording.get('deleted_spans'))
                and final
                and clear_pending
                and not claims
                and not recording.get('_v3_derive')
                and not recording.get('v3_backfill_run')
                and recording.get('status') == 'completed',
                **(backfill_conversion(recording) if recording.get('_v3_derive') else {}),
            }
            if recording.get('_v3_rederive_live'):
                # A live re-derive loads only settled sources (never pending) and changes nothing but their
                # claims: it never arms or cancels an audio purge, so undo can restore every row it touched.
                update = {'claims': claims}
            staged['recordings'][rid] = (observed.get(rid) or {}, update)
            tx.update(coll.document(rid), update)
        lease_update = {
            **({'v3_blocked_count': 0, 'v3_backoff_until': None, 'v3_blocked_reason': None} if final else {}),
            'outline_cache': encrypted_cache,
            'open_id': (
                open_ids[0] if open_ids else (lease.get('open_id') if lease.get('open_id') not in existing else None)
            ),
        }
        unlocked = {r['id'] for r in batch_rows if r.get('v3_unlocked') and not r.get('deleted')}
        if unlocked or lease.get('unlocked_ids'):
            previous_unlocked = set(lease.get('unlocked_ids') or ()) - {r['id'] for r in batch_rows}
            if key == 'builder' and clear_pending and final:
                # A full pass plans every eligible indexed preview. Missing,
                # settled or ineligible sources no longer owe a timer.
                lease_update['unlocked_ids'] = sorted(planned_unlocked)
            else:
                lease_update['unlocked_ids'] = sorted(previous_unlocked | unlocked)
        staged['lease'] = (lease, lease_update)
        tx.update(held, lease_update)
        return observed

    fixed = fixed_write_bytes(recordings, rows, encrypted_cache)
    # Reserve space for all donor writes, including the task-link fences in the survivor's batch.
    fixed_writes = len(recordings) + len(remove) + absorption_writes + len(retire) + len(retired) + 1
    if retired and fixed_writes + bool(rows) > BATCH_MAX_WRITES:
        raise Conflict('backfill_partition_budget')
    max_rows = max(1, BATCH_MAX_WRITES - fixed_writes)
    batches, current, size = [], [], 0
    for raw, encoded in zip(rows, prepared):
        amount = len(json.dumps(encoded, default=str).encode())
        if current and (
            size + amount > BATCH_ROW_BYTES or fixed + size + amount > BATCH_WRITE_BYTES or len(current) >= max_rows
        ):
            batches.append(current)
            current, size = [], 0
        current.append((raw, encoded))
        size += amount
    if current or not batches:
        batches.append(current)
    for index, batch in enumerate(batches):
        try:
            observed = commit(
                client.transaction(), [r for r, _ in batch], [r for _, r in batch], index == len(batches) - 1
            )
        except Conflict:
            raise
        except Exception as error:
            if isinstance(error, InvalidArgument) and size_error(error):
                log_largest_write(staged, batch=index, batches=len(batches))
            logger.warning(
                'event=v3_reconcile stage=projection_commit outcome=%s trace_id=%s batch=%d batches=%d',
                firestore_failure_reason(error),
                request_log_trace_id(),
                index,
                len(batches),
            )
            raise
        from utils.conversations.v3 import metrics

        for row, _encoded in batch:
            if failure_transitions[row['id']]:
                metrics.terminal_failure(row.get('v3_process_failure_reason'))
        if index != len(batches) - 1:
            # Read back only after our commit; any external race is checked
            # again by the next transaction's revision fence. Pending stays
            # set until the final batch, so an interrupted prefix self-heals.
            for rid in recordings:
                snapshot = coll.document(rid).get()
                current = snapshot.to_dict() or {}
                # The Home feed hook stamps every conversation write at Commit (COMMIT_STAMPED_FIELDS); those
                # stamps are our own write, not an external change.
                owned = {
                    'claims',
                    'v3_pending',
                    'v3_pending_since',
                    'v3_audio_purge_pending',
                    'backfill_superseded',
                    *COMMIT_STAMPED_FIELDS,
                }
                if recordings[rid].get('_v3_derive'):
                    # Our own committed conversion, not an external change.
                    owned |= {'recording', home_visibility_index.FIELD, 'v3_backfill_run', 'v3_backfill_prior'}
                changed = sorted(
                    k
                    for k in set(current) | set(observed[rid])
                    if k not in owned
                    and ((k in current) != (k in observed[rid]) or current.get(k) != observed[rid].get(k))
                )
                if changed:
                    # Claims are ours between batches; any other protected change still conflicts.
                    fence = recordings[rid].get('_v3_fence')
                    if fence is None or not speech_moved(
                        {**recordings[rid], '_v3_fence': {**fence, 'claims': current.get('claims')}}, current
                    ):
                        logger.warning(
                            'v3 projection readback changed kind=recording batch=%d fields=%s', index, changed[:8]
                        )
                        raise Conflict('source_changed')
                    moved.add(rid)
                recordings[rid] = {
                    **recordings[rid],
                    'claims': current.get('claims') or [],
                    '_v3_revision': snapshot.update_time,
                    **({'_v3_fence': source_fence(current)} if recordings[rid].get('_v3_fence') is not None else {}),
                }
            for raw, encoded in batch:
                snapshot = coll.document(raw['id']).get()
                if snapshot.exists:
                    current = snapshot.to_dict() or {}
                    changed = sorted(
                        k for k, value in encoded.items() if k not in COMMIT_STAMPED_FIELDS and current.get(k) != value
                    )
                    if changed:
                        logger.warning(
                            'v3 projection readback changed kind=derived_row batch=%d fields=%s', index, changed[:8]
                        )
                        raise Conflict('source_changed')
                    existing[raw['id']] = {**raw, '_v3_revision': snapshot.update_time}
    return moved


def release_claims(uid, row, *, firestore_client=None):
    """Idempotent claim release after durable delete intent, before hard erasure.

    A purge obligation lives on the recording. Live/pending recordings are never
    eligible for reclaim. The builder sees the deleted interval even after the
    conversation document has gone.
    """
    if row.get('v3_claims_transferred_to'):
        return
    if not row.get('v3_derived') and not row.get('recording_pieces'):
        return
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)

    @firestore.transactional
    def remove(tx):
        intent = (
            client.collection('users')
            .document(uid)
            .collection('deleted_conversations')
            .document(row['id'])
            .get(transaction=tx)
        )
        if not intent.exists:
            raise Conflict('delete_intent_required')
        # The delete caller may have read the card before a sync custody move
        # committed. Once intent exists, no such move may change its links.
        current = coll.document(row['id']).get(transaction=tx).to_dict() or row
        if current.get('v3_claims_transferred_to'):
            return
        ids = set(current.get('v3_recording_ids') or []) | {
            p['recording_id'] for p in current.get('recording_pieces') or []
        }
        snapshots = [(rid, coll.document(rid).get(transaction=tx)) for rid in ids]
        for rid, snapshot in snapshots:
            recording = snapshot.to_dict() or {}
            if not recording.get('recording'):
                continue
            claims = [c for c in recording.get('claims') or [] if c['conversation_id'] != row['id']]
            spans = list(recording.get('deleted_spans') or [])
            if not any(s.get('conversation_id') == row['id'] for s in spans):
                removed = [c for c in recording.get('claims') or [] if c['conversation_id'] == row['id']]
                intervals = [
                    (c.get('start', row['started_at']), c.get('end', row['finished_at'])) for c in removed
                ] or [(row['started_at'], row['finished_at'])]
                for claim in claims:
                    protected_start, protected_end = claim.get('start'), claim.get('end')
                    if protected_start is None or protected_end is None:
                        # Unknown surviving coverage is not permission to erase.
                        intervals = []
                        break
                    remaining = []
                    for start, end in intervals:
                        if end <= protected_start or start >= protected_end:
                            remaining.append((start, end))
                        else:
                            if start < protected_start:
                                remaining.append((start, protected_start))
                            if end > protected_end:
                                remaining.append((protected_end, end))
                    intervals = remaining
                spans.extend({'conversation_id': row['id'], 'start': start, 'end': end} for start, end in intervals)
            tx.update(
                coll.document(rid),
                {
                    'claims': claims,
                    'deleted_spans': spans,
                    # A backfill donor is a legacy conversation hidden only for the spot check: deleting
                    # a backfilled copy never erases the donor's audio or tombstones it; undo restores it.
                    'v3_audio_purge_pending': not claims
                    and not recording.get('v3_pending')
                    and not recording.get('v3_backfill_run')
                    and recording.get('status') == 'completed',
                },
            )

    remove(client.transaction())


# Fields the backfill conversion (and the claim/purge machinery that follows it) may write on a
# legacy donor. Their original values are kept on the donor so undo restores it exactly.
BACKFILL_TRACKED = (
    'recording',
    'claims',
    'v3_pending',
    'v3_pending_since',
    'v3_audio_purge_pending',
    'v3_audio_purge_retry_after',
    'v3_audio_purge_attempts',
    'backfill_superseded',
    'deleted_spans',
)
BACKFILL_SOURCES = frozenset({'omi', 'phone'})
# Metadata page for planning an owner's window; a larger window is refused, never truncated.
BACKFILL_WINDOW_MAX = 10000
BACKFILL_UNDO_PAGE = 100


def backfill_legacy_source(raw):
    """A completed legacy pendant/phone conversation the v3 backfill may re-derive."""
    return bool(
        raw.get('source') in BACKFILL_SOURCES
        and raw.get('status') == 'completed'
        and raw.get('started_at')
        and raw.get('data_protection_level') != 'private'
        and not any(
            raw.get(k)
            # Discarded rows stay discarded and imported rows were never pendant capture (live never
            # converts them either); re-deriving them would surface hidden or foreign history on Home.
            for k in (
                'recording',
                'v3_derived',
                'deleted',
                'discarded',
                'imported',
                'sync_merged_into',
                'is_locked',
                'v3_backfill_run',
            )
        )
    )


def legacy_manual_end(raw):
    """Legacy rows keep the trigger that closed them only in their relevance audit record."""
    decision = raw.get('relevance_decision')
    return isinstance(decision, dict) and decision.get('trigger') == 'client_finalize'


def backfill_conversion(recording):
    """Source patch for a backfill donor: hidden as a recording, its notes and summary untouched."""
    patch = {'recording': True, 'backfill_superseded': True, 'v3_backfill_run': recording['_v3_backfill_run']}
    if '_v3_backfill_prior' in recording:
        patch['v3_backfill_prior'] = recording['_v3_backfill_prior']
    return home_visibility_index.stamp(patch)


def _rederive_prior(row):
    """A previously derived backfill row offered to the planner as an open window with the same id.

    The planner then rebuilds its boundaries, text and notes from the sources (an id is reused, never
    deleted and recreated); edits made to the backfilled copy are not retained.
    """
    return {
        **row,
        'status': 'in_progress',
        'structured': {},
        'summary_covers_through': None,
        'title_locked': False,
        'manual_end': False,
        'discarded': False,
        'v3_rewrites': 0,
        'v3_process_attempts': 0,
        'v3_process_fingerprint': None,
        'v3_process_failed': False,
        'v3_process_failure_reason': None,
        'v3_notes_written': False,
    }


def load_derive(uid, *, since, until, run_id, rederive=False, firestore_client=None):
    """One planned backfill partition: legacy donors, this run's converted donors and derived rows.

    The operator plans partitions at five-minute silence gaps, so a stretch never spans two loads.
    Overflow is a blocked partition, never a partial conversion. Unreadable or private legacy rows
    stay ordinary visible conversations.
    """
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid, firestore_client=client):
        raise Conflict('account_deletion')
    snapshots = list(
        user_conversations(client, uid)
        .where(filter=FieldFilter('started_at', '>=', since))
        .where(filter=FieldFilter('started_at', '<', until))
        .order_by('started_at')
        .limit(LIMIT + 1)
        .stream()
    )
    if len(snapshots) > LIMIT:
        raise Conflict('backfill_partition_budget')

    def ours(raw):
        return bool(raw.get('v3_backfill_run')) and (rederive or raw.get('v3_backfill_run') == run_id)

    recordings, existing = {}, {}
    for snapshot in snapshots:
        raw = snapshot.to_dict() or {}
        if raw.get('deleted'):
            continue
        if backfill_legacy_source(raw) and not rederive:
            row = recording_input(uid, snapshot)
            if row is None or row.get('_v3_unreadable'):
                continue
            recordings[snapshot.id] = {
                **row,
                'recording': True,
                '_v3_derive': True,
                '_v3_backfill_run': run_id,
                '_v3_backfill_prior': {k: raw[k] for k in BACKFILL_TRACKED if k in raw},
                **({'v3_manual_end': True} if legacy_manual_end(raw) else {}),
            }
        elif raw.get('recording') and not raw.get('v3_derived') and ours(raw):
            # A donor this run (or, re-deriving, any run) already converted: resume or rebuild it.
            row = recording_input(uid, snapshot)
            if row is None or row.get('_v3_unreadable'):
                # Its copies are loaded below; planning without it would retire them and leave the
                # donor hidden with nothing on Home. Block until it reads again.
                raise Conflict('backfill_source_unreadable')
            recordings[snapshot.id] = {
                **row,
                '_v3_derive': True,
                '_v3_backfill_run': raw['v3_backfill_run'],
                **({'v3_manual_end': True} if legacy_manual_end(raw) else {}),
            }
        elif raw.get('v3_derived') and raw.get('backfilled') and ours(raw):
            row = decode_row(uid, snapshot)
            if row:
                existing[row['id']] = _rederive_prior(row) if rederive else row
    state = leases.lease_ref(client, uid, BACKFILL_LEASE).get().to_dict() or {}
    cache = json.loads(decrypt(state['outline_cache'], uid)) if state.get('outline_cache') else []
    return recordings, existing, cache


def backfill_window_metadata(uid, since, until, *, firestore_client=None):
    """Metadata only (no transcript decode) for planning an owner's window; refuses a truncated read."""
    client = firestore_client or get_firestore_client()
    snapshots = list(
        user_conversations(client, uid)
        .where(filter=FieldFilter('started_at', '>=', since))
        .where(filter=FieldFilter('started_at', '<', until))
        .order_by('started_at')
        .select(
            [
                'source',
                'status',
                'started_at',
                'finished_at',
                'recording',
                'v3_derived',
                'backfilled',
                'deleted',
                'discarded',
                'imported',
                'sync_merged_into',
                'is_locked',
                'data_protection_level',
                'v3_backfill_run',
                'home_hidden',
                'v3_rederive_live_run',
            ]
        )
        .limit(BACKFILL_WINDOW_MAX + 1)
        .stream()
    )
    if len(snapshots) > BACKFILL_WINDOW_MAX:
        raise Conflict('backfill_window_budget')
    return [{**(snapshot.to_dict() or {}), 'id': snapshot.id} for snapshot in snapshots]


def pending_backfill_processing(uid, *, after=None, deadline=float('inf'), firestore_client=None):
    """Read one backfill page and its next cursor. None means the budget expired."""
    if time.monotonic() >= deadline:
        return None
    client = firestore_client or get_firestore_client()
    conversations = user_conversations(client, uid)
    query = conversations.where(filter=FieldFilter('v3_backfill_process_pending', '==', True))
    if after is not None:
        query = query.order_by('__name__').start_after({'__name__': conversations.document(after)})
    timeout = min(60.0, deadline - time.monotonic())
    if timeout <= 0:
        return None
    rows = []
    tail = None
    size = 0
    try:
        for snapshot in query.limit(LIMIT).stream(timeout=timeout, retry=None):
            if time.monotonic() >= deadline:
                return None
            raw = snapshot.to_dict() or {}
            if python_owns_finalization(raw):
                row = decode_row(uid, snapshot, data=raw)
            else:
                # Foreign debt only needs an ownership marker for discovery.
                row = {key: raw[key] for key in (ENGINE_FIELD, EPOCH_FIELD) if key in raw}
            if row:
                rows.append(row)
            tail = snapshot.id
            size += 1
    except DeadlineExceeded:
        return None
    return rows, tail if size == LIMIT else None


def backfill_run_documents(uid, run_id, *, firestore_client=None):
    """Every document one backfill run stamped: converted donors and derived rows (ids and flags only)."""
    client = firestore_client or get_firestore_client()
    query = (
        user_conversations(client, uid)
        .where(filter=FieldFilter('v3_backfill_run', '==', run_id))
        .select(
            [
                'v3_derived',
                'backfilled',
                'recording',
                'claims',
                'deleted_spans',
                'v3_backfill_prior',
                'v3_recording_ids',
            ]
        )
    )
    return [{**(doc.to_dict() or {}), 'id': doc.id} for doc in query.stream()]


def deleted_after_backfill(donor):
    """The owner deleted a backfilled copy of this donor: restoring it would resurrect what they deleted.

    A delete releases the copy's claim and records its interval in deleted_spans. A converted donor
    always has a claim, so no claim left also means every copy that covered it was deleted.
    """
    prior = donor.get('v3_backfill_prior') or {}
    before = {s.get('conversation_id') for s in prior.get('deleted_spans') or []}
    spans = donor.get('deleted_spans') or []
    return any(s.get('conversation_id') not in before for s in spans) or not donor.get('claims')


def restore_backfill_donors(uid, token, ids, *, firestore_client=None):
    """Undo one page of donors exactly: every tracked field returns to its pre-backfill value.

    A donor whose backfilled copy the owner deleted stays converted (hidden), so the deletion holds;
    returns (restored, kept ids).
    """
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    held = leases.lease_ref(client, uid, BACKFILL_LEASE)

    @firestore.transactional
    def restore(tx):
        lease = held.get(transaction=tx).to_dict() or {}
        snapshots = [(coll.document(cid), coll.document(cid).get(transaction=tx)) for cid in ids]
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        restored, kept = 0, []
        for cid, (ref, snapshot) in zip(ids, snapshots):
            row = snapshot.to_dict() or {}
            if not snapshot.exists or row.get('v3_derived') or not row.get('v3_backfill_run'):
                continue
            prior = row.get('v3_backfill_prior')
            if not isinstance(prior, dict):
                raise Conflict('backfill_prior_missing')
            if deleted_after_backfill(row):
                kept.append(cid)
                continue
            patch = {k: prior[k] if k in prior else firestore.DELETE_FIELD for k in BACKFILL_TRACKED}
            patch.update(v3_backfill_run=firestore.DELETE_FIELD, v3_backfill_prior=firestore.DELETE_FIELD)
            tx.update(ref, home_visibility_index.stamp(patch, row))
            restored += 1
        return restored, kept

    return restore(client.transaction())


def delete_backfill_rows(uid, token, ids, *, firestore_client=None):
    """Remove one page of backfill-derived rows. No tombstone: they were never the user's conversations."""
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    held = leases.lease_ref(client, uid, BACKFILL_LEASE)

    @firestore.transactional
    def remove(tx):
        lease = held.get(transaction=tx).to_dict() or {}
        snapshots = [(coll.document(cid), coll.document(cid).get(transaction=tx)) for cid in ids]
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        removed = 0
        for ref, snapshot in snapshots:
            row = snapshot.to_dict() or {}
            if snapshot.exists and row.get('v3_derived') and row.get('backfilled') and row.get('v3_backfill_run'):
                tx.delete(ref)
                removed += 1
        return removed

    return remove(client.transaction())


def claim_audio_purge(uid, rid, *, firestore_client=None):
    """Close the owner before prefix deletion so late sync cannot reuse it."""
    client = firestore_client or get_firestore_client()
    ref = user_conversations(client, uid).document(rid)
    tombstone = client.collection('users').document(uid).collection('deleted_conversations').document(rid)

    @firestore.transactional
    def claim(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        intent = tombstone.get(transaction=tx)
        if (
            not row.get('recording')
            or not row.get('v3_audio_purge_pending')
            or row.get('v3_backfill_run')
            or row.get('claims')
            or row.get('v3_pending')
            or row.get('status') != 'completed'
        ):
            return False
        if not intent.exists:
            tx.set(
                tombstone,
                {'conversation_id': rid, 'deleted_at': datetime.now(timezone.utc), 'created_at': row.get('created_at')},
            )
        tx.update(ref, {'deleted': True, 'v3_audio_erased': True})
        return True

    return claim(client.transaction())


def transfer_claims(uid, sources, target, *, firestore_client=None):
    """Replace source claims with the durable merged window before source erase."""
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    ids = {rid for row in sources for rid in row.get('v3_recording_ids') or []}
    source_ids = {r['id'] for r in sources}

    @firestore.transactional
    def transfer(tx):
        target_row = coll.document(target['id']).get(transaction=tx).to_dict() or {}
        source_rows = [(r['id'], coll.document(r['id']).get(transaction=tx)) for r in sources]
        records = [(rid, coll.document(rid).get(transaction=tx)) for rid in ids]
        if not target_row or target_row.get('deleted'):
            raise Conflict('merge_target_unavailable')
        for rid, snapshot in records:
            row = snapshot.to_dict() or {}
            if row.get('deleted'):
                raise Conflict('merge_recording_unavailable')
        for rid, snapshot in records:
            row = snapshot.to_dict() or {}
            claims = [c for c in row.get('claims') or [] if c['conversation_id'] not in source_ids]
            claims.extend(
                {**claim, 'conversation_id': target['id']}
                for claim in row.get('claims') or []
                if claim['conversation_id'] in source_ids
            )
            unique = {(c['conversation_id'], c['start'], c['end']): c for c in claims}
            tx.update(coll.document(rid), {'claims': list(unique.values())})
        for cid, snapshot in source_rows:
            if snapshot.exists:
                tx.update(coll.document(cid), {'v3_claims_transferred_to': target['id']})

    transfer(client.transaction())


def outline_attempt(uid, token, fingerprint, *, key='builder', preemptible=False, firestore_client=None):
    if preemptible and key != 'builder':
        raise ValueError('only the live builder outline can be promoted on open')
    client = firestore_client or get_firestore_client()
    ref = leases.lease_ref(client, uid, key)

    @firestore.transactional
    def begin(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or row.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(
            timezone.utc
        ):
            raise Conflict('lease_lost')
        field = 'outline_flex_attempts' if preemptible else 'outline_attempts'
        attempts = dict(row.get(field) or {})
        count = attempts.get(fingerprint, 0)
        if count >= (1 if preemptible else 2):
            return False
        attempts[fingerprint] = count + 1
        update: dict[str, Any] = {field: dict(list(attempts.items())[-128:])}
        if preemptible:
            update['llm_preemptible'] = True
        tx.update(ref, update)
        return True

    return begin(client.transaction())


def write_live_title_preview(uid, token, cid, revision, *, title=None, firestore_client=None):
    """Claim one provider attempt or publish its result, conditional on the same live row."""
    client = firestore_client or get_firestore_client()
    ref = user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'builder')
    deletion_ref = account_deletion_document(uid, firestore_client=client)

    @firestore.transactional
    def write(tx):
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            return False
        deletion = deletion_ref.get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            return False
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('sync_content_revision') != revision or not policy.live_title_candidate(row):
            return False
        state = policy.LIVE_TITLE_STATE
        if title is None and row.get(state) is None:
            tx.update(ref, {state: 'attempted'})
            return True
        if title and row.get(state) == 'attempted':
            row['structured'] = {**(row.get('structured') or {}), 'title': title}
            tx.update(
                ref,
                {'structured': row['structured'], state: 'published', **stamp_home_display(uid, row, 'conversation')},
            )
            return True
        return False

    return write(client.transaction())
