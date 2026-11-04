"""Append-only episode facts and epoch-fenced shadow publication under users/{uid}.

No helper in this module writes an episode, conversation, legacy link or receipt.
A bounded single-field sequence query drains facts. The owner document is both the
append sequencer and durable dirty mark, mirroring sync's UID sequencer.
"""

import base64
import zlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config import episode_log as config
from database._client import get_firestore_client, run_transactional
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.encryption import encrypt, decrypt
from utils.episodes.log.codec import dumps, loads, digest

STATE_COLLECTION = 'episode_log_state'
STATE_ID = 'owner'
CHECKPOINT_CHUNK_BYTES = 200_000
MAX_CHECKPOINT_PARTS = 24
MAX_TRANSACTION_BYTES = 8_000_000
MAX_PUBLISH_ROWS = 128


class LostLease(RuntimeError):
    pass


class ProjectionCapacity(RuntimeError):
    pass


class AccountBlocked(RuntimeError):
    pass


def account_allowed(uid, *, firestore_client, transaction=None):
    """Uncached, transaction-bound fence on the same customer data plane.

    The durable authority survives recursive erasure. Reading it in publication
    serializes an already-running worker against accepted deletion, so it cannot
    recreate views after their collection has been swept.
    """
    snapshot = account_deletion_document(uid, firestore_client=firestore_client).get(transaction=transaction)
    return not account_deletion_marker_blocks_access(
        marker_exists=snapshot.exists, raw_status=(snapshot.to_dict() or {}).get('wipe_status')
    )


def root(client, uid):
    return client.collection('users').document(uid)


def owner_ref(client, uid):
    return root(client, uid).collection(STATE_COLLECTION).document(STATE_ID)


def derive_phase(state, now):
    """Pure job phase from log watermarks and lease facts, never a status field."""
    if int(state.get('cursor', 0)) >= int(state.get('next_seq', 0)) and not state.get('policy_barriers'):
        return 'idle'
    if state.get('lease_owner') and state.get('lease_until') and state['lease_until'] > now:
        return 'running'
    if state.get('retry_at'):
        return 'retrying'
    return 'queued'


def dirty_state(state, now, *, count=1):
    result = dict(state)
    first = state.get('pending_since') if state.get('next_seq', 0) > state.get('cursor', 0) else None
    first = first or now
    result.update(
        next_seq=int(state.get('next_seq', 0)) + count,
        pending_since=first,
        activity_at=now,
        queued_entered_at=state.get('queued_entered_at') if first != now else now,
        queued_deadline_at=first + timedelta(seconds=config.MAX_AGE_SECONDS),
    )
    result['drain_at'] = min(now + timedelta(seconds=config.DEBOUNCE_SECONDS), result['queued_deadline_at'])
    if result['next_seq'] - int(result.get('cursor', 0)) >= config.BATCH_SIZE:
        result['drain_at'] = now
    result['scan_at'] = max(result['drain_at'], result.get('lease_until') or now)
    return result


class Capture:
    """Prepare before the first legacy write; stage after all legacy reads."""

    def __init__(self, transaction, client, uid, *, user_ref=None):
        self.transaction, self.client, self.uid = transaction, client, uid
        self.root = user_ref if user_ref is not None else root(client, uid)
        self.ref = self.root.collection(STATE_COLLECTION).document(STATE_ID)
        self.state = self.ref.get(transaction=transaction).to_dict() or {}

    def stage(self, events, *, key=None, now=None, urgent=False):
        now = now or datetime.now(timezone.utc)
        seq = int(self.state.get('next_seq', 0)) + 1
        # Input facts use the exact attach gate digest. Decision facts also need
        # unique keys when identical domain state recurs after a reopen/restore.
        key = key or digest({'events': events, 'seq': seq})
        payload = encrypt(dumps(events), self.uid)
        if len(payload.encode()) > 800_000:
            raise ProjectionCapacity('episode_fact_too_large')
        self.transaction.create(
            self.root.collection('episode_facts').document(key),
            {'key': key, 'seq': seq, 'recorded_at': now, 'payload': payload},
        )
        self.state = dirty_state(self.state, now)
        if urgent:
            self.state['drain_at'] = now
            self.state['scan_at'] = max(now, self.state.get('lease_until') or now)
        self.transaction.set(self.ref, self.state)


def prepare(transaction, client, uid):
    return Capture(transaction, client, uid) if config.enabled(uid) else None


def mutation(capture, *, before=(), after=(), span=None, links=None, receipts=None):
    volatile = {'state_version', 'updated_at', 'state_updated_at', 'compose_lease', 'compose_attempted_at'}

    def domain(rows):
        return [{key: value for key, value in row.items() if key not in volatile} for row in rows]

    if capture is not None and (domain(before) != domain(after) or receipts or links or span):
        capture.stage(
            [
                {
                    'kind': 'mutation',
                    'payload': {
                        'before': list(before),
                        'after': list(after),
                        'span': span,
                        'links': links or {},
                        'receipts': receipts or {},
                    },
                }
            ]
        )


