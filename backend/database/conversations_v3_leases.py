"""Renewable token leases shared by builder and foreground/background writers."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from contextlib import contextmanager
import logging
import threading
from time import monotonic
from google.cloud import firestore
from database._client import get_firestore_client
from utils.conversations.v3 import Conflict

LEASE_SECONDS = 240
logger = logging.getLogger(__name__)


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


@contextmanager
def keepalive(uid, key, token):
    """Own and join the heartbeat of synchronous reprocess/merge writers."""
    stop = threading.Event()
    deadline = monotonic() + 900

    def heartbeat():
        failures, delay = 0, LEASE_SECONDS / 3
        while not stop.wait(delay):
            if monotonic() >= deadline:
                return
            try:
                renew(uid, key, token)
                failures, delay = 0, LEASE_SECONDS / 3
            except Exception as exc:
                # Persistence still checks the token and expiry. A transient
                # read fault must not cancel a paid call while its lease holds.
                logger.warning('event=v3_lease_renewal outcome=error exception_type=%s', type(exc).__name__)
                failures += 1
                if isinstance(exc, Conflict) or failures >= 3:
                    return
                delay = 2 ** (failures - 1)

    worker = threading.Thread(target=heartbeat, name='v3-writer-lease', daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join()
