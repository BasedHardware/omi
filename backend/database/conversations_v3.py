"""Bounded v3 reads and transaction-fenced leases/claims.

Only lifecycle calls commit_projection. Speech uses the existing conversation
codec; cached outlines are encrypted. Nothing is cleared after a lost race.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.transcript_pointer import TranscriptBlobAbsent, TranscriptShredded
from database import conversations, conversations_v3_leases as leases
from database.account_deletion_marker import account_deletion_blocks_user_work, account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.encryption import encrypt, decrypt
from utils.conversations.v3 import Conflict
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, OPEN_LOOP_EXTRACTIONS_FIELD

LIMIT = 128


def user_conversations(client, uid):
    return client.collection('users').document(uid).collection('conversations')


def decode_row(uid, snapshot) -> dict[str, Any] | None:
    data = snapshot.to_dict() or {}
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


def save_outline(uid, token, fingerprint, entries, *, firestore_client=None):
    """Keep a paid outline even when this pass's projection commit later conflicts."""
    client = firestore_client or get_firestore_client()
    ref = leases.lease_ref(client, uid, 'builder')

    @firestore.transactional
    def save(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or row.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(
            timezone.utc
        ):
            raise Conflict('lease_lost')
        cache = json.loads(decrypt(row['outline_cache'], uid)) if row.get('outline_cache') else []
        cache = [c for c in cache if c.get('fingerprint') != fingerprint]
        cache.append({'fingerprint': fingerprint, 'entries': entries})
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
    client = firestore_client or get_firestore_client()
    return (leases.lease_ref(client, uid, 'builder').get().to_dict() or {}).get('v3_backoff_until')


def load(uid, *, conversation_id=None, firestore_client=None):
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid):
        raise Conflict('account_deletion')
    coll = user_conversations(client, uid)
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
            if next_start and next_start - latest['finished_at'] < timedelta(minutes=5):
                latest['_v3_page_continues'] = True
    state = leases.lease_ref(client, uid, 'builder').get().to_dict() or {}
    cache = json.loads(decrypt(state['outline_cache'], uid)) if state.get('outline_cache') else []
    if not recordings and not state.get('open_id') and not opened:
        return unreadable, {}, cache
    existing = {}
    if opened:
        existing[opened['id']] = opened
    elif state.get('open_id') and not conversation_id:
        opened = decode_row(uid, coll.document(state['open_id']).get())
        if opened:
            existing[opened['id']] = opened
    queried = set()
    # Follow linked recordings until the closure converges. Each round adds at least one recording and
    # derived rows stay bounded by LIMIT; a fixed hop depth failed the same owner on every retry.
    for _round in range(LIMIT + 1):
        ids = {rid for row in existing.values() for rid in row.get('v3_recording_ids') or []}
        ids.update(
            p['recording_id']
            for row in existing.values()
            for p in row.get('recording_pieces') or []
            if p['recording_id'] != row['id']
        )
        for rid in ids - recordings.keys():
            row = recording_input(uid, coll.document(rid).get())
            if row:
                if row.get('_v3_unreadable'):
                    unreadable[rid] = row
                else:
                    recordings[rid] = row
        fresh = [r for rid, r in recordings.items() if rid not in queried and r and r.get('started_at')]
        if not fresh:
            break
        # Query disjoint affected source windows separately: historical sync must
        # not scan every conversation between its recorded day and today's live row.
        intervals = []
        for row in sorted(fresh, key=lambda r: r['started_at']):
            left = row['started_at'] - timedelta(minutes=20)
            right = min(speech_end(row), datetime.now(timezone.utc) + timedelta(minutes=5)) + timedelta(minutes=20)
            if intervals and left <= intervals[-1][1]:
                intervals[-1] = (intervals[-1][0], max(intervals[-1][1], right))
            else:
                intervals.append((left, right))
        for left, right in intervals:
            snapshots = list(
                coll.where(filter=FieldFilter('v3_derived', '==', True))
                .where(filter=FieldFilter('finished_at', '>=', left))
                .where(filter=FieldFilter('started_at', '<=', right))
                .limit(LIMIT + 1)
                .stream()
            )
            for doc in snapshots:
                row = decode_row(uid, doc)
                if row:
                    existing[row['id']] = row
            if len(snapshots) > LIMIT or len(existing) > LIMIT:
                raise Conflict('v3_derived_budget')
        queried.update(row['id'] for row in fresh)
    else:
        raise Conflict('v3_source_closure_budget')
    return {**recordings, **unreadable}, existing, cache


