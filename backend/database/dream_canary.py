"""Only the reserved synthetic account may receive canary records."""

import logging
import math
from typing import Any, Dict, Optional, cast

from google.cloud import firestore

from config.dream_agent import canary_uid
from database._client import get_firestore_client, run_transactional

logger = logging.getLogger(__name__)

RECORD_ID = 'dream-canary-conversation'


def _is_safe_doc_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    cleaned = value.strip()
    if (
        not cleaned
        or cleaned != value
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        return False
    return True


def _coerce_failure_count(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return min(100, max(0, value))
    if isinstance(value, float):
        if not math.isfinite(value):
            return 0
        return min(100, max(0, int(value)))
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
            return min(100, max(0, parsed))
        except ValueError:
            return 0
    return 0


def ensure_synthetic_owner(uid: Any, *, firestore_client: Optional[Any] = None) -> None:
    expected = canary_uid()
    if not _is_safe_doc_id(uid) or not _is_safe_doc_id(expected) or uid != expected:
        raise ValueError('dream_canary_configuration')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    owner = database.collection('users').document(uid)

    @firestore.transactional
    def ensure(tx: Any) -> None:
        snapshot = owner.get(transaction=tx)
        raw_existing: object = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
        if raw_existing is not None:
            if not isinstance(raw_existing, dict) or raw_existing.get('dream_canary') is not True:
                raise ValueError('dream_canary_existing_owner')
        else:
            tx.set(owner, {'dream_canary': True})

    run_transactional(database, ensure)


def reset_failures(*, firestore_client: Optional[Any] = None) -> int:
    """Operator skip is not a pass and must not keep the previous failure streak."""
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx: Any) -> int:
        ref.get(transaction=tx)
        tx.set(ref, {'canary_failures': 0}, merge=True)
        return 0

    return int(run_transactional(database, update))


def failure_count(*, firestore_client: Optional[Any] = None) -> int:
    database = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snapshot = database.collection('dream_canary_health').document('current').get()
    except Exception as exc:
        logger.warning('Failed to read dream canary health: %s', exc)
        return 0
    raw_row: object = snapshot.to_dict() if getattr(snapshot, 'exists', True) else {}
    row: Dict[str, Any] = cast(Dict[str, Any], raw_row) if isinstance(raw_row, dict) else {}
    return _coerce_failure_count(row.get('canary_failures', 0))


def record_result(passed: Any, *, firestore_client: Optional[Any] = None) -> int:
    if not isinstance(passed, bool):
        raise ValueError('passed must be a boolean')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx: Any) -> int:
        snapshot = ref.get(transaction=tx)
        raw_state: object = snapshot.to_dict() if getattr(snapshot, 'exists', True) else {}
        state: Dict[str, Any] = cast(Dict[str, Any], raw_state) if isinstance(raw_state, dict) else {}
        current_failures = _coerce_failure_count(state.get('canary_failures', 0))
        failures = 0 if passed else min(100, current_failures + 1)
        tx.set(ref, {'canary_failures': failures}, merge=True)
        return failures

    return int(run_transactional(database, update))
