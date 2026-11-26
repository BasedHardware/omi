"""Bounded v3 reads and transaction-fenced leases/claims.

Only lifecycle calls commit_projection. Speech uses the existing conversation
codec; cached outlines are encrypted. Nothing is cleared after a lost race.
"""

import json
import logging
import os
import time
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from google.api_core.exceptions import DeadlineExceeded, InvalidArgument
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import home_visibility_index
from database.conversations_v3_projection_budget import (
    encoded_bytes as _encoded_bytes,
    log_largest_write,
    partition_rows,
)
from database._client import firestore_failure_reason, get_firestore_client
from database.transcript_pointer import (
    MAX_PRELOAD_DOCUMENTS,
    TranscriptBlobAbsent,
    TranscriptShredded,
    run_preloaded_transaction_with_contention_retry,
)
from database import conversations, conversations_v3_leases as leases
from database import conversations_v3_commit_cost as commit_cost
from database import conversations_v3_collisions as collisions
from database.conversations_v3_finish_predecessors import attach as attach_finish_predecessors
from database.conversations_v3_undo_removals import removal_ref
from database import conversations_v3_write_equality as write_equality
from database.recurring_voice_privacy import filter_processing_write
from database.home_feed_fields import COMMIT_STAMPED_FIELDS
from database.account_deletion_marker import account_deletion_blocks_user_work, account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from models.finalization_owner import ENGINE_FIELD, EPOCH_FIELD, python_owns_finalization
from utils.encryption import encrypt, decrypt
from utils.home_feed.projection import stamp as stamp_home_display
from database.conversation_batch_purge_jobs import arm_fields, job_ref
from config.record_wal_duplicate import (
    MERGE_PLAN_FIELD,
    MERGE_TARGET_FIELD,
    RETAINED_DONORS_FIELD,
    SETTLED_FIELD,
    has_retained_custody,
)
from config.conversations_v3 import (
    bounded_pending_enabled,
    boundary_seconds,
    skip_unchanged_writes_enabled,
    stretch_cohesion_enabled,
)
from utils.conversations import terminal_settled
from utils.conversations.v3 import Conflict, UnlockedPage, metrics, policy, preview_wakes, request_log_trace_id
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
    # One token per stored field, taken before decoding: a lost commit names the fields that changed.
    loaded_fields = collisions.fingerprint(data)
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
    data[collisions.FIELDS_KEY] = loaded_fields
    return data


# A source recording whose revision moved during a pass may still be committed against when only its
# speech moved (appended segments, audio files, status, pending/manual-end markers). Any change to
# these fields (deletion, merge, privacy, lock, claims, identity) keeps the strict source_changed fence.
SOURCE_FENCE_FIELDS = (
    'recording',
    'deleted',
    'discarded',
    'deleted_spans',
    'sync_merged_into',
    'data_protection_level',
    'is_locked',
    'started_at',
    'claims',
    'v3_derived',
)


def source_fence(raw):
    row = raw or {}
    fields = SOURCE_FENCE_FIELDS
    if policy.NATIVE_MANUAL_STOP in row or policy.NATIVE_MANUAL_READY in row:
        fields += policy.NATIVE_MANUAL_SOURCE_FIELDS
    return {key: row.get(key) for key in fields}


def terminal_recording(row):
    return row.get('deleted') or row.get('discarded') or row.get('sync_merged_into')


def recording_input(uid, snapshot, *, skip_terminal=False):
    if not snapshot.exists:
        return None
    raw = snapshot.to_dict() or {}
    if (
        not (skip_terminal and terminal_recording(raw))
        and raw.get('data_protection_level') != 'private'
        and raw.get('started_at')
    ):
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
        collisions.FIELDS_KEY: collisions.fingerprint(raw),
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
    never resurrect a window the user deleted. Settled native tiles are returned
    so the planner can reserve their IDs without adopting their speech.
    """
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    found = {}
    for cid in ids:
        snapshot = coll.document(cid).get()
        raw = snapshot.to_dict() or {} if snapshot.exists else {}
        if (
            not (raw.get('v3_derived') or raw.get(policy.NATIVE_MANUAL_SETTLED))
            or raw.get('deleted')
            or raw.get('recording')
        ):
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

    run_preloaded_transaction_with_contention_retry(client, save)


BLOCKED_BACKOFF_MAX = timedelta(hours=1)


def record_blocked(uid, token, reason, *, on_open=False, firestore_client=None):
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
        tx.update(
            ref,
            {
                'v3_blocked_count': count,
                'v3_blocked_reason': reason,
                'v3_backoff_until': now + delay,
                'v3_unlocked_paging_attempted': (
                    bool(row.get('v3_unlocked_paging_attempted'))
                    or (not on_open and bounded_pending_enabled() and bool(row.get('unlocked_ids')))
                ),
                'v3_bounded_pending_attempted': (
                    bool(row.get('v3_bounded_pending_attempted')) if on_open else bounded_pending_enabled()
                ),
            },
        )
        return True

    return run_preloaded_transaction_with_contention_retry(client, park)


BOUNDED_RETRY_REASONS = frozenset({'v3_derived_budget', 'v3_source_closure_budget', 'document_too_large'})


def mark_bounded_attempt(uid, token, *, firestore_client=None):
    """Spend a legacy park's one early attempt under the acquired builder lease, before any paid work.

    A transient failure in that attempt (a provider error Cloud Tasks retries) must not reopen the bypass.
    """
    client = firestore_client or get_firestore_client()
    ref = leases.lease_ref(client, uid, 'builder')

    @firestore.transactional
    def mark(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') == token and _early_bounded_retry(row, row.get('v3_blocked_reason')):
            updates = {'v3_bounded_pending_attempted': True}
            if row.get('unlocked_ids'):
                updates['v3_unlocked_paging_attempted'] = True
            tx.update(ref, updates)

    run_preloaded_transaction_with_contention_retry(client, mark)


def backoff_until(uid, *, firestore_client=None):
    return backoff_state(uid, firestore_client=firestore_client)[0]


def _early_bounded_retry(row, reason):
    return not row.get('v3_bounded_pending_attempted') or (
        reason == 'v3_derived_budget' and row.get('unlocked_ids') and not row.get('v3_unlocked_paging_attempted')
    )


def backoff_state(uid, *, firestore_client=None):
    """(v3_backoff_until, v3_blocked_reason) from the owner's builder lease doc."""
    client = firestore_client or get_firestore_client()
    row = leases.lease_ref(client, uid, 'builder').get().to_dict() or {}
    reason = row.get('v3_blocked_reason')
    if bounded_pending_enabled() and reason in BOUNDED_RETRY_REASONS and _early_bounded_retry(row, reason):
        return None, reason
    return row.get('v3_backoff_until'), reason


