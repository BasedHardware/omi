"""Shadow capture may lose facts, never serving commits or conversation privacy."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from pathlib import Path
import json

import pytest
from google.cloud import firestore
from config import episode_log as config
from database import episode_log as store, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.episodes.log import capture, reads, worker
from utils.episodes.log.codec import loads
from utils.episodes.log.policy import home_policy_write
from utils.encryption import decrypt

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
UID = 'round2-synthetic'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('EPISODES_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '0')
    return StrictFirestore()


@pytest.mark.parametrize('failure', ['append', 'oversize', 'encryption', 'telemetry'])
def test_committed_composer_response_unchanged_when_capture_fails(client, monkeypatch, failure):
    from utils.metrics import OMI_FALLBACK_TOTAL

    path = ('users', UID, 'episodes', 'e')
    client.rows[path] = episodes.seal(
        UID,
        {
            'id': 'e',
            'status': 'closed',
            'close_reason': 'user',
            'state_version': 1,
            'started_at': NOW,
            'last_activity_at': NOW,
            'conversation_ids': [],
            'title': 'before',
        },
    )
    counter = OMI_FALLBACK_TOTAL.labels(
        component='sync_dispatch', from_mode='episode_capture', to_mode='legacy', reason='other', outcome='degraded'
    )
    before = counter._value.get()
    if failure in {'append', 'telemetry'}:
        monkeypatch.setattr(store, 'append', Mock(side_effect=RuntimeError('private contents')))
    if failure == 'encryption':
        monkeypatch.setattr(store, 'encrypt', Mock(side_effect=RuntimeError('private contents')))
    updates = {'title': 'after', 'composed_fingerprint': 'paid-once'}
    if failure == 'oversize':
        updates['parallel_content_spans'] = {f'c{i}': {'start': NOW, 'end': NOW} for i in range(1000)}
    if failure == 'telemetry':
        monkeypatch.setattr('utils.observability.fallback.record_fallback', Mock(side_effect=RuntimeError('metrics')))
    result = episodes.update_episode(UID, 'e', expected_version=1, updates=updates, firestore_client=client)
    committed = episodes.unseal(UID, client.rows[path])
    assert result['title'] == committed['title'] == 'after'
    assert result['state_version'] == committed['state_version'] == 2
    assert committed['composed_fingerprint'] == 'paid-once'
    # First transaction is always serving. All capture writes belong elsewhere.
    assert all(path[2] != 'episode_facts' for path, _ in client.transactions[0].creates)
    assert not any(k[2] == 'episode_facts' for k in client.rows)
    if failure != 'telemetry':
        assert counter._value.get() == before + 1


@pytest.mark.parametrize('entry', ['factory', 'state', 'barrier'])
@pytest.mark.parametrize('writer_fails', [False, True])
def test_policy_entry_failures_do_not_replace_or_repeat_original_writer(client, monkeypatch, entry, writer_fails):
    factory = Mock(return_value=client)
    monkeypatch.setattr(store, 'state', Mock(return_value={'cursor': 1}))
    broken = Mock(side_effect=RuntimeError('capture unavailable'))
    if entry == 'factory':
        factory = broken
    elif entry == 'state':
        monkeypatch.setattr(store, 'state', broken)
    else:
        monkeypatch.setattr(store, 'policy_barrier', broken)
    writer = (
        Mock(side_effect=ValueError('original failure')) if writer_fails else Mock(return_value='original response')
    )

    @home_policy_write(firestore_client=factory)
    def edit(uid, conversation_id):
        return writer()

    if writer_fails:
        with pytest.raises(ValueError, match='original failure'):
            edit(UID, 'c')
    else:
        assert edit(UID, 'c') == 'original response'
    writer.assert_called_once()


def test_absent_owner_failed_writer_is_called_once(client, monkeypatch):
    monkeypatch.setattr(store, 'state', lambda *a, **kw: {})
    writer = Mock(side_effect=ValueError('original failure'))

    @home_policy_write(firestore_client=lambda: client)
    def edit(uid, conversation_id):
        return writer()

    with pytest.raises(ValueError, match='original failure'):
        edit(UID, 'c')
    writer.assert_called_once()


@pytest.mark.parametrize('tombstone', [False, True])
def test_conversation_erasure_leaves_no_content_in_any_fact(client, tombstone):
    root = store.root(client, UID)
    conversation = root.collection('conversations').document('c')
    client.rows[conversation.path] = {'transcript': 'private conversation speech'}
    secret = 'private conversation speech'
    row = {
        'id': 'e',
        'status': 'closed',
        'started_at': NOW,
        'last_activity_at': NOW,
        'conversation_ids': ['c'],
        'title': secret,
        'bullets': [secret],
        'content': secret,
        'composed_notes': secret,
        'future_speech_field': secret,
    }
    store.append(UID, 'baseline', [{'kind': 'baseline', 'payload': {'row': row}}], firestore_client=client, now=NOW)
    store.append(
        UID,
        'member',
        [{'kind': 'member', 'cid': 'c', 'payload': {'structured': {'title': secret}}}],
        firestore_client=client,
        now=NOW,
    )

    @firestore.transactional
    def erase(transaction):
        intent = store.prepare_member_change(transaction, root)
        if tombstone:
            transaction.update(conversation, {'deleted': True, 'transcript': None})
        else:
            transaction.delete(conversation)
        store.member_changed(intent, ['c'])

    erase(client.transaction())
    facts = [value for path, value in client.rows.items() if path[2] == 'episode_facts']
    assert len(facts) == 3
    for fact in facts:
        decoded = decrypt(fact['payload'], UID)
        assert secret not in decoded
        assert 'future_speech_field' not in decoded and 'structured' not in decoded
        assert fact['expires_at'] - fact['recorded_at'] == timedelta(days=1)
        assert len(fact['payload'].encode()) <= store.MAX_FACT_BYTES
    policy = json.loads((Path(__file__).parents[2] / 'deploy/episode-log/retention.json').read_text())
    assert policy['field'] == 'expires_at' and policy['collection_groups'] == ['episode_facts']
    assert policy['retention_seconds'] == 86400


def test_idle_owner_clears_due_scan_and_legacy_idle_debt_is_not_woken(client, monkeypatch):
    store.append(UID, 'k', [], firestore_client=client, now=NOW)
    claimed = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=3))
    result = store.publish(UID, claimed, 1, {}, {}, {}, firestore_client=client, now=NOW + timedelta(minutes=4))
    assert 'scan_at' not in result and 'drain_at' not in result
    # Repair an owner written before this fix instead of rotating it forever.
    result.update(scan_at=NOW, drain_at=NOW)
    client.rows[('users', UID, 'episode_log_state', 'owner')] = result
    monkeypatch.setattr(store, 'due_owners', lambda *a, **kw: [(UID, result.copy())])
    wake = Mock()
    monkeypatch.setattr(worker, 'wake', wake)
    assert worker.sweep(firestore_client=client, now=NOW)['redriven'] == 0
    wake.assert_not_called()
    assert 'scan_at' not in store.state(UID, firestore_client=client)


def test_zero_percent_home_never_reads_appends_or_wakes_even_with_expired_clock(client, monkeypatch):
    monkeypatch.setattr(worker.random, 'random', lambda: 0)
    forbidden = Mock(side_effect=AssertionError('zero-percent Home touched log'))
    monkeypatch.setattr(store, 'state', forbidden)
    monkeypatch.setattr(store, 'append', forbidden)
    monkeypatch.setattr(worker, 'wake', forbidden)
    assert reads.ready(UID, firestore_client=client) is None
    worker.sample_read(UID, [{'id': 'e'}], firestore_client=client)
    worker.note_home_clock(UID, {'home_refresh_cid': 'c', 'home_valid_until': NOW}, firestore_client=client)
    worker.note_home_refresh(UID, 'e', 'key', firestore_client=client)
    forbidden.assert_not_called()


def test_remote_capture_kill_overrides_env_and_rechecks_after_serving_commit(client, monkeypatch):
    from utils import omi_flags
    from types import SimpleNamespace

    key = 'EPISODES_LOG_ENABLED'
    rules = {}
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: SimpleNamespace(rules=rules))
    assert config.enabled(UID)
    rules[key] = omi_flags.FlagRule.from_doc(key, {'active': False, 'rollout_percentage': 100})
    assert not config.enabled(UID)
    ref = store.root(client, UID).collection('conversations').document('c')

    @firestore.transactional
    def edit(transaction):
        intent = store.prepare(transaction, client, UID)
        transaction.set(ref, {'deleted': True})
        intent.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}])

    edit(client.transaction())
    assert client.rows[ref.path] == {'deleted': True}
    assert not any(k[2] == 'episode_facts' for k in client.rows)
    monkeypatch.setenv(key, 'off')
    rules[key] = omi_flags.FlagRule.from_doc(key, {'active': True, 'rollout_percentage': 100})
    assert config.enabled(UID)  # env is the absent-rule fallback


def test_content_only_composer_refreshes_reference_without_logging_lease_churn(client, monkeypatch):
    from utils.episodes.log.fold import Fold
    from utils.episodes.log.codec import dumps
    from utils.episodes import home_read

    monkeypatch.setenv('EPISODES_HOME_ROWS_ENABLED', 'off')
    row = {
        'id': 'e',
        'status': 'closed',
        'close_reason': 'user',
        'state_version': 1,
        'started_at': NOW,
        'last_activity_at': NOW,
        'conversation_ids': [],
        'title': 'old',
    }
    root = store.root(client, UID)
    client.rows[('users', UID, 'episodes', 'e')] = episodes.seal(UID, row)
    # Seed and publish the geometry, as a prior caught-up drain would.
    store.append(UID, 'seed', [{'kind': 'baseline', 'payload': {'row': row}}], firestore_client=client, now=NOW)
    monkeypatch.setattr(
        store,
        'fact_page',
        lambda uid, after, through, **kw: sorted(
            [v for k, v in client.rows.items() if k[2] == 'episode_facts' and after < v['seq'] <= through],
            key=lambda v: v['seq'],
        ),
    )
    monkeypatch.setattr(worker, 'wake', lambda *a: None)
    assert worker.drain(UID, firestore_client=client, now=NOW + timedelta(minutes=3)) == 'drained'
    before = store.state(UID, firestore_client=client)['next_seq']
    episodes.update_episode(
        UID, 'e', expected_version=1, updates={'compose_lease': {'token': 'lease'}}, firestore_client=client
    )
    assert store.state(UID, firestore_client=client)['next_seq'] == before
    episodes.update_episode(UID, 'e', expected_version=2, updates={'title': 'new'}, firestore_client=client)
    assert store.state(UID, firestore_client=client)['next_seq'] == before + 1
    at = store.state(UID, firestore_client=client)['drain_at']
    assert worker.drain(UID, firestore_client=client, now=at) == 'drained'
    view = episodes.unseal(UID, client.rows[('users', UID, 'episode_views', 'e')])
    assert view['title'] == 'new'
    assert 'new' not in dumps(store.checkpoint(UID, firestore_client=client))
