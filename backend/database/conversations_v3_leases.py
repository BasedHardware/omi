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


def acquire(uid, key, *, promote_llm=False, now=None, firestore_client=None):
    client = firestore_client or get_firestore_client()
    now = now or datetime.now(timezone.utc)
    token = uuid4().hex
    ref = lease_ref(client, uid, key)

    @firestore.transactional
    def claim(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if row.get('until') and row['until'] > now:
            if not (promote_llm and row.get('llm_preemptible') is True):
                return None
        row.pop('llm_preemptible', None)
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


def held(uid, key, *, now=None, firestore_client=None):
    """True while some writer holds this lease (read only)."""
    client = firestore_client or get_firestore_client()
    row = lease_ref(client, uid, key).get().to_dict() or {}
    return bool(row.get('token') and row.get('until') and row['until'] > (now or datetime.now(timezone.utc)))


def mark_llm_preemptible(uid, key, token, preemptible, *, firestore_client=None):
    """Limit takeover to the paid call and discard a result if foreground took over."""
    client = firestore_client or get_firestore_client()
    ref = lease_ref(client, uid, key)

    @firestore.transactional
    def finish(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or not row.get('until') or row['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        tx.update(ref, {'llm_preemptible': preemptible})

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
def keepalive(uid, key, token, *, firestore_client=None, max_seconds: int | None = 900):
    """Own and join the heartbeat of a synchronous writer."""
    stop = threading.Event()
    deadline = monotonic() + max_seconds if max_seconds is not None else None
    client_args = {'firestore_client': firestore_client} if firestore_client is not None else {}

    def heartbeat():
        failures, delay = 0, LEASE_SECONDS / 3
        while not stop.wait(delay):
            if deadline is not None and monotonic() >= deadline:
                return
            try:
                renew(uid, key, token, **client_args)
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
