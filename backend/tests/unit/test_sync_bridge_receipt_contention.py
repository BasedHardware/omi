"""Bridge receipt commits survive Firestore commit-contention exhaustion.

``@firestore.transactional`` replays a contended commit with the same
transaction id, without backoff, up to five times, then raises a bare
``ValueError``. The receipt boundary used the default ``run_transactional``
path, which restarts only an expired transaction id, so sustained contention
on a bridge tombstone failed finalize after intake already persisted
(``sync_finalize_exception exception_type=ValueError site=bridge_receipt``).
These tests drive the real SDK transaction loop against a scripted fake
client: the receipt must restart on a fresh transaction with bounded backoff,
must never stamp a receipt that did not commit, and must stay retryable when
the whole budget is spent.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import Aborted

from database import _client as client_module
from database.sync_bridges import mark_sync_bridge_cleaned
from utils.sync.telemetry import value_error_reason

DONOR = ('users', 'u', 'conversations', 'donor')


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return copy.deepcopy(self._data)


class _Doc:
    def __init__(self, client, path):
        self._client = client
        self.path = path

    def collection(self, name):
        return _Collection(self._client, (*self.path, name))

    def get(self, transaction=None, **kwargs):
        assert transaction is not None, 'the receipt body must read transactionally'
        return _Snapshot(self._client.rows.get(self.path))


class _Collection:
    def __init__(self, client, path):
        self._client = client
        self._path = path

    def document(self, name):
        return _Doc(self._client, (*self._path, name))


class _Transaction:
    """The lifecycle hooks the real ``_Transactional`` drives, plus scripted commits."""

    _read_only = False
    _max_attempts = 5

    def __init__(self, client):
        self._client = client
        self._id = None
        self.ops = []
        self.commit_ids = []

    def _clean_up(self):
        self._id = None
        self.ops = []

    def _begin(self, retry_id=None):
        if retry_id is None:
            self._client.transaction_ids += 1
            retry_id = f'txn-{self._client.transaction_ids}'.encode()
        self._id = retry_id

    def _rollback(self):
        return None

    def update(self, ref, patch):
        self.ops.append((ref.path, copy.deepcopy(patch)))

    def _commit(self):
        self.commit_ids.append(self._id)
        action = self._client.actions.pop(0) if self._client.actions else 'ok'
        if action == 'aborted':
            raise Aborted('Too much contention on these documents.')
        if self.ops:
            for path, patch in self.ops:
                self._client.rows[path].update(patch)
            self._client.commits_applied += 1


class _Client:
    def __init__(self, actions):
        self.actions = list(actions)
        self.rows = {
            DONOR: {'deleted': True, 'sync_merged_into': 'survivor', 'sync_content_revision': 3},
        }
        self.transactions = []
        self.transaction_ids = 0
        self.commits_applied = 0

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


@pytest.fixture
def sleeps(monkeypatch):
    delays = []
    monkeypatch.setattr(client_module, 'time', SimpleNamespace(sleep=delays.append))
    return delays


def test_contended_receipt_exhausts_sdk_replay_then_commits_on_a_fresh_transaction(sleeps):
    client = _Client(['aborted'] * 5 + ['ok'])

    assert mark_sync_bridge_cleaned('u', 'donor', 3, 'survivor', firestore_client=client) is True

    # One outer restart: the SDK spent its five same-id replays on the first
    # transaction (the production failure), then a fresh transaction committed.
    assert len(client.transactions) == 2
    first, second = client.transactions
    assert first.commit_ids == [b'txn-1'] * 5
    assert second.commit_ids == [b'txn-2']
    assert client.commits_applied == 1
    assert client.rows[DONOR]['sync_bridge_cleaned_revision'] == 3
    assert client.rows[DONOR]['sync_bridge_audio_target'] == 'survivor'
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0


def test_exhausted_contention_never_marks_cleaned_and_stays_retryable(sleeps):
    client = _Client(['aborted'] * 15)

    with pytest.raises(ValueError, match='Failed to commit transaction') as caught:
        mark_sync_bridge_cleaned('u', 'donor', 3, 'survivor', firestore_client=client)

    assert isinstance(caught.value.__cause__, Aborted)
    assert value_error_reason(caught.value) == 'sdk_commit_attempts_exhausted'
    assert len(client.transactions) == 3  # the full bounded budget, then raise
    assert client.commits_applied == 0
    assert 'sync_bridge_cleaned_revision' not in client.rows[DONOR]
    assert 'sync_bridge_audio_target' not in client.rows[DONOR]
    assert len(sleeps) == 2 and all(0 < delay <= 1.0 for delay in sleeps)

    # Nothing was swallowed: the identical call converges once contention drains,
    # so a retried sync job finishes the receipt it still owes.
    assert mark_sync_bridge_cleaned('u', 'donor', 3, 'survivor', firestore_client=client) is True
    assert client.rows[DONOR]['sync_bridge_cleaned_revision'] == 3


def test_restarted_receipt_refuses_a_revision_that_moved_during_backoff(monkeypatch):
    client = _Client(['aborted'] * 5)

    def advance_revision(_delay):
        client.rows[DONOR]['sync_content_revision'] += 1

    monkeypatch.setattr(client_module, 'time', SimpleNamespace(sleep=advance_revision))

    assert mark_sync_bridge_cleaned('u', 'donor', 3, 'survivor', firestore_client=client) is False

    assert len(client.transactions) == 2  # the restart ran and re-read
    assert client.commits_applied == 0
    assert 'sync_bridge_cleaned_revision' not in client.rows[DONOR]
    assert 'sync_bridge_audio_target' not in client.rows[DONOR]
