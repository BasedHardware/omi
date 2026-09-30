"""Hermetic guards layered on capture_wedge_state claims."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import capture_wedge_state as wedge


class _Boom(RuntimeError):
    pass


class _Doc:
    def __init__(self, raise_on_get=False):
        self.raise_on_get = raise_on_get

    def get(self, transaction=None):
        if self.raise_on_get:
            raise _Boom('firestore down')
        return SimpleNamespace(exists=False, to_dict=lambda: {})


class _Client:
    def __init__(self, doc):
        self.doc = doc

    def collection(self, _name):
        return self

    def document(self, _uid):
        return self.doc

    def transaction(self):
        return object()


def test_clean_day_rejects_non_calendar_values():
    with pytest.raises(ValueError):
        wedge.claim_wedge_first_seen('uid1', '2026-13-45')


def test_clean_id_rejects_path_tokens():
    with pytest.raises(ValueError):
        wedge.claim_wedge_first_seen('../x', '2026-09-30')


def test_claim_first_seen_fails_closed_when_get_raises(monkeypatch):
    monkeypatch.setattr(wedge.firestore, 'transactional', lambda fn: fn)
    client = _Client(_Doc(raise_on_get=True))
    assert (
        wedge.claim_wedge_first_seen('uid1', '2026-09-30', firestore_client=client, now=datetime.now(timezone.utc))
        is False
    )


def test_claim_nudge_fails_closed_when_transaction_raises(monkeypatch):
    def boom(_fn):
        def runner(_txn):
            raise _Boom('txn')

        return runner

    monkeypatch.setattr(wedge.firestore, 'transactional', boom)
    client = _Client(_Doc())
    assert wedge.claim_wedge_nudge_cooldown('uid1', firestore_client=client, now=datetime.now(timezone.utc)) is False
