"""Only the reserved synthetic account may receive canary records."""

import math
from typing import Any

from google.cloud import firestore

from config.dream_agent import canary_uid
from database._client import get_firestore_client, run_transactional

RECORD_ID = 'dream-canary-conversation'


def _is_safe_doc_id(doc_id: Any) -> bool:
    if not isinstance(doc_id, str):
        return False
    s = doc_id.strip()
    if not s or s != doc_id or len(s) > 128:
        return False
    if '/' in s or '\\' in s or '..' in s:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in s):
        return False
    return True


def _coerce_failure_count(val: Any) -> int:
    if val is None or isinstance(val, bool):
        return 0
    if isinstance(val, int):
        count = val
    elif isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return 0
        count = int(val)
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return 0
        try:
            f = float(s)
            if math.isnan(f) or math.isinf(f):
                return 0
            count = int(f)
        except (ValueError, OverflowError):
            return 0
    else:
        return 0
    return max(0, min(100, count))


def ensure_synthetic_owner(uid, *, firestore_client=None):
    expected = canary_uid()
    if not _is_safe_doc_id(uid) or not _is_safe_doc_id(expected) or uid != expected:
        raise ValueError('dream_canary_configuration')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    owner = database.collection('users').document(uid)

    @firestore.transactional
    def ensure(tx):
        snap = owner.get(transaction=tx)
        existing = snap.to_dict() if hasattr(snap, 'to_dict') else None
        if existing is not None:
            if not isinstance(existing, dict) or existing.get('dream_canary') is not True:
                raise ValueError('dream_canary_existing_owner')
        else:
            tx.set(owner, {'dream_canary': True})

    return run_transactional(database, ensure)


def reset_failures(*, firestore_client=None):
    """Operator skip is not a pass and must not keep the previous failure streak."""
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx):
        ref.get(transaction=tx)
        tx.set(ref, {'canary_failures': 0}, merge=True)
        return 0

    return run_transactional(database, update)


def failure_count(*, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snap = database.collection('dream_canary_health').document('current').get()
        row = snap.to_dict() if hasattr(snap, 'to_dict') else None
        if not isinstance(row, dict):
            row = {}
        return _coerce_failure_count(row.get('canary_failures'))
    except Exception:
        return 0


def record_result(passed, *, firestore_client=None):
    if not isinstance(passed, bool):
        raise ValueError('dream_canary_invalid_passed_type')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx):
        snap = ref.get(transaction=tx)
        state = snap.to_dict() if hasattr(snap, 'to_dict') else None
        if not isinstance(state, dict):
            state = {}
        failures = 0 if passed else min(100, _coerce_failure_count(state.get('canary_failures')) + 1)
        tx.set(ref, {'canary_failures': failures}, merge=True)
        return failures

    return run_transactional(database, update)
