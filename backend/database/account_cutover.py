"""Neutral-store persistence for whole-account cutover control documents."""

from __future__ import annotations

from typing import Any, Optional

from database import document_store
from database.read_boundary import MalformedDocError, parse_snapshot_strict
from models.account_cutover import AccountCutoverRecord, AccountCutoverState

CONTROL_COLLECTION = 'account_cutover'
CONTROL_DOCUMENT = 'state'


class AccountCutoverConcurrencyError(RuntimeError):
    """Raised when a CAS write loses a generation/token race, or CAS is unsupported."""

    def __init__(self, message: str = 'cutover concurrency conflict', *, code: str = 'cutover_concurrency_conflict'):
        super().__init__(message)
        self.code = code


def _control_path(uid: str) -> str:
    return f'users/{uid}/{CONTROL_COLLECTION}/{CONTROL_DOCUMENT}'


def default_legacy_record(uid: str) -> AccountCutoverRecord:
    return AccountCutoverRecord(uid=uid, state=AccountCutoverState.legacy)


def _snapshot_document_path(snapshot: Any, *, uid: str) -> str:
    path = getattr(snapshot, 'path', None)
    if isinstance(path, str) and path:
        return path
    return _control_path(uid)


def _parse_bound_record(uid: str, snapshot: Any) -> AccountCutoverRecord:
    """Parse an authoritative cutover doc and bind embedded uid to the path uid."""

    record = parse_snapshot_strict(AccountCutoverRecord, snapshot)
    if record.uid != uid:
        raise MalformedDocError(
            document_path=_snapshot_document_path(snapshot, uid=uid),
            error_types=('uid_binding_mismatch',),
            error_fields=('uid',),
        )
    return record


def _read_current_generation_and_token(
    uid: str,
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
    current = _parse_bound_record(uid, snapshot)
    return current.account_generation, current.checkpoint_token


def _assert_cas_matches(
    *,
    current_generation: int,
    current_token: Optional[str],
    expected_account_generation: int,
    expected_checkpoint_token: Optional[str],
    document_exists: bool,
) -> None:
    if current_generation != expected_account_generation:
        raise AccountCutoverConcurrencyError(
            f'account generation CAS mismatch expected={expected_account_generation} actual={current_generation}',
            code='cutover_generation_cas_mismatch',
        )
    # Existing documents with a checkpoint token require an exact token match so
    # same-generation concurrent writers cannot overwrite each other. Missing
    # documents (implicit legacy) and token-less first writes still allow None.
    if document_exists and current_token is not None:
        if expected_checkpoint_token is None or current_token != expected_checkpoint_token:
            raise AccountCutoverConcurrencyError(
                'checkpoint token CAS mismatch',
                code='cutover_checkpoint_cas_mismatch',
            )
    elif expected_checkpoint_token is not None and current_token != expected_checkpoint_token:
        raise AccountCutoverConcurrencyError(
            'checkpoint token CAS mismatch',
            code='cutover_checkpoint_cas_mismatch',
        )


def get_account_cutover_record(uid: str) -> AccountCutoverRecord:
    """Return the persisted cutover record, or an implicit legacy default.

    Missing documents remain legacy-compatible. Existing but malformed documents
    fail closed via ``MalformedDocError`` — they must not silently project as
    legacy and reopen product traffic. Embedded ``uid`` must match the path uid.
    """

    snapshot = document_store.get_document(_control_path(uid))
    if getattr(snapshot, 'exists', False) is not True:
        return default_legacy_record(uid)
    return _parse_bound_record(uid, snapshot)


def set_account_cutover_record(uid: str, record: AccountCutoverRecord) -> None:
    if record.uid != uid:
        raise ValueError('cutover record uid mismatch')
    document_store.set_document(_control_path(uid), record.persisted_payload())


def get_account_cutover_record_optional(uid: str) -> Optional[AccountCutoverRecord]:
    """Return None when no document exists (distinct from default legacy).

    Malformed existing documents fail closed rather than returning None.
    """

    snapshot = document_store.get_document(_control_path(uid))
    if getattr(snapshot, 'exists', False) is not True:
        return None
    return _parse_bound_record(uid, snapshot)


def cas_set_account_cutover_record(
    uid: str,
    record: AccountCutoverRecord,
    *,
    expected_account_generation: int,
    expected_checkpoint_token: Optional[str] = None,
    require_existing: bool = False,
) -> AccountCutoverRecord:
    """Persist ``record`` only when generation (and optional token) still match.

    The read/assert/write runs inside one neutral store transaction, so a same-
    generation concurrent writer cannot overwrite this one on either backend.
    """

    if record.uid != uid:
        raise ValueError('cutover record uid mismatch')

    path = _control_path(uid)
    payload = record.persisted_payload()

    def _txn(tx: Any) -> AccountCutoverRecord:
        snapshot = tx.get(path)
        document_exists = getattr(snapshot, 'exists', False) is True
        current_generation, current_token = _read_current_generation_and_token(
            uid,
            snapshot,
            require_existing=require_existing,
        )
        _assert_cas_matches(
            current_generation=current_generation,
            current_token=current_token,
            expected_account_generation=expected_account_generation,
            expected_checkpoint_token=expected_checkpoint_token,
            document_exists=document_exists,
        )
        tx.set(path, payload)
        return record

    return document_store.run_transaction(_txn)


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