def mark_pending(uid, cid, *, manual_end=False, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = user_conversations(client, uid).document(cid)

    @firestore.transactional
    def mark(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if not row.get('recording') or row.get('deleted'):
            return False
        update = {'v3_pending': True, 'v3_pending_since': row.get('v3_pending_since') or datetime.now(timezone.utc)}
        if manual_end:
            update['v3_manual_end'] = True
        tx.update(ref, update)
        return True

    return mark(client.transaction())


def commit_projection(uid, token, recordings, existing, rows, cache, *, clear_pending=True, firestore_client=None):
    """Commit derived rows and source claims; returns the ids of source recordings that kept moving.

    A recording that only received more speech during the pass does not fail the commit (a live
    wearer would otherwise starve every pass): the windows planned from the loaded snapshot commit,
    its claims merge onto the re-read document and it stays v3_pending so the next pass reads the
    new speech. Derived rows and any other source change keep the strict source_changed fence.
    """
    client = firestore_client or get_firestore_client()
    moved = set()
    coll = user_conversations(client, uid)
    held = leases.lease_ref(client, uid, 'builder')
    open_ids = [r['id'] for r in rows if r['status'] == 'in_progress' and not r.get('deleted')]
    if len(open_ids) > 1:
        raise Conflict('multiple_open_conversations')
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
        prepared.append(encoded)
    encrypted_cache = encrypt(json.dumps(cache, default=str), uid)

    @firestore.transactional
    def commit(tx, batch_rows, batch_prepared, final):
        observed = {}
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
        for rid, row in {**recordings, **existing}.items():
            snapshot = coll.document(rid).get(transaction=tx)
            current = snapshot.to_dict() or {} if snapshot.exists else None
            if not snapshot.exists or snapshot.update_time != row['_v3_revision']:
                if rid in existing or rid not in recordings or not speech_moved(row, current):
                    raise Conflict('source_changed')
                moved.add(rid)
            observed[rid] = current or {}
        for row in batch_rows:
            tombstone = (
                client.collection('users')
                .document(uid)
                .collection('deleted_conversations')
                .document(row['id'])
                .get(transaction=tx)
            )
            if tombstone.exists:
                raise Conflict('target_deleted')
        new_ids = {r['id'] for r in batch_rows} - existing.keys()
        for cid in new_ids:
            if coll.document(cid).get(transaction=tx).exists:
                raise Conflict('target_exists')
        from database.recurring_voice_privacy import filter_processing_write

        user = client.collection('users').document(uid)
        for row in batch_prepared:
            filter_processing_write(tx, user, row)
        for raw, row in zip(batch_rows, batch_prepared):
            if raw.get('deleted'):
                continue
            tx.set(coll.document(row['id']), row)
        for rid, recording in recordings.items():
            if recording.get('deleted') or recording.get('sync_merged_into'):
                tx.update(coll.document(rid), {'v3_pending': False, 'v3_pending_since': None})
                continue
            replaced = {r['id'] for r in batch_rows}
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
                tx.update(
                    coll.document(rid),
                    {
                        'claims': claims,
                        'v3_pending': True,
                        'v3_pending_since': observed[rid].get('v3_pending_since')
                        or recording.get('v3_pending_since')
                        or datetime.now(timezone.utc),
                    },
                )
                continue
            claims = [c for c in recording.get('claims') or [] if c['conversation_id'] not in replaced]
            for row in batch_rows:
                if rid not in row.get('v3_recording_ids', []) or row.get('deleted'):
                    continue
                spans = row.get('_v3_claims', {}).get(rid, [{'start': row['started_at'], 'end': row['finished_at']}])
                claims.extend({'conversation_id': row['id'], **span} for span in spans)
            tx.update(
                coll.document(rid),
                {
                    'claims': claims,
                    # A backfill conversion hides its donor as a recording in the first batch; until the
                    # final batch commits, it keeps a durable obligation so an interrupted run is rebuilt
                    # by the ordinary builder (backfill's loader skips recordings).
                    'v3_pending': (
                        False
                        if final and clear_pending
                        else bool(recording.get('v3_pending') or (recording.get('_v3_derive') and not final))
                    ),
                    'v3_pending_since': (
                        None
                        if final and clear_pending
                        else recording.get('v3_pending_since')
                        or (datetime.now(timezone.utc) if recording.get('_v3_derive') and not final else None)
                    ),
                    'v3_audio_purge_pending': bool(recording.get('deleted_spans'))
                    and final
                    and clear_pending
                    and not claims
                    and recording.get('status') == 'completed',
                    **(
                        {'recording': True, 'structured': {}, 'backfill_superseded': True}
                        if recording.get('_v3_derive')
                        else {}
                    ),
                },
            )
        tx.update(
            held,
            {
                **({'v3_blocked_count': 0, 'v3_backoff_until': None, 'v3_blocked_reason': None} if final else {}),
                'outline_cache': encrypted_cache,
                'open_id': (
                    open_ids[0]
                    if open_ids
                    else (lease.get('open_id') if lease.get('open_id') not in existing else None)
                ),
            },
        )
        return observed

    batches, current, size = [], [], 0
    for raw, encoded in zip(rows, prepared):
        amount = len(json.dumps(encoded, default=str).encode())
        if current and size + amount > 2 * 1024 * 1024:
            batches.append(current)
            current, size = [], 0
        current.append((raw, encoded))
        size += amount
    if current or not batches:
        batches.append(current)
    for index, batch in enumerate(batches):
        observed = commit(client.transaction(), [r for r, _ in batch], [r for _, r in batch], index == len(batches) - 1)
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
                owned = {'claims', 'v3_pending', 'v3_pending_since', 'v3_audio_purge_pending', 'backfill_superseded'}
                if recordings[rid].get('_v3_derive'):
                    # Our own committed conversion, not an external change.
                    owned |= {'recording', 'structured'}
                if {k: v for k, v in current.items() if k not in owned} != {
                    k: v for k, v in observed[rid].items() if k not in owned
                }:
                    # Claims are ours between batches; any other protected change still conflicts.
                    fence = recordings[rid].get('_v3_fence')
                    if fence is None or not speech_moved(
                        {**recordings[rid], '_v3_fence': {**fence, 'claims': current.get('claims')}}, current
                    ):
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
                    if any(current.get(k) != value for k, value in encoded.items()):
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
    ids = set(row.get('v3_recording_ids') or []) | {p['recording_id'] for p in row.get('recording_pieces') or []}

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
                    'v3_audio_purge_pending': not claims
                    and not recording.get('v3_pending')
                    and recording.get('status') == 'completed',
                },
            )

    remove(client.transaction())


