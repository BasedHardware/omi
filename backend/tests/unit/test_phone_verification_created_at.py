"""get_pending_verification_uid must not 500 on a malformed pending_verifications record.

It read datetime.fromisoformat(data['created_at']) directly, so a record missing created_at (KeyError) or
storing it as a non-string (TypeError) crashed POST /v1/phone/numbers/verify/check with a 500. It now
treats a malformed record as expired. Migrated to the WP2 storage port (ADR-0002): the getter reads
through the injected `_store` seam, so the tests seed a FakeDocumentStore at the pending_verifications
path and patch `_store`.
"""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database.phone_calls as phone_db
from tests.store_fakes import FakeDocumentStore

PHONE = '+15551234567'


def _bind(monkeypatch, data):
    """Seed a FakeDocumentStore at the pending_verifications doc for PHONE and patch the seam."""
    store = FakeDocumentStore()
    if data is not None:
        doc_id = phone_db._hash_phone_number(PHONE)
        store.set(f'{phone_db.pending_verifications_collection}/{doc_id}', data)
    monkeypatch.setattr(phone_db, '_store', lambda: store)
    return store


def test_missing_created_at_returns_none_not_500(monkeypatch):
    _bind(monkeypatch, {'uid': 'u1'})  # no created_at
    assert phone_db.get_pending_verification_uid(PHONE) is None


def test_non_string_created_at_returns_none_not_500(monkeypatch):
    _bind(monkeypatch, {'created_at': 12345, 'uid': 'u1'})
    assert phone_db.get_pending_verification_uid(PHONE) is None


def test_valid_recent_created_at_returns_uid(monkeypatch):
    now_iso = datetime.now(timezone.utc).isoformat()
    _bind(monkeypatch, {'created_at': now_iso, 'uid': 'u1'})
    assert phone_db.get_pending_verification_uid(PHONE) == 'u1'


def test_naive_recent_created_at_returns_uid_not_500(monkeypatch):
    # A parseable but timezone-naive recent created_at must not crash the aware-minus-naive subtraction.
    naive_recent = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    _bind(monkeypatch, {'created_at': naive_recent, 'uid': 'u1'})
    assert phone_db.get_pending_verification_uid(PHONE) == 'u1'


def test_naive_old_created_at_treated_expired_not_500(monkeypatch):
    naive_old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)).isoformat()
    _bind(monkeypatch, {'created_at': naive_old, 'uid': 'u1'})
    assert phone_db.get_pending_verification_uid(PHONE) is None


def test_expired_record_is_deleted(monkeypatch):
    # An expired (aware) record is treated as absent AND purged from the store.
    old_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    store = _bind(monkeypatch, {'created_at': old_iso, 'uid': 'u1'})
    doc_id = phone_db._hash_phone_number(PHONE)
    path = f'{phone_db.pending_verifications_collection}/{doc_id}'
    assert store.exists(path)
    assert phone_db.get_pending_verification_uid(PHONE) is None
    assert not store.exists(path)
