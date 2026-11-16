"""Bounded v3 reads and transaction-fenced leases/claims.

Only lifecycle calls commit_projection. Speech uses the existing conversation
codec; cached outlines are encrypted. Nothing is cleared after a lost race.
"""

import copy
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database import conversations
from database.account_deletion_marker import account_deletion_blocks_user_work, account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.encryption import encrypt, decrypt

LIMIT = 128
LEASE_SECONDS = 240


class Conflict(RuntimeError):
    pass


def collection(client, uid):
    return client.collection('users').document(uid).collection('conversations')


def lease_ref(client, uid, key):
    return client.collection('users').document(uid).collection('conversation_v3_leases').document(key)


def acquire(uid, key, *, now=None, firestore_client=None):
    client = firestore_client or get_firestore_client()
    now = now or datetime.now(timezone.utc)
    token = uuid4().hex
    ref = lease_ref(client, uid, key)

    @firestore.transactional
    def claim(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if row.get('until') and row['until'] > now:
            return None
        tx.set(ref, {**row, 'token': token, 'until': now + timedelta(seconds=LEASE_SECONDS)})
        return token

    return claim(client.transaction())


def release(uid, key, token, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = lease_ref(client, uid, key)

    @firestore.transactional
    def finish(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') == token:
            tx.update(ref, {'until': datetime.now(timezone.utc), 'token': None})

    finish(client.transaction())


def _decode(uid, snapshot):
    data = snapshot.to_dict() or {}
    if not snapshot.exists:
        return None
    data.setdefault('id', snapshot.id)
    segments = conversations.decode_transcript_segments_verified(
        uid, data.get('transcript_segments') or [], bool(data.get('transcript_segments_compressed'))
    )
    data = conversations.prepare_conversation_for_read(data, uid)
    if data is not None:
        data['transcript_segments'] = segments
    if data is None:
        raise Conflict('recording_decode_unavailable')
    data['_v3_revision'] = snapshot.update_time
    return data


def load(uid, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    if account_deletion_blocks_user_work(uid):
        raise Conflict('account_deletion')
    coll = collection(client, uid)
    pending = list(coll.where(filter=FieldFilter('v3_pending', '==', True)).limit(LIMIT + 1).stream())
    if len(pending) > LIMIT:
        raise Conflict('v3_pending_budget')
    recordings = {doc.id: _decode(uid, doc) for doc in pending}
    if recordings:
        eligible = [r for r in recordings.values() if r and r.get('started_at')]
        active = [r for r in eligible if r.get('status') == 'in_progress']
        anchor = min(active or eligible, key=lambda r: r['started_at']) if eligible else None
        if anchor:
            start = anchor['started_at'] - timedelta(minutes=20)
            end = (anchor.get('finished_at') or anchor['started_at']) + timedelta(minutes=20)
            recordings = {
                cid: r
                for cid, r in recordings.items()
                if r
                and r.get('started_at')
                and r['started_at'] <= end
                and (r.get('finished_at') or r['started_at']) >= start
            }
    state = lease_ref(client, uid, 'builder').get().to_dict() or {}
    cache = json.loads(decrypt(state['outline_cache'], uid)) if state.get('outline_cache') else []
    if not recordings and not state.get('open_id'):
        return {}, {}, cache
    existing = {}
    if state.get('open_id'):
        opened = _decode(uid, coll.document(state['open_id']).get())
        if opened:
            existing[opened['id']] = opened
    queried = set()
    for _round in range(4):
        ids = {rid for row in existing.values() for rid in row.get('v3_recording_ids') or []}
        ids.update(
            p['recording_id']
            for row in existing.values()
            for p in row.get('recording_pieces') or []
            if p['recording_id'] != row['id']
        )
        if len(ids | recordings.keys()) > LIMIT:
            raise Conflict('v3_recording_budget')
        for rid in ids - recordings.keys():
            row = _decode(uid, coll.document(rid).get())
            if row:
                recordings[rid] = row
        fresh = [r for rid, r in recordings.items() if rid not in queried and r and r.get('started_at')]
        if not fresh:
            break
        # Query disjoint affected source windows separately: historical sync must
        # not scan every conversation between its recorded day and today's live row.
        intervals = []
        for row in sorted(fresh, key=lambda r: r['started_at']):
            left = row['started_at'] - timedelta(minutes=20)
            right = (row.get('finished_at') or row['started_at']) + timedelta(minutes=20)
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
                row = _decode(uid, doc)
                if row:
                    existing[row['id']] = row
            if len(snapshots) > LIMIT or len(existing) > LIMIT:
                raise Conflict('v3_derived_budget')
        queried.update(row['id'] for row in fresh)
    else:
        raise Conflict('v3_source_closure_budget')
    return recordings, existing, cache


def mark_pending(uid, cid, *, manual_end=False, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = collection(client, uid).document(cid)

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


def commit_projection(uid, token, recordings, existing, rows, cache, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    coll = collection(client, uid)
    held = lease_ref(client, uid, 'builder')
    prepared = []
    for row in rows:
        clean = {k: v for k, v in row.items() if not k.startswith('_v3_') and k != 'updated_at'}
        prepared.append(
            conversations._prepare_conversation_for_write(
                clean, uid, clean.get('data_protection_level') or 'standard', allow_offload=False
            )
        )
    encrypted_cache = encrypt(json.dumps(cache, default=str), uid)

    @firestore.transactional
    def commit(tx):
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
            if not snapshot.exists or snapshot.update_time != row['_v3_revision']:
                raise Conflict('source_changed')
        for row in rows:
            tombstone = (
                client.collection('users')
                .document(uid)
                .collection('deleted_conversations')
                .document(row['id'])
                .get(transaction=tx)
            )
            if tombstone.exists:
                raise Conflict('target_deleted')
        new_ids = {r['id'] for r in rows} - existing.keys()
        for cid in new_ids:
            if coll.document(cid).get(transaction=tx).exists:
                raise Conflict('target_exists')
        from database.recurring_voice_privacy import filter_processing_write

        user = client.collection('users').document(uid)
        for row in prepared:
            filter_processing_write(tx, user, row)
        for raw, row in zip(rows, prepared):
            if raw.get('deleted'):
                continue
            tx.set(coll.document(row['id']), row)
        for rid, recording in recordings.items():
            if recording.get('deleted') or recording.get('sync_merged_into'):
                tx.update(coll.document(rid), {'v3_pending': False, 'v3_pending_since': None})
                continue
            claims = [c for c in recording.get('claims') or [] if c['conversation_id'] not in existing]
            for row in rows:
                if rid not in row.get('v3_recording_ids', []) or row.get('deleted'):
                    continue
                spans = row.get('_v3_claims', {}).get(rid, [{'start': row['started_at'], 'end': row['finished_at']}])
                claims.extend({'conversation_id': row['id'], **span} for span in spans)
            tx.update(
                coll.document(rid),
                {
                    'claims': claims,
                    'v3_pending': False,
                    'v3_pending_since': None,
                    **(
                        {'recording': True, 'structured': {}, 'backfill_superseded': True}
                        if recording.get('_v3_derive')
                        else {}
                    ),
                },
            )
        open_ids = [r['id'] for r in rows if r['status'] == 'in_progress' and not r.get('deleted')]
        if len(open_ids) > 1:
            raise Conflict('multiple_open_conversations')
        tx.update(
            held,
            {
                'outline_cache': encrypted_cache,
                'open_id': (
                    open_ids[0]
                    if open_ids
                    else (lease.get('open_id') if lease.get('open_id') not in existing else None)
                ),
            },
        )

    commit(client.transaction())


def store_summary(uid, cid, token, revision, structured, covers, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref, held = collection(client, uid).document(cid), lease_ref(client, uid, 'summary-' + cid)
    patch = conversations._prepare_conversation_for_write(
        {'structured': structured}, uid, 'enhanced', allow_offload=False
    )

    @firestore.transactional
    def store(tx):
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
            or current.get('deleted')
            or current.get('is_locked')
            or snapshot.update_time != revision
            or lease.get('token') != token
            or not lease.get('until')
            or lease['until'] <= datetime.now(timezone.utc)
        ):
            raise Conflict('summary_source_changed')
        if current.get('title_locked'):
            patch['structured']['title'] = (current.get('structured') or {}).get('title', '')
            patch['structured']['emoji'] = (current.get('structured') or {}).get('emoji', '')
        tx.update(
            ref,
            {
                **patch,
                'summary_covers_through': covers,
                **(
                    {'title_locked': True}
                    if current.get('v3_derived') and not current.get('home_hidden') and patch['structured'].get('title')
                    else {}
                ),
            },
        )

    store(client.transaction())


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
    coll = collection(client, uid)
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
        collection(client, uid).where(filter=FieldFilter('started_at', '>=', start)).limit(LIMIT + 1).stream()
    )
    if len(snapshots) > LIMIT:
        raise Conflict('backfill_window_budget; partition the operator job before enabling')
    rows = {}
    for snapshot in snapshots:
        row = _decode(uid, snapshot)
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
    ref = collection(client, uid).document(rid)
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
    coll = collection(client, uid)
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


def settle_processing(uid, cid, token, revision, covers, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = collection(client, uid).document(cid)
    held = lease_ref(client, uid, 'summary-' + cid)

    @firestore.transactional
    def settle(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if (
            not row
            or row.get('deleted')
            or row.get('sync_content_revision') != revision
            or lease.get('token') != token
            or not lease.get('until')
            or lease['until'] <= datetime.now(timezone.utc)
        ):
            raise Conflict('processing_source_changed')
        tx.update(ref, {'v3_process_pending': False, 'tile_state': 'done', 'summary_covers_through': covers})

    settle(client.transaction())


def renew(uid, key, token, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    ref = lease_ref(client, uid, key)

    @firestore.transactional
    def extend(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        now = datetime.now(timezone.utc)
        if row.get('token') != token or not row.get('until') or row['until'] <= now:
            raise Conflict('lease_lost')
        tx.update(ref, {'until': now + timedelta(seconds=LEASE_SECONDS)})

    extend(client.transaction())
