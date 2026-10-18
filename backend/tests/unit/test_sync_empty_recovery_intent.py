"""The atomic create/versioned-settle seam forbids duplicate paid dispatch."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import AlreadyExists
import pytest

from database import sync_empty_recovery as store
from utils.sync import empty_recovery_intent as intent


class AtomicDocument:
    def __init__(self):
        self.row = None
        self.version = 0

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def create(self, row):
        if self.row is not None:
            raise AlreadyExists('exists')
        self.row = dict(row)
        self.version += 1
        return SimpleNamespace(update_time=self.version)

    def get(self):
        return SimpleNamespace(to_dict=lambda: dict(self.row or {}))

    def update(self, row, *, option):
        assert option._last_update_time == self.version, 'stale write rejected'
        self.row.update(row)
        self.version += 1


@pytest.fixture
def document(monkeypatch):
    doc = AtomicDocument()
    monkeypatch.setattr(store, 'get_firestore_client', lambda: doc)
    monkeypatch.setattr(store, 'external_write_fence', lambda uid: nullcontext())
    return doc


@pytest.mark.parametrize('words', [[], [{'text': 'Synthetic recovery', 'timestamp': [0, 1]}]])
def test_replay_reads_encrypted_response_without_another_paid_call(document, words):
    dispatch = Mock(return_value=(words, 'vi'))
    assert intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch) == (words, 'vi')
    assert 'Synthetic recovery' not in document.row['response']
    assert intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch) == (words, 'vi')
    dispatch.assert_called_once()
    assert document.row['state'] == 'completed'


def test_provider_uncertainty_spends_intent_without_automatic_retry(document):
    dispatch = Mock(side_effect=TimeoutError('synthetic timeout'))
    with pytest.raises(TimeoutError):
        intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch)
    with pytest.raises(RuntimeError, match='unresolved'):
        intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch)
    dispatch.assert_called_once()
    assert document.row['state'] == 'running'


def test_lost_settle_reply_reuses_winner_result(document, monkeypatch):
    settle = intent.settle

    def lose_reply(*args):
        settle(*args)
        raise TimeoutError('lost reply')

    monkeypatch.setattr(intent, 'settle', lose_reply)
    dispatch = Mock(return_value=([], 'multi'))
    with pytest.raises(TimeoutError):
        intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch)
    assert intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch) == ([], 'multi')
    dispatch.assert_called_once()


def test_settle_cannot_overwrite_a_changed_intent(document):
    ref, version, cached = store.claim('synthetic-owner', 'stable-segment')
    document.version += 1
    with pytest.raises(AssertionError, match='stale'):
        store.settle('synthetic-owner', ref, version, 'encrypted')
    assert document.row['state'] == 'running'


def test_owner_deletion_fence_refuses_claim_before_dispatch(document, monkeypatch):
    monkeypatch.setattr(store, 'external_write_fence', Mock(side_effect=RuntimeError('fenced')))
    dispatch = Mock()
    with pytest.raises(RuntimeError, match='fenced'):
        intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch)
    dispatch.assert_not_called()
    assert document.row is None


@pytest.mark.parametrize('response', [None, {'invalid': True}, [[], 'multi']])
def test_cached_malformed_response_keeps_its_shape_without_redispatch(document, response):
    dispatch = Mock(return_value=response)
    assert intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch) == response
    assert intent.dispatch_once('synthetic-owner', 'stable-segment', dispatch) == response
    dispatch.assert_called_once()