TERMINAL_PENDING_SCAN_LIMIT = 50
TERMINAL_PENDING_CLEAR = {'v3_pending': False, 'v3_pending_since': None}


def _oldest_pending(coll, limit):
    return coll.where(filter=FieldFilter('v3_pending', '==', True)).order_by('v3_pending_since').limit(limit)


def clear_terminal_pending(uid, token, *, firestore_client=None):
    """Clear terminal markers and return the page limit to use for the remaining backlog."""
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid):
        raise Conflict('account_deletion')
    coll = user_conversations(client, uid)
    page = list(_oldest_pending(coll, TERMINAL_PENDING_SCAN_LIMIT).stream())
    candidates = {doc.id: doc.update_time for doc in page if _is_discarded_or_deleted(doc.to_dict() or {})}
    held = leases.lease_ref(client, uid, 'builder')
    deletion_ref = account_deletion_document(uid, firestore_client=client)

    @firestore.transactional
    def clear(tx):
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        deletion = deletion_ref.get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            raise Conflict('account_deletion')

        matching = []
        for rid, revision in candidates.items():
            ref = coll.document(rid)
            snapshot = ref.get(transaction=tx)
            row = snapshot.to_dict() or {}
            if (
                snapshot.exists
                and snapshot.update_time == revision
                and row.get('v3_pending') is True
                and _is_discarded_or_deleted(row)
            ):
                matching.append(ref)
        for ref in matching:
            tx.update(ref, TERMINAL_PENDING_CLEAR)
        remembered = lease.get('v3_bounded_pending_limit')
        # When the smaller page would already include the whole backlog, try the full page.
        # Only the final projection commit can clear the saved limit.
        return remembered if remembered in (1, 8) and len(page) - len(matching) >= remembered else None

    return run_preloaded_transaction_with_contention_retry(client, clear)


def _is_discarded_or_deleted(row):
    return row.get('recording') and (row.get('discarded') or row.get('deleted'))


def _select_unlocked(state, existing, limit, page):
    ids = sorted(set(state.get('unlocked_ids') or ()) - existing.keys())
    if page is None:
        if len(ids) > DERIVED_LIMIT:
            raise Conflict('v3_derived_budget')
        return ids
    # Rotate even when a visited preview stays unlocked, so it cannot hide later obligations.
    offset = bisect_right(ids, state.get('v3_unlocked_cursor') or '')
    ordered = ids[offset:] + ids[:offset]
    return ordered[: min(limit, DERIVED_LIMIT)]


def load(
    uid,
    *,
    conversation_id=None,
    pending_limit=32,
    unlocked_page: UnlockedPage | None = None,
    unlocked_limit=None,
    firestore_client=None,
):
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid):
        raise Conflict('account_deletion')
    coll = user_conversations(client, uid)
    silence_gap = timedelta(seconds=boundary_seconds(cohesion=stretch_cohesion_enabled())[0])
    margin = max(timedelta(minutes=20), silence_gap)
    opened = decode_row(uid, coll.document(conversation_id).get()) if conversation_id else None
    skip_terminal = not conversation_id and bounded_pending_enabled()
    if conversation_id:
        ids = (opened or {}).get('v3_recording_ids') or []
        pending = [coll.document(rid).get() for rid in ids]
    else:
        # A zero limit seeds only unlocked windows (the bounded retry's one-lane fallback).
        pending = list(_oldest_pending(coll, pending_limit).stream()) if pending_limit else []
    recordings, unreadable = {}, {}
    for doc in pending:
        row = recording_input(uid, doc, skip_terminal=skip_terminal)
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
                if doc.id not in recordings and not (skip_terminal and terminal_recording(doc.to_dict() or {}))
            ),
            None,
        )
        if following and latest.get('finished_at'):
            next_start = (following.to_dict() or {}).get('started_at')
            if next_start and next_start - latest['finished_at'] < silence_gap:
                latest['_v3_page_continues'] = True
    state = leases.lease_ref(client, uid, 'builder').get().to_dict() or {}
    cache = json.loads(decrypt(state['outline_cache'], uid)) if state.get('outline_cache') else []
    if unlocked_page is not None:
        unlocked_page.remaining, unlocked_page.cursor = frozenset(), None
        unlocked_page.seeds = (sum(doc.id in recordings or doc.id in unreadable for doc in pending), 0)
    ordered_unlocked = []
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
        limit = min(8, pending_limit) if unlocked_limit is None else unlocked_limit
        ordered_unlocked = _select_unlocked(state, existing, limit, unlocked_page)
        if unlocked_page is not None:
            unlocked_page.seeds = (unlocked_page.seeds[0], len(ordered_unlocked))
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
        for rid in sorted(unseen):
            row = recording_input(uid, coll.document(rid).get(), skip_terminal=skip_terminal)
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
        if skip_terminal and terminal_recording(unreadable[rid]):
            continue
        if policy.builder_eligible({**unreadable[rid], '_v3_unreadable': False}):
            raise Conflict('recording_decode_unavailable')
    _mark_successor_pending(coll, recordings)
    attach_finish_predecessors(coll, recordings, existing)
    if unlocked_page is not None:
        unlocked_page.remaining = frozenset(
            set(state.get('unlocked_ids') or ()) - existing.keys() - set(ordered_unlocked)
        )
        cursor = ordered_unlocked[-1] if ordered_unlocked else state.get('v3_unlocked_cursor')
        unlocked_page.cursor = cursor if unlocked_page.remaining else None
    return {**recordings, **unreadable}, existing, cache


