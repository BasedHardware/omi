"""Conservative blocks of minute slots; no quota RPC on the steady write path."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client, run_transactional
from database.legal_holds import external_write_fence
from utils.sync.live_cap_codec import MAX_OBJECT_BYTES

BLOCK_GROUPS = 64
SLOT_BYTES = MAX_OBJECT_BYTES + 128  # Four authenticated fragment encryption frames.
BLOCK_BYTES = (BLOCK_GROUPS + 1) * SLOT_BYTES  # One active group may coexist with its composed source.
MAX_MONTHLY_BYTES = 8 * 1024**3
MAX_MONTHLY_GROUPS = 100_000


@dataclass
class Capacity:
    uid: str
    month: str
    identity: str
    used: int = 0

    def consume(self) -> None:
        if self.used >= BLOCK_GROUPS:
            raise ValueError('held capacity block exhausted')
        self.used += 1  # Consume only after a reconciled durable publication receipt.


def acquire(uid: str, month: str, identity: str | None = None) -> Capacity:
    client = get_firestore_client()
    identity = identity or uuid4().hex
    quota = client.collection('users').document(uid).collection('stt_cap_live_storage').document(month)
    lease = quota.collection('reservations').document(identity)

    @firestore.transactional
    def commit(tx: Any) -> None:
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            _acquire(tx)

    def _acquire(tx: Any) -> None:
        previous = lease.get(transaction=tx)
        if previous.exists:
            if previous.to_dict().get('closed'):
                raise ValueError('held capacity lease already closed')
            return
        snapshot = quota.get(transaction=tx)
        row = (snapshot.to_dict() or {}) if snapshot.exists else {}
        size, groups = row.get('bytes', 0) + BLOCK_BYTES, row.get('chunks', 0) + BLOCK_GROUPS
        if size > MAX_MONTHLY_BYTES or groups > MAX_MONTHLY_GROUPS:
            raise RuntimeError('live held audio storage capacity reached')
        tx.set(quota, {'bytes': size, 'chunks': groups}, merge=True)
        tx.create(lease, {'groups': BLOCK_GROUPS, 'bytes': BLOCK_BYTES, 'closed': False})

    # Idempotent on the reservation id: a deadline after commit sees the lease and
    # does not add the block twice. Backoff stays off the event loop; acquire
    # runs on the database executor and holds no session lock.
    run_transactional(client, commit, transient=True)
    return Capacity(uid, month, identity)


def release(capacity: Capacity) -> None:
    if capacity.used == BLOCK_GROUPS:
        return  # The block is fully reserved; no refund or extra write needed.
    client = get_firestore_client()
    quota = (
        client.collection('users').document(capacity.uid).collection('stt_cap_live_storage').document(capacity.month)
    )
    lease = quota.collection('reservations').document(capacity.identity)

    @firestore.transactional
    def commit(tx: Any) -> None:
        with external_write_fence(capacity.uid, firestore_client=client, transaction=tx):
            _release(tx)

    def _release(tx: Any) -> None:
        snapshot = lease.get(transaction=tx)
        if not snapshot.exists or snapshot.to_dict().get('closed'):
            return
        current = quota.get(transaction=tx)
        row = current.to_dict() or {}
        unused = BLOCK_GROUPS - capacity.used
        refund_bytes = max(0, snapshot.to_dict().get('bytes', BLOCK_GROUPS * SLOT_BYTES) - capacity.used * SLOT_BYTES)
        tx.update(quota, {'bytes': max(0, row['bytes'] - refund_bytes), 'chunks': max(0, row['chunks'] - unused)})
        tx.update(lease, {'closed': True, 'groups': capacity.used})

    run_transactional(client, commit, transient=True)