def append(uid, key, events, *, firestore_client=None, now=None, urgent=False):
    if not config.enabled(uid):
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            return None
        capture = Capture(transaction, client, uid)
        exists = root(client, uid).collection('episode_facts').document(key).get(transaction=transaction).exists
        if exists:
            return None
        capture.stage(events, key=key, now=now, urgent=urgent)
        return capture.state['drain_at']

    return run_transactional(client, commit, transient=True)


def state(uid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return owner_ref(client, uid).get().to_dict() or {}


def claim(uid, *, firestore_client=None, now=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)
    token = uuid4().hex

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            return None
        ref = owner_ref(client, uid)
        row = ref.get(transaction=transaction).to_dict() or {}
        if derive_phase(row, now) in {'idle', 'running'} or row['drain_at'] > now:
            return None
        prior = dict(row)
        row.update(
            lease_owner=token,
            epoch=int(row.get('epoch', 0)) + 1,
            lease_until=now + timedelta(seconds=config.LEASE_SECONDS),
            running_entered_at=now,
            retry_at=None,
        )
        row['scan_at'] = row['lease_until']
        transaction.set(ref, row)
        return {'state': row, 'prior': prior, 'token': token, 'epoch': row['epoch']}

    return run_transactional(client, commit, transient=True)


def fact_page(uid, after, through, *, limit=config.BATCH_SIZE, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        root(client, uid)
        .collection('episode_facts')
        .where(filter=FieldFilter('seq', '>', after))
        .where(filter=FieldFilter('seq', '<=', through))
        .order_by('seq')
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


def read_batch(uid, claimed, *, firestore_client=None):
    row = claimed['state']
    start = int(row.get('cursor', 0)) + 1
    end = min(int(row['next_seq']), start + config.BATCH_SIZE - 1)
    page = fact_page(uid, start - 1, end, firestore_client=firestore_client)
    facts = []
    if len(page) != end - start + 1:
        raise ValueError('episode_fact_sequence_gap')
    for seq, fact in enumerate(page, start):
        if fact.get('seq') != seq:
            raise ValueError('episode_fact_sequence_gap')
        facts.extend(loads(decrypt(fact['payload'], uid)))
    return facts, end


def checkpoint(uid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = root(client, uid).collection('episode_log_checkpoint')
    row = collection.document('fold').get().to_dict() or {}
    if not row:
        return None
    chunks = []
    for index in range(row['parts']):
        part = collection.document(f'part-{index}').get().to_dict() or {}
        if part.get('cursor') != row['cursor'] or part.get('epoch') != row['epoch']:
            raise LostLease('episode_checkpoint_changed_during_read')
        chunks.append(decrypt(part['payload'], uid))
    return loads(zlib.decompress(base64.b64decode(''.join(chunks))).decode())


def publish(uid, claimed, cursor, fold_state, views, links, *, firestore_client=None, now=None, home_clock=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)
    home_clock = home_clock or {}
    packed = base64.b64encode(zlib.compress(dumps(fold_state).encode())).decode()
    parts = [
        encrypt(packed[offset : offset + CHECKPOINT_CHUNK_BYTES], uid)
        for offset in range(0, len(packed), CHECKPOINT_CHUNK_BYTES)
    ]
    transaction_bytes = sum(len(value.encode()) for value in parts) + len(
        dumps({'views': views, 'links': links}).encode()
    )
    if (
        len(parts) > MAX_CHECKPOINT_PARTS
        or len(views) + len(links) > MAX_PUBLISH_ROWS
        or transaction_bytes > MAX_TRANSACTION_BYTES
    ):
        raise ProjectionCapacity('episode_projection_capacity')

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            raise LostLease('episode_account_deletion_fenced')
        ref = owner_ref(client, uid)
        row = ref.get(transaction=transaction).to_dict() or {}
        if (
            row.get('epoch') != claimed['epoch']
            or row.get('lease_owner') != claimed['token']
            or not row.get('lease_until')
            or row['lease_until'] <= now
        ):
            raise LostLease('episode_drain_lease_lost')
        # Caller already sealed every speech-derived field and Home payload.
        for eid, view in views.items():
            transaction.set(root(client, uid).collection('episode_views').document(eid), view)
        for cid, link in links.items():
            transaction.set(root(client, uid).collection('episode_view_links').document(cid), link)
        checkpoints = root(client, uid).collection('episode_log_checkpoint')
        for index, part in enumerate(parts):
            transaction.set(
                checkpoints.document(f'part-{index}'), {'payload': part, 'cursor': cursor, 'epoch': claimed['epoch']}
            )
        transaction.set(
            checkpoints.document('fold'), {'parts': len(parts), 'cursor': cursor, 'epoch': claimed['epoch']}
        )
        result = dict(
            row,
            cursor=cursor,
            lease_owner=None,
            lease_until=None,
            retry_at=None,
            home_version=int(row.get('home_version', 0)) + bool(views),
            projected_at=now,
            home_rows_ready=config.home_enabled(),
            home_member_clocks=home_clock.get('members') or {},
            home_valid_until=home_clock.get('deadline_at'),
            home_refresh_cid=home_clock.get('cid'),
        )
        if cursor == row['next_seq']:
            barriers = list((row.get('policy_barriers') or {}).values())
            first = min((value['entered_at'] for value in barriers), default=None)
            deadline = min((value['deadline_at'] for value in barriers), default=None)
            result.update(
                pending_since=first,
                queued_entered_at=first,
                queued_deadline_at=deadline,
                drain_at=deadline if barriers else row.get('drain_at'),
                scan_at=deadline,
            )
        else:
            result.update(drain_at=now, scan_at=now)
        transaction.set(ref, result)
        return result

    return run_transactional(client, commit, transient=True)


def retry(uid, claimed, *, firestore_client=None, now=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def commit(transaction):
        ref = owner_ref(client, uid)
        row = ref.get(transaction=transaction).to_dict() or {}
        if row.get('epoch') != claimed['epoch'] or row.get('lease_owner') != claimed['token']:
            return False
        deadline = now + timedelta(seconds=config.RETRY_SECONDS)
        transaction.set(
            ref,
            dict(
                row,
                lease_owner=None,
                lease_until=None,
                retry_at=deadline,
                retrying_entered_at=now,
                drain_at=deadline,
                scan_at=deadline,
            ),
        )
        return True

    return run_transactional(client, commit, transient=True)


def due_owners(now, *, limit=config.SWEEP_SIZE, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection_group(STATE_COLLECTION)
        .where(filter=FieldFilter('scan_at', '<=', now))
        .order_by('scan_at')
        .limit(limit)
    )
    return [(doc.reference.parent.parent.id, doc.to_dict()) for doc in query.stream()]


def redrive_scan(uid, observed, *, firestore_client=None, now=None):
    """Rotate a bounded sweep page, including disabled or failing users.

    Only discovery moves: drain_at and all phase deadlines stay intact. A
    concurrent append/claim wins instead of having its scan deadline replaced.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def commit(transaction):
        ref = owner_ref(client, uid)
        row = ref.get(transaction=transaction).to_dict() or {}
        if any(row.get(key) != observed.get(key) for key in ('scan_at', 'epoch', 'next_seq', 'cursor')):
            return False
        transaction.update(ref, {'scan_at': now + timedelta(seconds=config.SWEEP_REDRIVE_SECONDS)})
        return True

    return run_transactional(client, commit, transient=True)


def policy_barrier(uid, cid, token, *, entering, firestore_client=None, now=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            raise AccountBlocked('episode_account_deletion_fenced')
        capture = Capture(transaction, client, uid)
        barriers = dict(capture.state.get('policy_barriers') or {})
        if entering:
            barriers[token] = {
                'cid': cid,
                'entered_at': now,
                'deadline_at': now + timedelta(seconds=config.MAX_AGE_SECONDS),
            }
        else:
            barriers.pop(token, None)
        capture.state['policy_barriers'] = barriers
        capture.stage([{'kind': 'member_refresh', 'cid': cid, 'payload': {}}], now=now)

    return run_transactional(client, commit, transient=True)


def recover_policy_barriers(uid, *, firestore_client=None, now=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            return None
        capture = Capture(transaction, client, uid)
        barriers = dict(capture.state.get('policy_barriers') or {})
        expired = {token: value for token, value in barriers.items() if value['deadline_at'] <= now}
        if not expired:
            return
        prior = dict(capture.state)
        capture.state['policy_barriers'] = {token: value for token, value in barriers.items() if token not in expired}
        capture.stage(
            [
                {'kind': 'member_refresh', 'cid': cid, 'payload': {}}
                for cid in sorted({value['cid'] for value in expired.values()})
            ],
            now=now,
        )
        capture.state.update(drain_at=now, scan_at=now)
        transaction.set(capture.ref, capture.state)
        return prior

    return run_transactional(client, commit, transient=True)


def finish_backfill(uid, *, firestore_client=None):
    """Marker is in the same sequencer: reads wait until its watermark is drained."""
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            raise AccountBlocked('episode_account_deletion_fenced')
        capture = Capture(transaction, client, uid)
        capture.state['backfill_complete'] = True
        capture.state['backfill_watermark'] = int(capture.state.get('next_seq', 0)) + 1
        capture.stage([{'kind': 'backfill_complete', 'payload': {}}])

    return run_transactional(client, commit, transient=True)


def prepare_member_change(transaction, user_ref):
    """Atomic policy invalidation for sync/smart-merge writers bypassing CRUD.

    Only users with an existing episode log pay a dirty write. The new fact
    is part of the conversation transaction, so ready reads cannot race a
    committed discard, donor redirect or changed member title.
    """
    if not config.enabled(user_ref.id):
        return None
    capture = Capture(transaction, None, user_ref.id, user_ref=user_ref)
    return capture if capture.state else None


def member_changed(capture, cids):
    if capture is not None:
        capture.stage([{'kind': 'member_refresh', 'cid': cid, 'payload': {}} for cid in sorted(set(cids))])