def _mark_successor_pending(coll, recordings):
    """Keep the latest stretch open while the recording after a rotation is captured or transcribed.

    Batch recordings get no transcript until they seal. Only a recording that listen rotation
    sealed carries the cap stamp; every other stretch keeps the plain five-minute rule.
    """
    # Only decoded speech counts: a terminal row loaded undecoded may still hold an offloaded transcript pointer.
    spoken = [
        r
        for r in recordings.values()
        if isinstance(r.get('transcript_segments'), list)
        and r['transcript_segments']
        and r.get('started_at')
        and not terminal_recording(r)
    ]
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
            and not (bounded_pending_enabled() and raw.get('discarded'))
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
    'discarded',
    'sync_merged_into',
    'data_protection_level',
]


def unique_claims(claims):
    """Identical claims (same conversation, same span) are one claim; order of first appearance is kept."""
    return list({(c.get('conversation_id'), c.get('start'), c.get('end')): c for c in claims}.values())


# Firestore's per-document limit is 1 MiB ("... exceeds the maximum allowed size"); a commit request is
# separately capped ("Request payload size exceeds the limit: N bytes").
DOCUMENT_TOO_LARGE = 'exceeds the maximum allowed size'
PROPERTY_TOO_LARGE = ('The value of property', 'is longer than')  # one field over 1 MiB: parks like a document
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
    if DOCUMENT_TOO_LARGE in text or all(marker in text for marker in PROPERTY_TOO_LARGE):
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


