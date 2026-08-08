"""Firestore persistence for whole-account cutover control documents."""

from __future__ import annotations

from typing import Any, Optional

from database._client import get_firestore_client
from database.read_boundary import parse_snapshot_or_none
from models.account_cutover import AccountCutoverRecord, AccountCutoverState

CONTROL_COLLECTION = 'account_cutover'
CONTROL_DOCUMENT = 'state'


def _control_ref(uid: str, *, firestore_client: Any = None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid).collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)


def default_legacy_record(uid: str) -> AccountCutoverRecord:
    return AccountCutoverRecord(uid=uid, state=AccountCutoverState.legacy)


def get_account_cutover_record(uid: str, *, firestore_client: Any = None) -> AccountCutoverRecord:
    """Return the persisted cutover record, or an implicit legacy default."""

    snapshot = _control_ref(uid, firestore_client=firestore_client).get()
    if getattr(snapshot, 'exists', False) is not True:
        return default_legacy_record(uid)
    parsed = parse_snapshot_or_none(AccountCutoverRecord, snapshot)
    if parsed is None:
        return default_legacy_record(uid)
    return parsed


def set_account_cutover_record(
    uid: str,
    record: AccountCutoverRecord,
    *,
    firestore_client: Any = None,
) -> None:
    if record.uid != uid:
        raise ValueError('cutover record uid mismatch')
    _control_ref(uid, firestore_client=firestore_client).set(record.persisted_payload())


def get_account_cutover_record_optional(
    uid: str,
    *,
    firestore_client: Any = None,
) -> Optional[AccountCutoverRecord]:
    """Return None when no document exists (distinct from default legacy)."""

    snapshot = _control_ref(uid, firestore_client=firestore_client).get()
    if getattr(snapshot, 'exists', False) is not True:
        return None
    return parse_snapshot_or_none(AccountCutoverRecord, snapshot)


__all__ = [
    'CONTROL_COLLECTION',
    'CONTROL_DOCUMENT',
    'default_legacy_record',
    'get_account_cutover_record',
    'get_account_cutover_record_optional',
    'set_account_cutover_record',
]
