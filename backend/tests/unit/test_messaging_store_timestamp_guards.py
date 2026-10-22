"""Unit tests for UTC timestamp coercion and null field guards in database.messaging and database.messaging_albums."""

from datetime import datetime, timedelta, timezone
import json
import sys
from types import ModuleType
from unittest.mock import MagicMock

if 'stripe' not in sys.modules:
    sys.modules['stripe'] = ModuleType('stripe')

from database import messaging, messaging_albums
from utils import encryption


def test_age_coerces_naive_and_iso_timestamps_and_guards_missing_created_at():
    """messaging._age() should normalize naive datetimes and ISO-8601 strings to UTC without raising TypeError."""
    now = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)
    naive_created = datetime(2026, 4, 21, 11, 59, 0)
    assert messaging._age({'created_at': naive_created}, now) == 60.0
    assert messaging._age({'started_at': '2026-04-21T11:58:30Z'}, now, 'started_at') == 90.0
    assert messaging._age({}, now) == float(messaging.STALE_SECONDS)


def test_claim_handles_explicit_null_album_ready_at_and_naive_timestamps(monkeypatch):
    """MessagingStore._claim() should not raise TypeError when album_ready_at is explicitly None or created_at is naive."""
    monkeypatch.setattr(messaging.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(messaging, 'run_with_transaction_contention_retry', lambda tx_fn, apply, **kw: apply(MagicMock()))

    now = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)
    raw_payload = {'text': 'hello', 'media_group_id': None}
    encrypted = encryption.encrypt(json.dumps(raw_payload), 'ident-1')

    candidate = MagicMock()
    candidate.reference.path = 'channel_identities/ident-1/inbox/msg-1'
    candidate.to_dict.return_value = {
        'status': 'pending',
        'created_at': datetime(2026, 4, 21, 11, 59, 50),  # naive datetime
        'album_ready_at': None,  # explicit None previously raised TypeError on None > now
        'payload': encrypted,
    }

    client = MagicMock()
    ref = client.document.return_value
    ref.parent.parent.id = 'ident-1'
    ref.parent.where.return_value.order_by.return_value.stream.return_value = [candidate]

    store = messaging.MessagingStore(firestore_client=client)
    claimed = store.claim_next('channel_identities/ident-1/inbox/msg-1', now=now)
    assert claimed == ('channel_identities/ident-1/inbox/msg-1', raw_payload)


def test_notice_allowed_and_seal_album_handle_naive_and_iso_timestamps(monkeypatch):
    """notice_allowed() and seal_album() should coerce naive/ISO timestamps and guard null attachments."""
    monkeypatch.setattr(messaging.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(messaging, 'run_with_transaction_contention_retry', lambda tx_fn, apply, **kw: apply(MagicMock()))
    monkeypatch.setattr(messaging_albums.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(
        messaging_albums, 'run_with_transaction_contention_retry', lambda tx_fn, apply, **kw: apply(MagicMock())
    )

    client = MagicMock()
    ident_doc = client.collection.return_value.document.return_value
    ident_snap = MagicMock()
    # Recent naive datetime within the 3600s window
    ident_snap.to_dict.return_value = {
        'notice_unlinked': (datetime.now(timezone.utc) - timedelta(seconds=30)).replace(tzinfo=None)
    }
    ident_doc.get.return_value = ident_snap

    store = messaging.MessagingStore(firestore_client=client)
    msg = MagicMock(channel='telegram', provider='telegram', external_user_id='u-1')
    assert store.notice_allowed(msg, 'unlinked', window=3600) is False

    # Test seal_album with naive started_at and explicit None attachments
    raw_album_payload = {'text': 'album', 'attachments': None}
    encrypted_album = encryption.encrypt(json.dumps(raw_album_payload), 'ident-1')
    album_ref = client.document.return_value
    album_ref.parent.parent.id = 'ident-1'
    album_snap = MagicMock()
    album_snap.to_dict.return_value = {
        'status': 'running',
        'started_at': (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None),
        'payload': encrypted_album,
    }
    album_ref.get.return_value = album_snap

    sealed = messaging_albums.seal_album(client, 'channel_identities/ident-1/inbox/album-1', 0, stale_seconds=300)
    assert sealed is None
