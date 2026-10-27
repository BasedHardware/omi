"""Bounded required-intake scans rotate without creating a second work queue."""

from datetime import datetime
from google.cloud import firestore

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.memory_collections import MemoryCollections
from database.required_intake_fence import assert_account_active


def _ref(uid, phase, client):
    if phase not in {'retry', 'completion'}:
        raise ValueError('required_intake_cursor_phase')
    return client.document(f'{MemoryCollections(uid=uid).memory_runs}/required_intake_{phase}_scan')


def load(uid, phase, *, db_client):
    before = _ref(uid, phase, db_client).get(timeout=3).to_dict() or None
    control = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state).get(timeout=3).to_dict() or {}
    cursor = (
        before
        if (
            isinstance(before, dict)
            and set(before) == {'captured_at', 'memory_id'}
            and isinstance(before['captured_at'], datetime)
            and isinstance(before['memory_id'], str)
        )
        else None
    )
    return before, cursor, control.get('account_generation')


def finish(uid, phase, before, after, generation, *, db_client):
    ref = _ref(uid, phase, db_client)

    @firestore.transactional
    def commit(tx):
        assert_account_active(uid, tx, db_client)
        control = (
            db_client.document(MemoryCollections(uid=uid).memory_apply_control_state).get(transaction=tx).to_dict()
            or {}
        )
        current = ref.get(transaction=tx).to_dict() or None
        if generation is not None and control.get('account_generation') == generation and current == before:
            # Reset with an empty metadata document; never delete source data.
            tx.set(ref, after or {})

    run_with_transaction_contention_retry(db_client.transaction, commit, operation_name='required_intake_scan_cursor')
