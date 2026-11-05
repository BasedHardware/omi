"""Recovery and observation contracts found during batch-2 review."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
from config import episode_log as config
from database import episode_log as store, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.episodes import home_read
from utils.episodes.log import metrics, reads, worker
from utils.episodes.log.worker import wake as real_wake
from utils.episodes.log.codec import loads
from utils.episodes.log.fold import Fold
from utils.episodes.log.policy import home_policy_write
from utils.encryption import decrypt
from tests.unit.episode_log_support.oracle import Oracle

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
UID = 'review-user'


@pytest.mark.parametrize('strategy', ['canonical', 'fallback'])
def test_live_and_recorded_transactions_never_read_log_owner(client, monkeypatch, strategy):
    from database import episode_recorded_components

    reads = []
    original = StrictFirestoreDocument.get

    def observed(ref, *args, **kwargs):
        if kwargs.get('transaction') is not None:
            reads.append((id(kwargs['transaction']), ref.path))
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', observed)
    if strategy == 'fallback':
        monkeypatch.setattr(episode_recorded_components, 'attach', lambda *args, **kwargs: None)
    owner = ('users', UID, 'episode_log_state', 'owner')
    with Oracle(UID) as oracle:
        oracle.attach('recorded', NOW, NOW + timedelta(minutes=1))
        assert reads[0][1] != owner
        serving = reads[0][0]
        assert all(path != owner for tx, path in reads if tx == serving)
        reads.clear()
        episodes.commit_moment(
            UID,
            expected_episode_id=None,
            expected_version=None,
            new_episode={
                'id': 'live',
                'status': 'live',
                'started_at': NOW + timedelta(hours=10),
                'last_activity_at': NOW + timedelta(hours=10, minutes=1),
                'conversation_ids': [],
            },
            firestore_client=oracle.store,
        )
        assert reads[0][1] != owner
        serving = reads[0][0]
        assert all(path != owner for tx, path in reads if tx == serving)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('EPISODES_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '100')
    monkeypatch.setattr(worker, 'wake', lambda *args: None)
    return StrictFirestore()


def test_uncertain_member_returning_to_old_state_is_not_deduplicated(client):
    for title in ('first', 'second', 'first'):
        assert worker.mark_dirty(UID, 'c', {'structured': {'title': title}}, firestore_client=client)
    facts = sorted(
        [v for k, v in client.rows.items() if k[:3] == ('users', UID, 'episode_facts')], key=lambda f: f['seq']
    )
    assert len(facts) == 3
    fold = Fold(UID)
    for fact in facts:
        for event in loads(decrypt(fact['payload'], UID)):
            fold.apply(event)
    assert fold.members == {}
    assert all('structured' not in decrypt(fact['payload'], UID) for fact in facts)


def test_links_only_mutation_carries_null_tombstone_without_deletion():
    capture = Mock()
    store.mutation(capture, links={'current': {'episode_id': None}})
    fold = Fold(UID)
    fold.apply({'kind': 'baseline_link', 'cid': 'current', 'payload': {'episode_id': 'old'}})
    fold.apply(capture.stage.call_args.args[0][0])
    assert fold.links['current'] == {'episode_id': None}
    store.mutation(capture, span={'cid': 'c', 'start': NOW, 'end': NOW})
    assert capture.stage.call_count == 2


def test_policy_release_failure_preserves_success_and_failed_writer(client, monkeypatch):
    monkeypatch.setattr(store, 'state', lambda *args, **kwargs: {'cursor': 0})
    barrier = Mock(side_effect=[None, RuntimeError('release unavailable'), None, RuntimeError('release unavailable')])
    monkeypatch.setattr(store, 'policy_barrier', barrier)

    @home_policy_write(firestore_client=lambda: client)
    def edit(uid, conversation_id, fails=False):
        if fails:
            raise ValueError('original write error')
        return 'committed'

    assert edit(UID, 'c') == 'committed'
    with pytest.raises(ValueError, match='original write error'):
        edit(UID, 'c', True)


def test_unknown_kill_switch_word_keeps_capture_off(client, monkeypatch, caplog):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'typo')
    assert not config.enabled(UID)


def test_both_missing_rows_agree_and_alert_counters_are_primed():
    assert set(metrics.differences(None, None).values()) == {'match'}
    phases = {s.labels['phase'] for f in metrics.OVERDUE.collect() for s in f.samples}
    assert phases == {'queued', 'running', 'retrying'}
    drift = {(s.labels['field'], s.labels['outcome']) for f in metrics.DRIFT.collect() for s in f.samples}
    assert all((field, 'mismatch') in drift for field in metrics.FIELDS)


def test_legacy_row_identity_and_drift_member_reads_are_batched(client, monkeypatch):
    for eid in ('a', 'b'):
        client.rows[('users', UID, 'episodes', eid)] = {'title': eid}
    monkeypatch.setattr(episodes, 'unseal', lambda uid, row: row)
    monkeypatch.setattr(store, 'state', lambda *args, **kwargs: {'cursor': 1, 'next_seq': 1})
    member_reads, home_metrics = Mock(return_value={}), Mock()
    monkeypatch.setattr(home_read, 'read_members', member_reads)
    monkeypatch.setattr(home_read.episode_metrics, 'record_home_members', home_metrics)
    rows = {eid: {'id': eid, 'title': eid} for eid in ('a', 'b')}
    worker.compare_rows(UID, rows, {'a': None, 'b': None}, client, cursor=1)
    assert worker._legacy(UID, 'a', client)['id'] == 'a'
    assert member_reads.call_count == 1 and not home_metrics.called


def test_invalid_home_payload_requests_one_urgent_refresh(client, monkeypatch):
    monkeypatch.setattr(
        home_read, 'list_episode_window', lambda *args, **kwargs: ([{'id': 'e', 'home_policy_version': 'old'}], None)
    )
    for _ in range(2):
        with pytest.raises(ValueError, match='episode_home_policy_changed'):
            reads.list_window(UID, NOW, NOW, firestore_client=client)
    assert store.state(UID, firestore_client=client)['next_seq'] == 1
    fact = next(v for k, v in client.rows.items() if k[:3] == ('users', UID, 'episode_facts'))
    event = loads(decrypt(fact['payload'], UID))[0]
    Fold(UID).apply(event)
    assert event == {'kind': 'home_refresh', 'payload': {'eid': 'e'}}


def test_wake_failure_after_publication_keeps_drain_committed(client, monkeypatch):
    monkeypatch.setenv('EPISODES_HOME_ROWS_ENABLED', 'off')
    store.append(
        UID, 'input', [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client, now=NOW
    )
    fact = next(v for k, v in client.rows.items() if k[:3] == ('users', UID, 'episode_facts'))
    monkeypatch.setattr(store, 'fact_page', lambda *args, **kwargs: [fact])
    publish = store.publish

    def append_after_publish(*args, **kwargs):
        result = publish(*args, **kwargs)
        result['scan_at'] = NOW
        return result

    monkeypatch.setattr(store, 'publish', append_after_publish)
    monkeypatch.setattr(worker, 'wake', real_wake)
    monkeypatch.setattr(
        worker.cloud_tasks, 'enqueue_episode_uid_wake', Mock(side_effect=RuntimeError('queue unavailable'))
    )
    fallback = Mock()
    monkeypatch.setattr('utils.observability.fallback.record_fallback', fallback)
    assert worker.drain(UID, firestore_client=client, now=NOW + timedelta(minutes=4)) == 'drained'
    state = store.state(UID, firestore_client=client)
    assert state['cursor'] == state['next_seq'] == 1 and state['lease_owner'] is None
    fallback.assert_called_once()
    assert fallback.call_args.kwargs['outcome'] == 'degraded'


def test_clock_capacity_never_silently_truncates_visibility_deadlines():
    from utils.episodes.log.clock import home_clock

    ids = [str(i) for i in range(129)]
    with pytest.raises(ValueError, match='episode_home_clock_capacity'):
        home_clock({'e': {'conversation_ids': ids}}, {}, {cid: NOW + timedelta(hours=1) for cid in ids}, set(), NOW)


def test_disabled_sweep_still_runs_read_only_retention_guard(client, monkeypatch):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'off')
    from utils.episodes.log import retention

    factory = Mock(return_value=client)
    guard = Mock()
    monkeypatch.setattr(retention, 'guard', guard)
    monkeypatch.setattr(worker, 'get_firestore_client', factory)
    assert worker.sweep() == {'disabled': 1}
    factory.assert_called_once()
    guard.assert_called_once_with(client)


def test_remote_read_rule_overrides_env_and_can_rollback_without_deploy(client, monkeypatch):
    from types import SimpleNamespace
    from utils import omi_flags

    key = 'EPISODES_LOG_READ_PERCENT'
    monkeypatch.setenv(key, '100')
    rules = {}
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: SimpleNamespace(rules=rules))
    assert reads.selected(UID)
    for active, percent, expected in [(False, 100, False), (True, 0, False), (True, 100, True)]:
        rules[key] = omi_flags.FlagRule.from_doc(key, {'active': active, 'rollout_percentage': percent})
        assert reads.selected(UID) is expected
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'off')
    assert reads.selected(UID) is False


@pytest.mark.parametrize('status', ['pending_deletion', 'running', 'completed', None])
def test_accepted_or_invalid_deletion_blocks_new_async_facts_and_leases(client, status):
    client.rows[('account_deletions', UID)] = {'wipe_status': status}
    assert (
        store.append(UID, 'late', [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client)
        is None
    )
    assert store.claim(UID, firestore_client=client) is None
    assert not any(key[:2] == ('users', UID) for key in client.rows)
    with pytest.raises(store.AccountBlocked):
        store.policy_barrier(UID, 'c', 'token', entering=True, firestore_client=client)


def test_deletion_accepted_after_claim_fences_publication_without_recreating_views(client):
    store.append(
        UID, 'before', [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client, now=NOW
    )
    claim = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=3))
    client.rows[('account_deletions', UID)] = {'wipe_status': 'pending_deletion'}
    with pytest.raises(store.LostLease, match='account_deletion_fenced'):
        store.publish(
            UID,
            claim,
            1,
            {},
            {'e': {'title': 'must not resurrect'}},
            {},
            firestore_client=client,
            now=NOW + timedelta(minutes=4),
        )
    assert ('users', UID, 'episode_views', 'e') not in client.rows
    assert store.state(UID, firestore_client=client).get('cursor', 0) == 0
    client.rows[('account_deletions', UID)] = {'wipe_status': 'cancelled'}
    assert store.account_allowed(UID, firestore_client=client)