def mark_pending(uid, cid, *, manual_end=False, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = user_conversations(client, uid).document(cid)
    # Bookkeeping only (conversations_v3_collisions.marked): what this mark changed and whether it met a lock.
    tries, changed, started = [0], ['skipped'], time.monotonic()

    skip_unchanged = skip_unchanged_writes_enabled()

    @firestore.transactional
    def mark(tx):
        tries[0] += 1
        row = ref.get(transaction=tx).to_dict() or {}
        if not row.get('recording') or row.get('deleted'):
            changed[0] = 'skipped'
            return False, None
        # True still owes a wake even when the durable marker is already set.
        # A legacy marker without a timestamp is invisible to the ordered loader and sweeper.
        if (
            skip_unchanged
            and row.get('v3_pending') is True
            and isinstance(row.get('v3_pending_since'), datetime)
            and (not manual_end or row.get('v3_manual_end') is True)
        ):
            # Already marked: no write now, but the read still took the row's lock inside a transaction.
            changed[0] = 'already_pending'
            return True, 'skipped'
        # The landing time (SPEECH_LANDED_FIELD) is stamped by the transaction that commits the speech,
        # not here: a reconcile can run between that commit and this re-arm.
        update = {'v3_pending': True, 'v3_pending_since': row.get('v3_pending_since') or datetime.now(timezone.utc)}
        if manual_end:
            update['v3_manual_end'] = True
        changed[0] = 'already_pending' if all(row.get(k) == v for k, v in update.items()) else 'armed'
        tx.update(ref, update)
        return True, 'written'

    try:
        should_enqueue, outcome = mark(client.transaction())
    except Exception as error:
        collisions.marked('failed', tries[0], time.monotonic() - started, error)
        raise
    collisions.marked(changed[0], tries[0], time.monotonic() - started)
    if outcome:
        metrics.projection_writes('mark_pending', int(outcome == 'written'), int(outcome == 'skipped'))
    return should_enqueue


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
            or row.get(policy.NATIVE_MANUAL_STOP)
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


def _unlocked_lease_update(lease, batch_rows, planned, page, key, clear_pending, final):
    indexed = set(lease.get('unlocked_ids') or ())
    unlocked = {row['id'] for row in batch_rows if row.get('v3_unlocked') and not row.get('deleted')}
    update = {}
    if key == 'builder' and clear_pending and final:
        # A partial pass can retire visited obligations only. Intermediate batches may already
        # have updated the index for newly written previews, which are also in the full plan.
        remaining = indexed & page.remaining if page is not None else set()
        if indexed or planned:
            update['unlocked_ids'] = sorted(planned | remaining)
        if page is not None and lease.get('v3_unlocked_cursor') != page.cursor:
            update['v3_unlocked_cursor'] = page.cursor
    elif indexed or unlocked:
        update['unlocked_ids'] = sorted((indexed - {row['id'] for row in batch_rows}) | unlocked)
    return update


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
    removed_ids: set[str] | None = None,
    retire=None,
    settle=None,
    key='builder',
    bounded_pending_limit=None,
    unlocked_page=None,
    firestore_client=None,
):
    """Commit derived rows and source claims; returns the ids of source recordings that kept moving.

    ``retire`` (live re-derive only) maps a row id to the soft-retirement patch the final batch applies:
    its claims leave every loaded recording with the same commit that writes the rows absorbing them.
    ``removed_ids``, if supplied, receives only the backfill removals committed by the final batch.

    A recording that only received more speech during the pass does not fail the commit (a live
    wearer would otherwise starve every pass): the windows planned from the loaded snapshot commit,
    its claims merge onto the re-read document and it stays v3_pending so the next pass reads the
    new speech. Derived rows and any other source change keep the strict source_changed fence.
    """
    client = firestore_client or get_firestore_client()
    retire = dict(retire or {})
    settle = dict(settle or {})
    if any(
        existing.get(cid, {}).get(field)
        for cid in remove
        for field in (policy.NATIVE_MANUAL_BINDING, policy.NATIVE_MANUAL_NOTES_VISIBILITY, policy.NATIVE_MANUAL_SETTLED)
    ):
        raise Conflict('backfill_native_finish_unsupported')
    if settle and (
        key != 'builder' or remove or retire or not settle.keys() <= existing.keys() - {r['id'] for r in rows}
    ):
        raise Conflict('source_changed')
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
            collisions.report(collisions.RACED, collisions.CONVERSATION, None, writer='plan', lane=key, phase='plan')
            raise Conflict('source_changed')
    # Replacing claims on the same recording must be atomic with removing their old windows.
    replacing_claimants = set()
    if remove:
        planned_sources = {rid for row in rows if not row.get('deleted') for rid in row.get('v3_recording_ids', ())}
        replacing_claimants = set(remove) & {
            claim['conversation_id']
            for rid in planned_sources & recordings.keys()
            for claim in recordings[rid].get('claims') or []
        }
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
    settle_enabled = terminal_settled.serving(uid)
    skip_unchanged = skip_unchanged_writes_enabled()
    written_rows, skipped_rows = set(), set()
    # What the current transaction attempt writes, kept by reference and sized only after a failure.
    staged = {}
    # Bookkeeping only: which document, and whose write, costs this commit a try or the whole pass.
    watch = collisions.CommitWatch(key, {**recordings, **existing}, lead=SOURCE_FENCE_FIELDS)

    @firestore.transactional
    def commit(tx, batch_rows, batch_prepared, final):
        watch.begin()  # Counts the try: the retry runs this body again after a lock abort.
        observed = {}
        batch_moved = set()
        staged.clear()
        staged.update(
            rows=[row for raw, row in zip(batch_rows, batch_prepared) if not raw.get('deleted')], recordings={}
        )
        now = datetime.now(timezone.utc)
        lease_snapshot = held.get(transaction=tx)
        lease = lease_snapshot.to_dict() or {}
        watch.saw(collisions.LEASE_KEY, lease_snapshot, lease)
        watch.phase('deletion_marker')
        deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            raise Conflict('account_deletion')
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= now:
            raise Conflict('lease_lost')
        # Firestore requires every read before every write, including tombstones.
        inputs = {**recordings, **existing}
        watch.phase('documents')
        for rid, snapshot in _projection_snapshots(client, coll, tx, list(inputs), batch_reads=batch_reads):
            row = inputs[rid]
            current = snapshot.to_dict() or {} if snapshot.exists else None
            watch.saw(rid, snapshot, current)
            if not snapshot.exists or snapshot.update_time != row['_v3_revision']:
                if rid in existing or rid not in recordings or not speech_moved(row, current):
                    watch.raced(rid, row, snapshot, current)
                    raise Conflict('source_changed')
                batch_moved.add(rid)
            observed[rid] = current or {}
        watch.reads_done()
        watch.phase('guards')
        absorbed = {cid: row['id'] for row in batch_rows for cid in row.get('_v3_absorbed', ())}
        touched = {*(row['id'] for row in batch_rows), *absorbed}
        if final:
            touched.update((*retire, *remove, *settle))
        if any(has_retained_custody(observed.get(cid)) for cid in touched):
            collisions.report(
                collisions.RACED, collisions.CONVERSATION, None, writer='retained_custody', lane=key, phase='guards'
            )
            raise Conflict('source_changed')
        if absorbed and merge_donors_have_tasks(uid, absorbed, firestore_client=client, transaction=tx):
            collisions.report(
                collisions.RACED, collisions.CONVERSATION, None, writer='task_links', lane=key, phase='guards'
            )
            raise Conflict('source_changed')
        if retired and merge_donors_have_tasks(uid, retired, firestore_client=client, transaction=tx):
            raise Conflict('rederive_live_donor_tasks')
        tombstones = client.collection('users').document(uid).collection('deleted_conversations')
        tombstone_ids = list(
            dict.fromkeys(
                [*(row['id'] for row in batch_rows), *absorbed, *((retire.keys() | settle.keys()) if final else ())]
            )
        )
        if any(
            snapshot.exists
            for _, snapshot in _projection_snapshots(client, tombstones, tx, tombstone_ids, batch_reads=batch_reads)
        ):
            raise Conflict('target_deleted')
        new_ids = sorted({r['id'] for r in batch_rows} - existing.keys())
        if any(
            snapshot.exists for _, snapshot in _projection_snapshots(client, coll, tx, new_ids, batch_reads=batch_reads)
        ):
            raise Conflict('target_exists')
        deleting = set()
        user = client.collection('users').document(uid)
        if final and remove:
            for cid in remove:
                # Only a backfill re-derive retires a copy, and only its own backfilled rows.
                if not (existing.get(cid) or {}).get('backfilled'):
                    raise Conflict('remove_not_backfilled')
            from database import memories

            without_tasks = {
                cid
                for cid in remove
                if not merge_donors_have_tasks(uid, [cid], firestore_client=client, transaction=tx)
            }
            if without_tasks:
                deleting = without_tasks - memories.linked_conversation_ids(
                    uid, without_tasks, firestore_client=client, transaction=tx
                )
            if replacing_claimants - deleting:
                raise Conflict('backfill_rederive_linked_claims')
        watch.phase('privacy')
        # Filtering can mutate the encoded payload; every attempt needs its original input.
        batch_prepared = [dict(row) for row in batch_prepared]
        for row in batch_prepared:
            filter_processing_write(tx, user, row)
        watch.phase('commit')
        skipped_ids = set()
        skipped_patches, written = set(), set()

        def update_if_changed(ref, current, patch, *, count_row=True):
            if skip_unchanged and write_equality.or_write(write_equality.same_patch, current, patch):
                if count_row:
                    skipped_patches.add(ref.id)
                return
            tx.update(ref, patch)
            if count_row:
                written.add(ref.id)

        for raw, row in zip(batch_rows, batch_prepared):
            if raw.get('deleted'):
                continue
            if final and row['id'] in retire:
                # A live re-derive survivor's bridge list lands with the bridges it names.
                row = {**row, **retire[row['id']]}
            # Planned settles (failure patch, unavailable preview) close here; the planner row keeps any prior stamp.
            row = terminal_settled.stamp(observed.get(row['id']) or {}, dict(row), now=now, enabled=settle_enabled)
            cid = row['id']
            if (
                skip_unchanged
                and cid in observed
                and write_equality.or_write(write_equality.same_conversation, uid, observed[cid], row)
            ):
                skipped_ids.add(cid)
                continue
            tx.set(coll.document(cid), row)
            written.add(cid)
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
            written.add(cid)
        if final:
            for cid, patch in settle.items():
                tx.update(coll.document(cid), home_visibility_index.stamp(patch, observed[cid]))
            for cid in sorted(deleting):
                tx.set(removal_ref(user, cid), {'removed_by_backfill_rederive': True})
                tx.delete(coll.document(cid))
                written.add(cid)
            planned_ids = {r['id'] for r in batch_rows}
            for cid, patch in retire.items():
                if cid not in planned_ids:
                    update_if_changed(coll.document(cid), observed.get(cid, {}), patch)
                if cid in retired:
                    tx.set(removal_ref(user, cid), {'retired_by_repair': True})
        replaced = (
            {r['id'] for r in batch_rows} | set(absorbed) | deleting | (retired | settle.keys() if final else set())
        )
        for rid, recording in recordings.items():
            if (
                recording.get('deleted')
                or recording.get('sync_merged_into')
                or (key == 'builder' and clear_pending and bounded_pending_enabled() and recording.get('discarded'))
            ):
                update_if_changed(coll.document(rid), observed[rid], TERMINAL_PENDING_CLEAR)
                continue
            if recording.get('discarded'):
                continue  # Existing custody is retained even when terminal cleanup is disabled.
            if rid in batch_moved or rid in moved:
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
                update_if_changed(coll.document(rid), observed[rid], update)
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
            update_if_changed(coll.document(rid), observed[rid], update)
        lease_update = {
            **({'v3_blocked_count': 0, 'v3_backoff_until': None, 'v3_blocked_reason': None} if final else {}),
            'outline_cache': encrypted_cache,
            'open_id': (
                open_ids[0] if open_ids else (lease.get('open_id') if lease.get('open_id') not in existing else None)
            ),
        }
        if final and bounded_pending_limit is not None:
            remembered_limit = bounded_pending_limit if bounded_pending_limit < 32 else None
            if lease.get('v3_bounded_pending_limit') != remembered_limit:
                lease_update['v3_bounded_pending_limit'] = remembered_limit
        lease_update.update(
            _unlocked_lease_update(lease, batch_rows, planned_unlocked, unlocked_page, key, clear_pending, final)
        )
        if skip_unchanged and write_equality.or_write(
            write_equality.same_outline_cache, uid, lease.get('outline_cache'), encrypted_cache
        ):
            lease_update['outline_cache'] = lease['outline_cache']
        staged['lease'] = (lease, lease_update)
        update_if_changed(held, lease, lease_update, count_row=False)
        return observed, batch_moved, batch_prepared, skipped_ids, written, skipped_ids | skipped_patches, deleting

    fixed = fixed_write_bytes(recordings, rows, encrypted_cache)
    fixed += _encoded_bytes(settle) if settle else 0
    fixed_writes = len(recordings) + 2 * len(remove) + absorption_writes + len(retire) + len(retired) + len(settle) + 1
    batches = partition_rows(
        rows,
        prepared,
        fixed=fixed,
        fixed_writes=fixed_writes,
        max_writes=BATCH_MAX_WRITES,
        max_bytes=BATCH_WRITE_BYTES,
        row_bytes=BATCH_ROW_BYTES,
        max_pointers=MAX_PRELOAD_DOCUMENTS,
        removals=bool(retired or remove),
        settle=bool(settle),
        replacing_claimants=replacing_claimants,
    )
    for index, batch in enumerate(batches):
        batch_rows, batch_prepared, final = [r for r, _ in batch], [r for _, r in batch], index == len(batches) - 1
        try:
            watch.reset()

            def execute():
                # Main's retry: up to three fresh transactions with a jittered wait (SCA-2918).
                return run_preloaded_transaction_with_contention_retry(
                    client, commit, batch_rows, batch_prepared, final
                )

            if key == 'builder':
                # The live builder's commit is timed and the cost of its lock retries counted
                # (database/conversations_v3_commit_cost.py). The transaction and its retries are unchanged.
                result = commit_cost.run(
                    execute,
                    reads_per_attempt=2 + len(recordings) + len(existing) + len(batch_rows),
                    attempts=lambda: watch.attempt,
                )
            else:
                result = execute()
            observed, batch_moved, committed_prepared, skipped_ids, written, skipped, deleting = result
        except Conflict:
            raise
        except Exception as error:
            watch.failed(error, client, coll, held)
            if isinstance(error, InvalidArgument) and size_error(error):
                metrics.safe_metric(lambda: log_largest_write(staged, batch=index, batches=len(batches)))
            metrics.safe_metric(
                lambda: logger.warning(
                    'event=v3_reconcile stage=projection_commit outcome=%s trace_id=%s batch=%d batches=%d',
                    firestore_failure_reason(error),
                    request_log_trace_id(),
                    index,
                    len(batches),
                )
            )
            raise
        moved.update(batch_moved)
        written_rows.update(written)
        skipped_rows.update(skipped)
        if removed_ids is not None:
            removed_ids.update(deleting)

        for row, _encoded in batch:
            if failure_transitions[row['id']]:
                metrics.safe_metric(lambda row=row: metrics.terminal_failure(row.get('v3_process_failure_reason')))
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
                        metrics.safe_metric(
                            lambda: logger.warning(
                                'v3 projection readback changed kind=recording batch=%d fields=%s',
                                index,
                                changed[:8],
                            )
                        )
                        collisions.report(
                            collisions.RACED,
                            collisions.RECORDING_ROW,
                            changed,
                            lane=key,
                            phase='readback',
                            update_time=snapshot.update_time,
                        )
                        raise Conflict('source_changed')
                    moved.add(rid)
                recordings[rid] = {
                    **recordings[rid],
                    'claims': current.get('claims') or [],
                    '_v3_revision': snapshot.update_time,
                    collisions.FIELDS_KEY: collisions.fingerprint(current),
                    **({'_v3_fence': source_fence(current)} if recordings[rid].get('_v3_fence') is not None else {}),
                }
            for (raw, _), encoded in zip(batch, committed_prepared):
                if raw['id'] in skipped_ids:
                    continue  # The next batch fences this row at its original revision.
                snapshot = coll.document(raw['id']).get()
                if snapshot.exists:
                    current = snapshot.to_dict() or {}
                    changed = sorted(
                        k for k, value in encoded.items() if k not in COMMIT_STAMPED_FIELDS and current.get(k) != value
                    )
                    if changed:
                        metrics.safe_metric(
                            lambda: logger.warning(
                                'v3 projection readback changed kind=derived_row batch=%d fields=%s',
                                index,
                                changed[:8],
                            )
                        )
                        collisions.report(
                            collisions.RACED,
                            collisions.doc_kind(current),
                            changed,
                            lane=key,
                            phase='readback',
                            update_time=snapshot.update_time,
                        )
                        raise Conflict('source_changed')
                    existing[raw['id']] = {
                        **raw,
                        '_v3_revision': snapshot.update_time,
                        collisions.FIELDS_KEY: collisions.fingerprint(current),
                    }
    metrics.projection_writes('commit_projection', len(written_rows), len(skipped_rows - written_rows))
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
            deleted_copies = list(recording.get('v3_backfill_deleted_copies') or [])
            if recording.get('v3_backfill_run') and row['id'] not in deleted_copies:
                # Undo must see this deletion even when surviving claims cover the interval (no span).
                deleted_copies.append(row['id'])
            tx.update(
                coll.document(rid),
                {
                    'claims': claims,
                    'deleted_spans': spans,
                    **({'v3_backfill_deleted_copies': deleted_copies} if deleted_copies else {}),
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
    'v3_backfill_deleted_copies',
)
BACKFILL_SOURCES = frozenset({'omi', 'phone'})
# Metadata page for planning an owner's window; a larger window is refused, never truncated.
BACKFILL_WINDOW_MAX = 10000
# Documents one undo transaction reads: the lease and run, each donor, and per copy the row, its
# tombstone and its notes lease. Kept within Firestore's 500 per-transaction bound.
UNDO_GROUP_MAX = 500


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
        # The rebuilt window decides its own notes obligation; a stale marker never rides along.
        'v3_process_pending': False,
        'v3_backfill_process_pending': False,
        # A fresh notes retry budget for the rebuilt window.
        'v3_backfill_attempts': 0,
    }