def load_derive(uid, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid, firestore_client=client):
        raise Conflict('account_deletion')
    start = datetime.now(timezone.utc) - timedelta(days=30)
    # Query by time alone, then classify sources. Overflow is a blocked backfill,
    # never a claim that a partial 30-day history was converted.
    snapshots = list(
        user_conversations(client, uid).where(filter=FieldFilter('started_at', '>=', start)).limit(LIMIT + 1).stream()
    )
    if len(snapshots) > LIMIT:
        raise Conflict('backfill_window_budget; partition the operator job before enabling')
    rows = {}
    for snapshot in snapshots:
        row = decode_row(uid, snapshot)
        if (
            row
            and row.get('source') in {'omi', 'phone'}
            and row.get('status') == 'completed'
            and not any(row.get(k) for k in ('recording', 'v3_derived', 'deleted', 'sync_merged_into', 'is_locked'))
        ):
            rows[row['id']] = {**row, 'recording': True, '_v3_derive': True}
    return rows, {}, []


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


def outline_attempt(uid, token, fingerprint, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = leases.lease_ref(client, uid, 'builder')

    @firestore.transactional
    def begin(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or row.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(
            timezone.utc
        ):
            raise Conflict('lease_lost')
        attempts = dict(row.get('outline_attempts') or {})
        count = attempts.get(fingerprint, 0)
        if count >= 2:
            return False
        attempts[fingerprint] = count + 1
        tx.update(ref, {'outline_attempts': dict(list(attempts.items())[-128:])})
        return True

    return begin(client.transaction())
