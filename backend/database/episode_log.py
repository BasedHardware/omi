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
MAX_FACT_BYTES = 65_536
FACT_RETENTION = timedelta(days=1)


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
    if (
        int(state.get('cursor', 0)) >= int(state.get('next_seq', 0))
        and not state.get('policy_barriers')
        and not state.get('capture_dirty')
    ):
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
    """Independent log transaction only; never use in a serving transaction."""

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
        from utils.episodes.log.facts import compact_events

        payload = encrypt(dumps(compact_events(events)), self.uid)
        if len(payload.encode()) > MAX_FACT_BYTES:
            raise ProjectionCapacity('episode_fact_too_large')
        self.transaction.create(
            self.root.collection('episode_facts').document(key),
            {'key': key, 'seq': seq, 'recorded_at': now, 'expires_at': now + FACT_RETENTION, 'payload': payload},
        )
        self.state = dirty_state(self.state, now)
        if urgent:
            self.state['drain_at'] = now
            self.state['scan_at'] = max(now, self.state.get('lease_until') or now)
        self.transaction.set(self.ref, self.state)


def prepare(transaction, client, uid):
    # Recording intent is IO-free. Remote admission is checked after commit.
    from utils.episodes.log.capture import prepare_capture

    return prepare_capture(transaction, client, uid)


def mutation(capture, *, before=(), after=(), span=None, links=None, receipts=None, changed_fields=None):
    volatile = {'state_version', 'updated_at', 'state_updated_at', 'compose_lease', 'compose_attempted_at'}

    if changed_fields is not None and not set(changed_fields) - volatile and not (receipts or links or span):
        return

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
    from utils.episodes.log import retention

    retention.require_active(client)

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

    return run_transactional(client, commit, attempts=1, initial_transaction=client.transaction(max_attempts=2))


def state(uid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return owner_ref(client, uid).get().to_dict() or {}


def invalidate(uid, *, firestore_client=None, now=None, cid=None, token=None):
    """A capture gap survives ordinary drains, restarts and concurrent publishers."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def commit(transaction):
        if not account_allowed(uid, firestore_client=client, transaction=transaction):
            return
        ref = owner_ref(client, uid)
        row = ref.get(transaction=transaction).to_dict() or {}
        if cid and token:
            row['policy_barriers'] = {
                **(row.get('policy_barriers') or {}),
                token: {'cid': cid, 'entered_at': now, 'deadline_at': now + timedelta(seconds=config.MAX_AGE_SECONDS)},
            }
        transaction.set(
            ref,
            dict(
                row,
                capture_dirty=uuid4().hex,
                next_seq=int(row.get('next_seq', 0)),
                cursor=int(row.get('cursor', 0)),
                home_rows_ready=False,
                epoch=int(row.get('epoch', 0)) + 1,
                lease_owner=None,
                lease_until=None,
                drain_at=now,
                scan_at=now,
            ),
        )

    return run_transactional(client, commit, attempts=1, initial_transaction=client.transaction(max_attempts=2))


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


def publish(
    uid,
    claimed,
    cursor,
    fold_state,
    views,
    links,
    *,
    firestore_client=None,
    now=None,
    home_clock=None,
    repaired=False,
    removed_views=(),
    removed_links=(),
):
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
        or len(views) + len(links) + len(removed_views) + len(removed_links) > MAX_PUBLISH_ROWS
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
        if repaired and (
            row.get('capture_dirty') != claimed['state'].get('capture_dirty')
            or row.get('next_seq', 0) != claimed['state'].get('next_seq', 0)
            or row.get('policy_barriers')
        ):
            raise LostLease('episode_reconcile_changed_during_read')
        # Caller already sealed every speech-derived field and Home payload.
        for eid, view in views.items():
            transaction.set(root(client, uid).collection('episode_views').document(eid), view)
        for cid, link in links.items():
            transaction.set(root(client, uid).collection('episode_view_links').document(cid), link)
        for eid in removed_views:
            transaction.delete(root(client, uid).collection('episode_views').document(eid))
        for cid in removed_links:
            transaction.delete(root(client, uid).collection('episode_view_links').document(cid))
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
            home_version=int(row.get('home_version', 0)) + bool(views or removed_views or repaired),
            projected_at=now,
            home_rows_ready=config.home_enabled(),
            home_member_clocks=home_clock.get('members') or {},
            home_valid_until=home_clock.get('deadline_at'),
            home_refresh_cid=home_clock.get('cid'),
        )
        if repaired:
            result.pop('capture_dirty', None)
        if result.get('capture_dirty'):
            result['home_rows_ready'] = False
        if cursor == row['next_seq']:
            barriers = list((row.get('policy_barriers') or {}).values())
            first = min((value['entered_at'] for value in barriers), default=None)
            deadline = min((value['deadline_at'] for value in barriers), default=None)
            result.update(
                pending_since=first,
                queued_entered_at=first,
                queued_deadline_at=deadline,
                drain_at=deadline,
                scan_at=deadline,
            )
        else:
            result.update(drain_at=now, scan_at=now)
        if result.get('capture_dirty'):
            result.update(drain_at=now, scan_at=now)
        elif cursor == row.get('next_seq', 0) and not row.get('policy_barriers'):
            result.pop('scan_at', None)
            result.pop('drain_at', None)
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
        if derive_phase(row, now) == 'idle':
            row.pop('scan_at', None)
            row.pop('drain_at', None)
            transaction.set(ref, row)
            return False
        transaction.update(ref, {'scan_at': now + timedelta(seconds=config.SWEEP_REDRIVE_SECONDS)})
        return True

    return run_transactional(client, commit, transient=True)


def policy_barrier(uid, cid, token, *, entering, firestore_client=None, now=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)
    from utils.episodes.log import retention

    retention.require_active(client)

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

    return run_transactional(client, commit, attempts=1, initial_transaction=client.transaction(max_attempts=2))


def recover_policy_barriers(uid, *, firestore_client=None, now=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)
    from utils.episodes.log import retention

    retention.require_active(client)

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
    from utils.episodes.log import retention

    retention.require_active(client)

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
    """Register an IO-free post-commit refresh for sync/smart-merge writers."""
    capture = prepare(transaction, getattr(transaction, '_client', None), user_ref.id) if user_ref is not None else None
    if capture is not None:
        capture.existing_only = True
    return capture


def member_changed(capture, cids):
    if capture is not None:
        capture.stage([{'kind': 'member_refresh', 'cid': cid, 'payload': {}} for cid in sorted(set(cids))])