def load_derive(uid, *, since, until, run_id, rederive=False, firestore_client=None):
    """One planned backfill partition: legacy donors, this run's converted donors and derived rows.

    The operator plans partitions at five-minute silence gaps, so a stretch never spans two loads.
    Overflow is a blocked partition, never a partial conversion. Unreadable or private legacy rows
    stay ordinary visible conversations.
    """
    client = firestore_client or get_firestore_client()
    # The marker lives on the data plane; the default resolver pins it (never the conversations client).
    # Fresh: this load gates sending the owner's transcript to the outline model.
    if account_deletion_blocks_user_work(uid, fresh=True):
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
                'v3_backfill_deleted_copies',
            ]
        )
    )
    return [{**(doc.to_dict() or {}), 'id': doc.id} for doc in query.stream()]


def deleted_after_backfill(donor):
    """The owner deleted a backfilled copy of this donor: restoring it would resurrect what they deleted.

    A delete records the copy's interval in the donor's deleted_spans (keyed by the copy id); spans the
    donor already had before the run are not the owner's post-backfill deletion. A donor with no claim
    but no new span (its copy never committed, or a re-derive retired it) is not a deletion.
    """
    if donor.get('v3_backfill_deleted_copies'):
        return True
    prior = donor.get('v3_backfill_prior') or {}
    before = {s.get('conversation_id') for s in prior.get('deleted_spans') or []}
    return any(s.get('conversation_id') not in before for s in donor.get('deleted_spans') or [])


