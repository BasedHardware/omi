"""Only the reserved synthetic account may receive canary records."""

from google.cloud import firestore

from config.dream_agent import canary_uid
from database._client import get_firestore_client

RECORD_ID = 'dream-canary-conversation'


def ensure_synthetic_owner(uid, *, firestore_client=None):
    if not uid or uid != canary_uid():
        raise ValueError('dream_canary_configuration')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    owner = database.collection('users').document(uid)

    @firestore.transactional
    def ensure(tx):
        existing = owner.get(transaction=tx).to_dict()
        if existing is not None and existing.get('dream_canary') is not True:
            raise ValueError('dream_canary_existing_owner')
        if existing is None:
            tx.set(owner, {'dream_canary': True})

    ensure(database.transaction())


def reset_failures(*, firestore_client=None):
    """Operator skip is not a pass and must not keep the previous failure streak."""
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx):
        ref.get(transaction=tx)
        tx.set(ref, {'canary_failures': 0}, merge=True)
        return 0

    return update(database.transaction())


def failure_count(*, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    row = database.collection('dream_canary_health').document('current').get().to_dict() or {}
    return int(row.get('canary_failures', 0))


def record_result(passed, *, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx):
        state = ref.get(transaction=tx).to_dict() or {}
        failures = 0 if passed else min(100, int(state.get('canary_failures', 0)) + 1)
        tx.set(ref, {'canary_failures': failures}, merge=True)
        return failures

    return update(database.transaction())
