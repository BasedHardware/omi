"""Queued-writer publication proofs and capture-off TTL data-query isolation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import episode_log as config
from database import episode_log as store
from utils import omi_flags
from utils.episodes.log import reconcile, retention, worker


@pytest.mark.parametrize('remote', [None, False])
def test_capture_off_inactive_ttl_never_queries_facts(monkeypatch, remote):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on' if remote is False else 'off')
    rules = {} if remote is None else {'EPISODES_LOG_ENABLED': SimpleNamespace(active=False)}
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: SimpleNamespace(rules=rules))
    monkeypatch.setattr(retention, '_guard_until', {})
    active = Mock(return_value=False)
    monkeypatch.setattr(retention, 'active', active)
    client = Mock(project='demo-round4', _database='(default)')
    retention.guard(client)
    assert worker.sweep(firestore_client=client) == {'disabled': 1}
    client.collection_group.assert_not_called()
    active.assert_not_called()
    assert not client.mock_calls
    assert not retention._guard_until  # A subsequent flag-on probe is not suppressed.


def test_remote_capture_on_admits_ttl_probe_even_with_env_off(monkeypatch):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'off')
    monkeypatch.setattr(
        omi_flags, 'snapshot', lambda: SimpleNamespace(rules={'EPISODES_LOG_ENABLED': SimpleNamespace(active=True)})
    )
    monkeypatch.setattr(retention, '_guard_until', {})
    monkeypatch.setattr(retention, 'active', lambda client: False)
    client = Mock(project='demo-round4', _database='(default)')
    client.collection_group.return_value.select.return_value.limit.return_value.stream.return_value = iter([])
    assert config.capture_possible()
    retention.guard(client)
    client.collection_group.assert_called_once_with('episode_facts')


@pytest.mark.parametrize('current', [{}, {'row': 2}, {'row': 1, 'inserted': 1}])
def test_reconcile_proof_rechecks_versions_in_publishing_transaction(monkeypatch, current):
    client, transaction = object(), object()
    docs = [
        SimpleNamespace(reference=SimpleNamespace(path=path), update_time=version) for path, version in current.items()
    ]
    read = Mock(return_value=docs)
    monkeypatch.setattr(reconcile, 'source_documents', read)
    with pytest.raises(store.LostLease, match='source_changed'):
        reconcile.verify('synthetic', client, {'row': 1}, transaction)
    read.assert_called_once_with('synthetic', client, transaction=transaction)