def deleted_copy_ids(uid, ids, *, firestore_client=None):
    """Copy ids that now have a deletion tombstone (ids and existence only)."""
    client = firestore_client or get_firestore_client()
    tombstones = client.collection('users').document(uid).collection('deleted_conversations')
    return [cid for cid in ids if tombstones.document(cid).get().exists]


def undo_backfill_group(uid, token, donor_ids, row_ids, *, run_id, firestore_client=None):
    """Undo one connected group of a run in one transaction: restore its donors exactly, remove its copies.

    A group is every donor and copy linked by claims, so it either goes back to legacy whole or stays
    v3 whole. It stays when the owner deleted any copy in it (a tombstone for a copy id, or a donor
    deleted span added after the run); its copies' owed backfill notes move to the live marker so
    they are still written. The tombstones are read inside the transaction, so a deletion racing undo
    either lands first (the group stays) or retries after the copies are gone. A group whose copy
    also holds a recording outside the group or is stamped with another run stays too: 'kept_live'. Returns
    (outcome, donors restored or kept, rows removed). The run ledger's undo progress
    (totals and removed copy ids) is written in the same transaction, so a crash never loses it.
    """
    if 2 + len(donor_ids) + 3 * len(row_ids) > UNDO_GROUP_MAX:
        # Partitions cap loaded documents (LIMIT), so a group stays far below the transaction write
        # limit; anything larger is refused whole rather than undone across transactions.
        raise Conflict('undo_group_too_large')
    client = firestore_client or get_firestore_client()
    coll = user_conversations(client, uid)
    tombstones = client.collection('users').document(uid).collection('deleted_conversations')
    held = leases.lease_ref(client, uid, BACKFILL_LEASE)
    from database import conversations_v3_backfill_runs as runs

    ledger = runs.run_ref(client, uid, run_id)

    @firestore.transactional
    def undo(tx):
        lease = held.get(transaction=tx).to_dict() or {}
        run = ledger.get(transaction=tx)
        donors = [(cid, coll.document(cid).get(transaction=tx)) for cid in donor_ids]
        rows = [(cid, coll.document(cid).get(transaction=tx)) for cid in row_ids]
        deleted = [tombstones.document(cid).get(transaction=tx).exists for cid in row_ids]
        notes = [leases.lease_ref(client, uid, 'summary-' + cid).get(transaction=tx).to_dict() or {} for cid in row_ids]
        now = datetime.now(timezone.utc)
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= now:
            raise Conflict('lease_lost')
        if any(n.get('token') and n.get('until') and n['until'] > now for n in notes):
            # A notes write started on a copy after undo's first check: never delete under it.
            raise Conflict('notes_in_flight')
        donor_rows = [(cid, snapshot.to_dict() or {}) for cid, snapshot in donors if snapshot.exists]
        converted = [
            (cid, row) for cid, row in donor_rows if not row.get('v3_derived') and row.get('v3_backfill_run') == run_id
        ]
        copies = [(cid, snapshot.to_dict() or {}) for cid, snapshot in rows]
        foreign = any(row.get('v3_backfill_run') not in (None, run_id) for _, row in donor_rows + copies)
        group = set(donor_ids)
        # A live pass after the run carries the run tag onto a window that also holds live recordings
        # (service.reconcile): deleting that copy would delete live capture, so the group stays v3.
        # Any recording outside the group counts, a donor of another run included. A group that is
        # also an owner deletion is reported as 'kept' (the deletion reason wins).
        live = any(
            rid not in group
            for _, snapshot in rows
            if snapshot.exists
            for rid in (snapshot.to_dict() or {}).get('v3_recording_ids') or []
        )
        owner_deleted = any(deleted) or any(deleted_after_backfill(row) for _, row in converted)
        if live or foreign or owner_deleted:
            for (cid, row), gone in zip(copies, deleted):
                if row.get('v3_backfill_run') != run_id:
                    continue
                if row.get('v3_backfill_process_pending'):
                    # A copy the owner deleted never goes to the notes model; the others still get notes.
                    patch = {'v3_backfill_process_pending': False, 'v3_process_pending': not gone}
                    tx.update(coll.document(cid), patch)
                elif gone and row.get('v3_process_pending'):
                    tx.update(coll.document(cid), {'v3_process_pending': False})
            return ('kept' if owner_deleted else 'kept_live'), len(converted), 0
        for cid, row in converted:
            prior = row.get('v3_backfill_prior')
            if not isinstance(prior, dict):
                raise Conflict('backfill_prior_missing')
            patch = {k: prior[k] if k in prior else firestore.DELETE_FIELD for k in BACKFILL_TRACKED}
            patch.update(v3_backfill_run=firestore.DELETE_FIELD, v3_backfill_prior=firestore.DELETE_FIELD)
            tx.update(coll.document(cid), home_visibility_index.stamp(patch, row))
        removed = []
        for cid, row in copies:
            # Only this backfill's copies; never a live row and no tombstone (they were never the owner's).
            if row.get('v3_derived') and row.get('backfilled') and row.get('v3_backfill_run') == run_id:
                tx.delete(coll.document(cid))
                removed.append(cid)
        if run.exists:
            progress = (run.to_dict() or {}).get('undo_progress') or {}
            tx.update(
                ledger,
                {
                    'undo_progress': {
                        'donors_restored': int(progress.get('donors_restored') or 0) + len(converted),
                        'rows_removed': int(progress.get('rows_removed') or 0) + len(removed),
                        'removed_ids': list(progress.get('removed_ids') or []) + removed,
                    }
                },
            )
        return 'undone', len(converted), len(removed)

    return undo(client.transaction())


