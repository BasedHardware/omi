"""Durability, rollback, migration and privacy contracts; no customer IO."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from unittest.mock import Mock

import pytest
from config import episode_log as config
from database import episode_log as store, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.episode_log_support.oracle import Oracle
from utils.episodes import home_read, composer
from utils.encryption import decrypt
from utils.episodes.log import worker, metrics, reads
from utils.episodes.log.policy import home_policy_write
from utils.episodes.log.codec import dumps, loads
from utils.episodes.log.fold import Fold
from utils.episodes.log.key import gate_digest
from utils.episodes.log.backfill import convert

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
UID = 'log-unit-user'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    client = StrictFirestore()
    monkeypatch.setattr(
        store,
        'fact_page',
        lambda u, after, through, limit=64, **kwargs: sorted(
            [
                v
                for k, v in client.rows.items()
                if k[:3] == ('users', u, 'episode_facts') and after < v['seq'] <= through
            ],
            key=lambda v: v['seq'],
        )[:limit],
    )
    return client


def append(client, key='a', now=NOW):
    return store.append(
        UID, key, [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client, now=now
    )


def test_duplicate_key_no_writes_and_payload_sealed(client):
    assert append(client) == NOW + timedelta(minutes=3)
    count = sum(len(t.sets) + len(t.creates) for t in client.transactions)
    assert append(client) is None
    assert sum(len(t.sets) + len(t.creates) for t in client.transactions) == count
    assert 'member_refresh' not in client.rows[('users', UID, 'episode_facts', 'a')]['payload']
    assert all(path[:2] == ('users', UID) for path in client.rows)


def test_drift_sampling_client_failure_never_breaks_serving(client, monkeypatch):
    monkeypatch.setattr(worker.random, 'random', lambda: 0)

    def unavailable():
        raise RuntimeError('client_unavailable')

    monkeypatch.setattr(worker, 'get_firestore_client', unavailable)
    assert worker.sample_read(UID, [{'id': 'episode'}]) is None


def test_debounce_size_and_max_age_bound():
    state = {}
    for n in range(60):
        state = store.dirty_state(state, NOW + timedelta(seconds=n * 30))
        assert state['drain_at'] <= NOW + timedelta(minutes=25)
    for n in range(5):
        at = NOW + timedelta(minutes=35, seconds=n)
        state = store.dirty_state(state, at)
    assert state['drain_at'] == at
    assert 'status' not in state


def test_killed_mid_drain_redrives_and_lost_lease_never_publishes(client):
    append(client)
    first = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=3))
    assert first and store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=4)) is None
    assert not any(path[2] == 'episode_views' for path in client.rows)
    second = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=14))
    assert second['epoch'] == first['epoch'] + 1
    events, cursor = store.read_batch(UID, second, firestore_client=client)
    assert len(events) == 1 and cursor == 1
    assert store.state(UID, firestore_client=client).get('cursor', 0) == 0
    for claimed, at in ((first, NOW + timedelta(minutes=14)), (second, NOW + timedelta(minutes=25))):
        with pytest.raises(store.LostLease):
            store.publish(UID, claimed, 1, {}, {'e': {'id': 'e'}}, {}, firestore_client=client, now=at)
    assert not any(path[2] == 'episode_views' for path in client.rows)


def test_append_during_drain_remains_dirty(client):
    append(client)
    first = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=3))
    append(client, 'b', NOW + timedelta(minutes=4))
    state = store.publish(UID, first, 1, {}, {}, {}, firestore_client=client, now=NOW + timedelta(minutes=4))
    assert state['next_seq'] == 2 and state['cursor'] == 1
    assert state['scan_at'] == NOW + timedelta(minutes=4) and not state['lease_owner']


def test_retry_has_entry_deadline_and_exit(client):
    append(client)
    claimed = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=3))
    at = NOW + timedelta(minutes=4)
    assert store.retry(UID, claimed, firestore_client=client, now=at)
    row = store.state(UID, firestore_client=client)
    assert store.derive_phase(row, at) == 'retrying' and row['retry_at'] == at + timedelta(seconds=30)
    claimed = store.claim(UID, firestore_client=client, now=row['retry_at'])
    assert store.derive_phase(claimed['state'], row['retry_at']) == 'running'


def test_switch_off_no_io(monkeypatch):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'off')
    client = Mock()
    assert store.append(UID, 'k', [], firestore_client=client) is None
    assert store.prepare(Mock(), client, UID) is None
    assert worker.drain(UID, firestore_client=client) == 'disabled'
    assert worker.sweep(firestore_client=client) == {'disabled': 1}
    assert not worker.mark_dirty(UID, 'c', {'id': 'c'}, firestore_client=client)
    assert not client.method_calls


@pytest.mark.parametrize('recorded', [False, True])
def test_switch_off_legacy_activity_never_prepares_log_content(client, monkeypatch, recorded):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'off')
    monkeypatch.setattr(episodes, 'recorded_episodes_enabled', lambda: recorded)
    monkeypatch.setattr(episodes.episode_timeline, 'check_window', lambda *args, **kwargs: None)
    unseal = Mock(side_effect=AssertionError('disabled log decrypted content'))
    monkeypatch.setattr(episodes, 'unseal', unseal)
    path = ('users', UID, 'episodes', 'e')
    client.rows[path] = {
        'id': 'e',
        'status': 'live',
        'started_at': NOW,
        'last_activity_at': NOW,
        'conversation_ids': ['c'],
        'content': 'synthetic-unreadable-content',
    }
    at = NOW + timedelta(seconds=10)
    assert episodes.record_activity(UID, 'e', 'c', at, firestore_client=client) == at
    assert client.rows[path]['last_activity_at'] == at
    assert not any(key[2] in {'episode_facts', 'episode_log_state'} for key in client.rows)
    unseal.assert_not_called()


def test_drift_bounded_and_reread_handles_inflight_writer():
    expected = {'id': 'e', 'status': 'closed', 'title': 'kept'}
    assert set(metrics.compare({'status': 'live'}, expected, reread=lambda: expected).values()) == {'match'}
    observed = metrics.compare(expected, dict(expected, title='changed'))
    assert observed['content_hash'] == 'mismatch' and set(observed) == set(metrics.FIELDS)
    assert metrics.DRIFT._labelnames == ('field', 'outcome')


def test_key_catches_revision_bounds_discard_donor_terminal_state():
    row = {
        'id': 'c',
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=10),
        'sync_content_revision': 4,
        'transcript_segments': [{'text': 'hello', 'start': 0, 'end': 10}],
    }
    initial = gate_digest(row)
    for change in (
        {'discarded': True},
        {'sync_merged_from': ['donor']},
        {'sync_content_revision': 5},
        {'status': 'failed'},
        {'finished_at': NOW + timedelta(seconds=20)},
    ):
        assert gate_digest(dict(row, **change)) != initial
    assert gate_digest(row) == initial


def test_real_atomic_facts_replay_and_checkpoint_resume(client):
    uid = 'proto-u'
    with Oracle(uid) as oracle:
        for cid, a, b in [('a', 0, 60), ('b', 3600, 3660), ('bridge', 1200, 2500)]:
            oracle.attach(cid, NOW + timedelta(seconds=a), NOW + timedelta(seconds=b))
        oracle.discard('a')
        oracle.repoint('b', 'bridge')
        state = store.state(uid, firestore_client=oracle.store)
        events, _ = store.read_batch(uid, {'state': state}, firestore_client=oracle.store)
        fold = Fold(uid)
        for event in events[:2]:
            fold.apply(event)
        fold = Fold(uid, loads(dumps(fold.checkpoint())))
        for event in events[2:]:
            fold.apply(event)
        actual = fold.rows()
        for path, row in oracle.store.rows.items():
            if path[:3] != ('users', uid, 'episodes'):
                continue
            for field in (
                'started_at',
                'last_activity_at',
                'recorded_members',
                'conversation_ids',
                'discarded_conversation_ids',
                'member_activity',
                'recorded_merged_into',
            ):
                left, right = actual[path[-1]].get(field), row.get(field)
                if field in {'conversation_ids', 'discarded_conversation_ids'}:
                    left, right = sorted(left or []), sorted(right or [])
                assert left == right, (path[-1], field)


def test_backfill_dry_run_fingerprint_archives_redirect_fences(client):
    row = {
        'id': 'fixed',
        'status': 'closed',
        'started_at': NOW,
        'last_activity_at': NOW,
        'composed_fingerprint': 'paid',
        'composed_notes': 'notes',
        'composer_version': 3,
        'wrap_up_requested_at': NOW,
        'conversation_ids': ['c'],
    }
    records = [
        {'namespace': 'episodes', 'id': 'fixed', 'data': row},
        {'namespace': 'episodes', 'id': 'old', 'data': dict(row, id='old', recorded_merged_into='fixed')},
        {'namespace': 'episode_links', 'id': 'c', 'data': {'episode_id': 'fixed'}},
        {'namespace': 'episode_segment_receipts', 'id': 'content-v1:c', 'data': {'ids': ['new']}},
        {'namespace': 'receipt_archive', 'id': 'content-v1:c', 'archive': 0, 'data': {'ids': ['old']}},
    ]
    assert convert(UID, records, firestore_client=client)['written'] == 0 and not client.rows
    convert(UID, records, apply=True, firestore_client=client)
    events, _ = store.read_batch(UID, {'state': store.state(UID, firestore_client=client)}, firestore_client=client)
    fold = Fold(UID)
    for event in events:
        fold.apply(event)
    assert fold.rows()['fixed']['composed_fingerprint'] == 'paid'
    assert fold.rows()['old']['recorded_merged_into'] == 'fixed'
    assert fold.receipts['content-v1:c'] == ['new', 'old']
    assert fold.links['c']['episode_id'] == 'fixed' and fold.projector.episodes[0].fixed


def test_policy_barrier_blocks_reads_recovers_at_deadline(client, monkeypatch):
    monkeypatch.setattr(reads, 'selected', lambda uid: True)
    store.policy_barrier(UID, 'c', 't', entering=True, firestore_client=client, now=NOW)
    assert reads.ready(UID, firestore_client=client) is None
    store.recover_policy_barriers(UID, firestore_client=client, now=NOW + timedelta(minutes=26))
    row = store.state(UID, firestore_client=client)
    assert not row['policy_barriers'] and row['next_seq'] == 2 and row['scan_at'] == NOW + timedelta(minutes=26)


def test_conditional_version_scoped_to_user_window_page_policy(monkeypatch):
    state = {'home_version': 5}
    a = reads.version(UID, state, NOW, NOW + timedelta(days=1), 50, None)
    assert a != reads.version('other', state, NOW, NOW + timedelta(days=1), 50, None)
    assert a != reads.version(UID, state, NOW, NOW + timedelta(days=2), 50, None)
    assert a != reads.version(UID, state, NOW, NOW + timedelta(days=1), 50, 'page2')
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'off')
    assert a != reads.version(UID, state, NOW, NOW + timedelta(days=1), 50, None)


def test_real_drain_recovers_failure_publishes_sealed_home_and_never_changes_legacy(client, monkeypatch):

    uid = 'proto-u'
    with Oracle(uid) as oracle:
        oracle.attach('c', NOW, NOW + timedelta(seconds=60))
    client = oracle.store
    monkeypatch.setattr(
        store,
        'fact_page',
        lambda u, after, through, limit=64, **kwargs: sorted(
            [
                v
                for k, v in client.rows.items()
                if k[:3] == ('users', u, 'episode_facts') and after < v['seq'] <= through
            ],
            key=lambda v: v['seq'],
        )[:limit],
    )
    monkeypatch.setattr(episodes, 'unseal', lambda uid, row: row)
    monkeypatch.setattr(
        home_read,
        'read_members',
        lambda *args, **kwargs: {
            'c': {
                'structured': {'title': 'Synthetic member', 'emoji': '🗒️'},
                'started_at': NOW,
                'status': 'completed',
                'discarded': False,
            },
        },
    )
    paid = Mock(side_effect=AssertionError('drain invoked paid composer'))
    monkeypatch.setattr(composer, 'compose', paid)
    legacy = {k: deepcopy(v) for k, v in client.rows.items() if k[2] in {'episodes', 'episode_links', 'conversations'}}
    store.finish_backfill(uid, firestore_client=client)
    at = store.state(uid, firestore_client=client)['drain_at']
    publish = store.publish
    monkeypatch.setattr(store, 'publish', Mock(side_effect=RuntimeError('synthetic killed drain')))
    with pytest.raises(RuntimeError, match='synthetic killed drain'):
        worker.drain(uid, firestore_client=client, now=at)
    pending = store.state(uid, firestore_client=client)
    assert pending.get('cursor', 0) == 0 and pending['retry_at']
    monkeypatch.setattr(store, 'publish', publish)
    monkeypatch.setattr(worker, 'wake', lambda *args: None)
    assert worker.drain(uid, firestore_client=client, now=pending['retry_at']) == 'drained'
    assert store.state(uid, firestore_client=client)['cursor'] == pending['next_seq']
    assert store.checkpoint(uid, firestore_client=client)['metadata']
    view = next(v for k, v in client.rows.items() if k[2] == 'episode_views')
    home = loads(decrypt(view['home_payload'], uid))
    assert home['members'][0]['title'] == 'Synthetic member'
    assert 'Synthetic member' not in view['home_payload']
    assert all(client.rows[k] == value for k, value in legacy.items())
    paid.assert_not_called()


def test_member_policy_dirty_fact_joins_conversation_commit_only_for_existing_log(client):
    root = client.collection('users').document(UID)
    ref = root.collection('conversations').document('c')
    client.rows[ref.path] = {'discarded': False}

    @firestore.transactional
    def change(transaction):
        capture = store.prepare_member_change(transaction, root)
        ref.get(transaction=transaction)
        store.member_changed(capture, ['c'])
        transaction.update(ref, {'discarded': True})

    change(client.transaction())
    assert not any(path[2] == 'episode_facts' for path in client.rows)
    client.rows[('users', UID, 'episode_log_state', 'owner')] = {'cursor': 0, 'next_seq': 0}
    change(client.transaction())
    assert store.state(UID, firestore_client=client)['next_seq'] == 1
    assert client.rows[ref.path]['discarded']


def test_backfilled_wedge_remains_nonautomatic_in_the_materialized_view():
    row = {
        'id': 'wedge',
        'status': 'closed',
        'close_reason': 'gap',
        'started_at': NOW,
        'last_activity_at': NOW,
        'conversation_ids': ['c'],
    }
    fold = Fold(UID)
    fold.apply({'kind': 'fence', 'payload': {'row': row}})
    assert 'recorded_members' not in fold.rows()['wedge']
    restored = Fold(UID, loads(dumps(fold.checkpoint())))
    assert 'recorded_members' not in restored.rows()['wedge'] and restored.projector.episodes[0].fixed


def test_drift_ignores_volatile_wire_clock_and_absent_empty_content():
    left = {'status': 'closed', 'home_row': {'members': [], 'state_updated_at': NOW}}
    right = {
        'status': 'closed',
        'title': '',
        'bullets': [],
        'home_row': {'members': [], 'state_updated_at': NOW + timedelta(seconds=1)},
    }
    assert set(metrics.differences(left, right).values()) == {'match'}


def test_caught_up_policy_barrier_still_has_queued_deadline_and_recovery(client):
    store.policy_barrier(UID, 'c', 'token', entering=True, firestore_client=client, now=NOW)
    claimed = store.claim(UID, firestore_client=client, now=NOW + timedelta(minutes=3))
    row = store.publish(UID, claimed, 1, {}, {}, {}, firestore_client=client, now=NOW + timedelta(minutes=4))
    assert row['cursor'] == row['next_seq']
    assert store.derive_phase(row, NOW + timedelta(minutes=4)) == 'queued'
    assert row['queued_entered_at'] == NOW and row['scan_at'] == row['queued_deadline_at'] == NOW + timedelta(
        minutes=25
    )
    prior = store.recover_policy_barriers(UID, firestore_client=client, now=NOW + timedelta(minutes=26))
    assert prior['queued_deadline_at'] == NOW + timedelta(minutes=25)
    assert store.state(UID, firestore_client=client)['next_seq'] == 2


def test_drift_only_counts_a_stable_caught_up_watermark(client, monkeypatch):
    monkeypatch.setenv('EPISODES_HOME_ROWS_ENABLED', 'off')
    path = ('users', UID, 'episode_log_state', 'owner')
    client.rows[path] = {'cursor': 1, 'next_seq': 2, 'home_version': 1, 'epoch': 1}
    legacy = Mock(return_value={'id': 'e', 'title': 'same'})
    compare = Mock()
    monkeypatch.setattr(worker, '_legacy', legacy)
    monkeypatch.setattr(metrics, 'compare', compare)
    worker.compare_rows(UID, {'e': {'id': 'e', 'title': 'same'}}, {}, client, cursor=1)
    legacy.assert_not_called()
    compare.assert_not_called()
    client.rows[path]['next_seq'] = 1
    worker.compare_rows(UID, {'e': {'id': 'e', 'title': 'same'}}, {}, client, cursor=1)
    assert compare.call_count == 1
    compare.reset_mock()

    def concurrent_append(*args):
        client.rows[path]['next_seq'] = 2
        return {'id': 'e', 'title': 'newer legacy'}

    legacy.side_effect = concurrent_append
    worker.compare_rows(UID, {'e': {'id': 'e', 'title': 'same'}}, {}, client, cursor=1)
    compare.assert_not_called()


def test_read_sampling_waits_for_backfill_then_caps_at_three_rows(client, monkeypatch):
    monkeypatch.setenv('EPISODES_HOME_ROWS_ENABLED', 'off')
    monkeypatch.setattr(worker.random, 'random', lambda: 0)
    monkeypatch.setattr(episodes, 'unseal', lambda uid, row: row)
    legacy = Mock(return_value={'title': 'same'})
    compare = Mock()
    monkeypatch.setattr(worker, '_legacy', legacy)
    monkeypatch.setattr(metrics, 'compare', compare)
    path = ('users', UID, 'episode_log_state', 'owner')
    client.rows[path] = {'cursor': 1, 'next_seq': 1, 'home_version': 1, 'epoch': 1}
    rows = [{'id': str(index)} for index in range(4)]
    for row in rows:
        client.rows[('users', UID, 'episode_views', row['id'])] = {'title': 'same'}
    worker.sample_read(UID, rows, firestore_client=client)
    compare.assert_not_called()
    client.rows[path]['backfill_complete'] = True
    worker.sample_read(UID, rows, firestore_client=client)
    assert compare.call_count == legacy.call_count == 3


@pytest.mark.parametrize('enabled', ['on', 'off'])
@pytest.mark.parametrize('fails', [False, True])
def test_shadow_member_policy_edits_dirty_before_read_flip(client, monkeypatch, enabled, fails):
    monkeypatch.setenv('EPISODES_LOG_READ_PERCENT', '0')
    monkeypatch.setenv('EPISODES_LOG_ENABLED', enabled)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    path = ('users', UID, 'episode_log_state', 'owner')
    client.rows[path] = {'cursor': 0, 'next_seq': 0}

    @home_policy_write(firestore_client=lambda: client)
    def edit(uid, conversation_id):
        assert bool(client.rows[path].get('policy_barriers')) == (enabled == 'on')
        if fails:
            raise ValueError('synthetic failed member write')
        return 'edited'

    if fails:
        with pytest.raises(ValueError, match='synthetic failed member write'):
            edit(UID, 'c')
    else:
        assert edit(UID, 'c') == 'edited'
    assert not client.rows[path].get('policy_barriers')
    assert client.rows[path]['next_seq'] == (2 if enabled == 'on' else 0)


def test_bounded_sweep_rotates_disabled_and_failed_users_without_changing_deadlines(client, monkeypatch):
    for uid in ('a-disabled', 'b-failed', 'c-healthy'):
        client.rows[('users', uid, 'episode_log_state', 'owner')] = {
            'cursor': 0,
            'next_seq': 1,
            'scan_at': NOW - timedelta(seconds=1),
            'drain_at': NOW,
            'queued_entered_at': NOW - timedelta(minutes=25),
            'queued_deadline_at': NOW,
        }

    def due(now, **kwargs):
        return sorted(
            (key[1], deepcopy(value))
            for key, value in client.rows.items()
            if key[2] == 'episode_log_state' and value['scan_at'] <= now
        )[:2]

    monkeypatch.setattr(store, 'due_owners', due)
    monkeypatch.setattr(config, 'enabled', lambda uid: uid != 'a-disabled')
    wake = Mock(side_effect=[RuntimeError('synthetic task dispatch failure'), None])
    monkeypatch.setattr(worker.cloud_tasks, 'enqueue_episode_uid_wake', wake)
    first = worker.sweep(firestore_client=client, now=NOW)
    second = worker.sweep(firestore_client=client, now=NOW)
    assert first == {'scanned': 2, 'redriven': 0, 'error': 1}
    assert second == {'scanned': 1, 'redriven': 1, 'error': 0}
    assert wake.call_args.args[0] == 'c-healthy'
    for uid in ('a-disabled', 'b-failed', 'c-healthy'):
        state = store.state(uid, firestore_client=client)
        assert state['scan_at'] == NOW + timedelta(minutes=2)
        assert state['drain_at'] == state['queued_deadline_at'] == NOW
        assert not store.redrive_scan(uid, dict(state, next_seq=0), firestore_client=client, now=NOW)


def test_expired_policy_clock_is_not_counted_as_projection_drift(client, monkeypatch):
    path = ('users', UID, 'episode_log_state', 'owner')
    client.rows[path] = {
        'cursor': 1,
        'next_seq': 1,
        'home_valid_until': datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    legacy = Mock()
    monkeypatch.setattr(worker, '_legacy', legacy)
    worker.compare_rows(UID, {'e': {'id': 'e'}}, {}, client, cursor=1)
    legacy.assert_not_called()


def test_pending_metadata_only_close_dirties_shadow_once(client, monkeypatch):
    from database import episode_timeline
    from utils.episodes.timeline import choose_recorded_episode

    monkeypatch.setenv('EPISODE_ATTACH_READ_OPTIMIZATIONS_ENABLED', 'on')
    with Oracle(UID) as oracle:
        oracle.attach('c', NOW, NOW + timedelta(minutes=2))
        path = ('users', UID, 'conversations', 'c')
        oracle.store.rows[path].update(
            source='omi',
            server_batch_audio_closed=True,
            server_batch_audio_start=NOW.timestamp(),
            server_batch_audio_end=(NOW + timedelta(minutes=2)).timestamp(),
        )
        before = store.state(UID, firestore_client=oracle.store)['next_seq']

        def close():
            return episode_timeline.attach_recorded(
                UID,
                'c',
                'omi',
                NOW,
                NOW + timedelta(minutes=2),
                choose=choose_recorded_episode,
                new_episode={},
                firestore_client=oracle.store,
                pending_at=NOW,
            )

        close()
        assert store.state(UID, firestore_client=oracle.store)['next_seq'] == before + 1
        deadline = oracle.store.rows[path]['episode_transcription_deadline_at']
        close()
        assert store.state(UID, firestore_client=oracle.store)['next_seq'] == before + 1
        assert oracle.store.rows[path]['episode_transcription_deadline_at'] == deadline


@pytest.mark.parametrize('entry', ['member', 'home_clock', 'home_refresh'])
def test_failed_wakes_emit_shared_degraded_metric_without_customer_labels(client, monkeypatch, caplog, entry):
    from utils.metrics import OMI_FALLBACK_TOTAL

    monkeypatch.setattr(store, 'append', Mock(return_value=NOW))
    enqueue = Mock(side_effect=RuntimeError(UID + ': private audio text'))
    monkeypatch.setattr(worker.cloud_tasks, 'enqueue_episode_uid_wake', enqueue)
    counter = OMI_FALLBACK_TOTAL.labels(
        component='sync_dispatch',
        from_mode='episode_cloud_task',
        to_mode='episode_sweep',
        reason='enqueue_failed',
        outcome='degraded',
    )
    before = counter._value.get()
    if entry == 'member':
        assert worker.mark_dirty(UID, 'c', {'status': 'completed'}) is True
    elif entry == 'home_clock':
        worker.note_home_clock(UID, {'home_refresh_cid': 'c', 'home_valid_until': NOW})
    else:
        worker.note_home_refresh(UID, 'e', 'refresh')
    assert enqueue.call_count == 1
    assert counter._value.get() == before + 1
    assert 'reason=enqueue_failed outcome=degraded' in caplog.text
    assert UID not in caplog.text and 'private audio text' not in caplog.text


def test_successful_wake_does_not_emit_degraded_metric(monkeypatch):
    from utils.metrics import OMI_FALLBACK_TOTAL

    monkeypatch.setattr(worker.cloud_tasks, 'enqueue_episode_uid_wake', Mock())
    counter = OMI_FALLBACK_TOTAL.labels(
        component='sync_dispatch',
        from_mode='episode_cloud_task',
        to_mode='episode_sweep',
        reason='enqueue_failed',
        outcome='degraded',
    )
    before = counter._value.get()
    worker.wake(UID, NOW)
    assert counter._value.get() == before
