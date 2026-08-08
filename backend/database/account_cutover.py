"""Firestore persistence for whole-account cutover control documents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional, cast

from database._client import get_firestore_client
from database.read_boundary import parse_snapshot_strict
from models.account_cutover import AccountCutoverRecord, AccountCutoverState

CONTROL_COLLECTION = 'account_cutover'
CONTROL_DOCUMENT = 'state'


class AccountCutoverConcurrencyError(RuntimeError):
    """Raised when a CAS write loses a generation/token race, or CAS is unsupported."""

    def __init__(self, message: str = 'cutover concurrency conflict', *, code: str = 'cutover_concurrency_conflict'):
        super().__init__(message)
        self.code = code


def _control_ref(uid: str, *, firestore_client: Any = None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid).collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)


def default_legacy_record(uid: str) -> AccountCutoverRecord:
    return AccountCutoverRecord(uid=uid, state=AccountCutoverState.legacy)


def _read_current_generation_and_token(
    snapshot: Any,
    *,
    require_existing: bool,
) -> tuple[int, Optional[str]]:
    if getattr(snapshot, 'exists', False) is not True:
        if require_existing:
            raise AccountCutoverConcurrencyError(
                'cutover document missing during CAS write',
                code='cutover_missing_during_cas',
            )
        return 0, None
    current = parse_snapshot_strict(AccountCutoverRecord, snapshot)
    return current.account_generation, current.checkpoint_token


def _assert_cas_matches(
    *,
    current_generation: int,
    current_token: Optional[str],
    expected_account_generation: int,
    expected_checkpoint_token: Optional[str],
) -> None:
    if current_generation != expected_account_generation:
        raise AccountCutoverConcurrencyError(
            f'account generation CAS mismatch expected={expected_account_generation} actual={current_generation}',
            code='cutover_generation_cas_mismatch',
        )
    if expected_checkpoint_token is not None and current_token != expected_checkpoint_token:
        raise AccountCutoverConcurrencyError(
            'checkpoint token CAS mismatch',
            code='cutover_checkpoint_cas_mismatch',
        )


def get_account_cutover_record(uid: str, *, firestore_client: Any = None) -> AccountCutoverRecord:
    """Return the persisted cutover record, or an implicit legacy default.

    Missing documents remain legacy-compatible. Existing but malformed documents
    fail closed via ``MalformedDocError`` — they must not silently project as
    legacy and reopen product traffic.
    """

    snapshot = _control_ref(uid, firestore_client=firestore_client).get()
    if getattr(snapshot, 'exists', False) is not True:
        return default_legacy_record(uid)
    return parse_snapshot_strict(AccountCutoverRecord, snapshot)


def set_account_cutover_record(
    uid: str,
    record: AccountCutoverRecord,
    *,
    firestore_client: Any = None,
) -> None:
    if record.uid != uid:
        raise ValueError('cutover record uid mismatch')
    _write_document(_control_ref(uid, firestore_client=firestore_client), record.persisted_payload())


def get_account_cutover_record_optional(
    uid: str,
    *,
    firestore_client: Any = None,
) -> Optional[AccountCutoverRecord]:
    """Return None when no document exists (distinct from default legacy).

    Malformed existing documents fail closed rather than returning None.
    """

    snapshot = _control_ref(uid, firestore_client=firestore_client).get()
    if getattr(snapshot, 'exists', False) is not True:
        return None
    return parse_snapshot_strict(AccountCutoverRecord, snapshot)


def _write_document(doc_ref: Any, payload: dict[str, object]) -> None:
    setter = getattr(doc_ref, 'set', None)
    if callable(setter):
        setter(payload)
        return
    # Hermetic StrictFirestore documents expose rows via path/_database only.
    database = getattr(doc_ref, '_database', None)
    path = getattr(doc_ref, 'path', None)
    if database is not None and path is not None and hasattr(database, 'rows'):
        database.rows[path] = deepcopy(payload)
        return
    raise AccountCutoverConcurrencyError(
        'firestore document reference does not support cutover writes',
        code='cutover_cas_unsupported',
    )


def cas_set_account_cutover_record(
    uid: str,
    record: AccountCutoverRecord,
    *,
    expected_account_generation: int,
    expected_checkpoint_token: Optional[str] = None,
    require_existing: bool = False,
    firestore_client: Any = None,
) -> AccountCutoverRecord:
    """Persist ``record`` only when generation (and optional token) still match.

    Prefers a Firestore transaction when available. Clients that expose a process
    lock (hermetic StrictFirestore) serialize the read/CAS/write under that lock.
    Clients with neither primitive explicitly refuse concurrent mutation.
    """

    if record.uid != uid:
        raise ValueError('cutover record uid mismatch')

    client = firestore_client if firestore_client is not None else get_firestore_client()
    doc_ref = _control_ref(uid, firestore_client=client)
    payload = record.persisted_payload()
    lock = getattr(client, 'lock', None)

    def _locked_cas() -> AccountCutoverRecord:
        snapshot = doc_ref.get()
        current_generation, current_token = _read_current_generation_and_token(
            snapshot,
            require_existing=require_existing,
        )
        _assert_cas_matches(
            current_generation=current_generation,
            current_token=current_token,
            expected_account_generation=expected_account_generation,
            expected_checkpoint_token=expected_checkpoint_token,
        )
        _write_document(doc_ref, payload)
        return record

    if lock is not None:
        with lock:
            return _locked_cas()

    transaction_factory = getattr(client, 'transaction', None)
    if callable(transaction_factory):
        try:
            from google.cloud.firestore_v1 import transactional
        except ImportError as error:
            raise AccountCutoverConcurrencyError(
                'google.cloud.firestore transactional CAS unavailable',
                code='cutover_cas_unsupported',
            ) from error

        @transactional
        def _txn(transaction: Any) -> AccountCutoverRecord:
            snapshot = doc_ref.get(transaction=transaction)
            current_generation, current_token = _read_current_generation_and_token(
                snapshot,
                require_existing=require_existing,
            )
            _assert_cas_matches(
                current_generation=current_generation,
                current_token=current_token,
                expected_account_generation=expected_account_generation,
                expected_checkpoint_token=expected_checkpoint_token,
            )
            transaction.set(doc_ref, payload)
            return record

        return cast(Any, _txn)(transaction_factory())

    raise AccountCutoverConcurrencyError(
        'firestore client does not support transactional/locked cutover CAS',
        code='cutover_cas_unsupported',
    )


__all__ = [
    'CONTROL_COLLECTION',
    'CONTROL_DOCUMENT',
    'AccountCutoverConcurrencyError',
    'cas_set_account_cutover_record',
    'default_legacy_record',
    'get_account_cutover_record',
    'get_account_cutover_record_optional',
    'set_account_cutover_record',
]