# Record-WAL duplicate custody a user erasure invalidates. The merge plan is
# job-scoped today; clearing it here keeps a stray row copy from outliving erasure.
AUDIO_PURGE_CUSTODY_FIELDS = (SETTLED_FIELD, RETAINED_DONORS_FIELD, MERGE_TARGET_FIELD, MERGE_PLAN_FIELD)
# Batch intakes keyed to the recording (wal_duplicate_<file>, wal_duplicate_terminal_<job>)
# are owed erasure before the blobs go: 'inline' runs purge_batch_owner in the sweep,
# 'armed' means a conversation_batch_purge_jobs obligation was written with this marker.
AUDIO_PURGE_INTAKES_FIELD = 'v3_audio_purge_intakes'
# A merge target's retained donors, kept from the custody clear until the blob erase runs.
AUDIO_PURGE_DONORS_FIELD = 'v3_audio_purge_source_ids'


def _custody_clear(row):
    """Delete each AUDIO_PURGE_CUSTODY_FIELDS field present on ``row``.

    Keys are spelled out rather than generated so the terminal-writer ratchet
    can see this patch never carries ``status``.
    """
    clear = {
        SETTLED_FIELD: firestore.DELETE_FIELD,
        RETAINED_DONORS_FIELD: firestore.DELETE_FIELD,
        MERGE_TARGET_FIELD: firestore.DELETE_FIELD,
        MERGE_PLAN_FIELD: firestore.DELETE_FIELD,
    }
    for field in list(clear):
        if field not in row:
            del clear[field]
    return clear


@dataclass(frozen=True)
class AudioPurgeClaim:
    """What the purge owes before deleting blobs. ``intakes``: none, inline, pending or done."""

    custody_invalidated: bool = False
    intakes: str = 'none'
    donor_ids: tuple[str, ...] = ()


def claim_audio_purge(uid, rid, *, defer_intake_purge=False, firestore_client=None):
    """Close the owner before prefix deletion so late sync cannot reuse it.

    A user deletion outranks record-WAL duplicate custody: the same commit that
    closes the owner clears the custody fields and records that the batch
    intakes are owed erasure (arming the obligations when ``defer_intake_purge``).
    A merge target's retained donors are erased with it, so the commit also
    writes each donor's deletion intent and clears its custody; an erased donor
    is removed from its live successor's lineage. Returns False when the row is
    not purgeable, else an ``AudioPurgeClaim``.
    """
    client = firestore_client or get_firestore_client()
    conversations_ref = user_conversations(client, uid)
    ref = conversations_ref.document(rid)
    tombstones = client.collection('users').document(uid).collection('deleted_conversations')

    @firestore.transactional
    def claim(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        intent = tombstones.document(rid).get(transaction=tx)
        if (
            not row.get('recording')
            or not row.get('v3_audio_purge_pending')
            or row.get('v3_backfill_run')
            or row.get('claims')
            or row.get('v3_pending')
            or row.get('status') != 'completed'
        ):
            return False
        custody = has_retained_custody(row) or bool(row.get(MERGE_PLAN_FIELD))
        owed = row.get(AUDIO_PURGE_INTAKES_FIELD)
        if custody and owed is None:
            owed = 'inline'
        donors = list(row.get(AUDIO_PURGE_DONORS_FIELD) or [])
        retained = row.get(RETAINED_DONORS_FIELD) if custody else None
        if isinstance(retained, list) and retained and not donors:
            # The donor list goes with custody; the erase it is owed may run sweeps later.
            donors = [d for d in retained if isinstance(d, str) and d and '/' not in d and d != rid]
        # Every read precedes the first write. Rows without custody or donors read nothing more.
        donor_rows = {donor: conversations_ref.document(donor).get(transaction=tx) for donor in donors}
        donor_intents = {donor: tombstones.document(donor).get(transaction=tx).exists for donor in donors}
        # A donor another target now retains is not this recording's to erase.
        donors = [
            donor
            for donor in donors
            if not isinstance(target := (donor_rows[donor].to_dict() or {}).get(MERGE_TARGET_FIELD), str)
            or target == rid
        ]
        owners = (rid, *donors)
        armed = {owner: job_ref(client, uid, owner).get(transaction=tx).exists for owner in owners} if owed else {}
        successor_id = row.get(MERGE_TARGET_FIELD) if custody else None
        successor_ref = (
            conversations_ref.document(successor_id) if isinstance(successor_id, str) and successor_id else None
        )
        successor = (successor_ref.get(transaction=tx).to_dict() or {}) if successor_ref is not None else {}
        now = datetime.now(timezone.utc)
        if not intent.exists:
            tx.set(
                tombstones.document(rid),
                {'conversation_id': rid, 'deleted_at': now, 'created_at': row.get('created_at')},
            )
        for donor in donors:
            snapshot = donor_rows[donor]
            donor_row = (snapshot.to_dict() or {}) if snapshot.exists else {}
            if not donor_intents[donor]:
                # The donor's own deletion intent: its batch purge requires it, and handoff,
                # live upload and merge publication refuse a tombstoned donor.
                tx.set(
                    tombstones.document(donor),
                    {'conversation_id': donor, 'deleted_at': now, 'created_at': donor_row.get('created_at')},
                )
            stale = _custody_clear(donor_row)
            if stale:
                tx.update(conversations_ref.document(donor), stale)
        lineage = {}
        retained_lineage = successor.get(RETAINED_DONORS_FIELD) or []
        if rid in retained_lineage:
            lineage[RETAINED_DONORS_FIELD] = [value for value in retained_lineage if value != rid]
        merged_lineage = successor.get('sync_merged_from') or []
        if rid in merged_lineage:
            lineage['sync_merged_from'] = [value for value in merged_lineage if value != rid]
        if lineage:
            # The erased donor leaves its successor's lineage, so no later delete or merge resolves it.
            tx.update(successor_ref, lineage)
        updates: dict[str, Any] = {'deleted': True, 'v3_audio_erased': True}
        if custody:
            updates.update(_custody_clear(row))
        if donors != list(row.get(AUDIO_PURGE_DONORS_FIELD) or []):
            updates[AUDIO_PURGE_DONORS_FIELD] = donors
        if owed == 'inline' and defer_intake_purge:
            for owner in owners:
                if not armed[owner]:
                    # Each owner's tombstone above is the obligation runner's deletion intent.
                    tx.set(job_ref(client, uid, owner), arm_fields(uid, owner))
                    armed[owner] = True
            owed = 'armed'
        if owed and owed != row.get(AUDIO_PURGE_INTAKES_FIELD):
            updates[AUDIO_PURGE_INTAKES_FIELD] = owed
        tx.update(ref, updates)
        pending = any(armed.values())
        if owed == 'armed':
            # Without dispatch the sweep erases inline; absent armed obligations were run to completion.
            intakes = ('pending' if defer_intake_purge else 'inline') if pending else 'done'
        else:
            intakes = owed or 'none'
        return AudioPurgeClaim(custody_invalidated=custody, intakes=intakes, donor_ids=tuple(donors))

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

    return run_preloaded_transaction_with_contention_retry(client, begin)


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

    return run_preloaded_transaction_with_contention_retry(client, write)
