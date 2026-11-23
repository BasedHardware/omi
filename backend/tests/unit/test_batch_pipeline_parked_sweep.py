import time
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from database.firestore_read_origin import current_read_origin
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import parked_sweep
from utils.batch_pipeline.parked_sweep import ParkedSweep, summarize

CONTROL_PATH = ('batch_pipeline_dev_leases', parked_sweep.CONTROL)
NOW = 100_000
HOUR = NOW // parked_sweep.HOUR_SECONDS


@pytest.fixture
def sweep_store(monkeypatch):
    monkeypatch.delenv('BATCH_PARKED_JOB_SWEEPER_ENABLED', raising=False)
    monkeypatch.setattr(parked_sweep, 'time', SimpleNamespace(time=lambda: NOW, monotonic=time.monotonic))
    return SimpleNamespace(
        namespace='batch_pipeline_dev',
        client=StrictFirestore(
            {CONTROL_PATH: {'cursors': {'quarantined': 'previous', 'held_expired': 'last-expired'}}},
            require_begun=True,
        ),
    )


def test_sample_uses_bounded_reasons_and_age_buckets():
    rows = [
        {'owner_key': 'a', 'quarantined_at': 1, 'quarantine_diagnostic': {'worker_reason': ['malformed']}},
        {
            'owner_key': 'a',
            'quarantined_at': 99_000,
            'recovery': {'started_at': 1, 'failure': {'reason': 'empty_asr'}},
        },
        {'quarantined_at': float('nan'), 'quarantine_diagnostic': {'exception_class': 'lease_expired'}},
    ]
    assert summarize(rows, 100_000) == {
        'oldest_age_seconds': 99_999,
        'distinct_known_owners': 1,
        'reason_age': [
            {'reason': 'lease_expired', 'age_bucket': 'unknown', 'units': 1},
            {'reason': 'post_submit_empty_asr', 'age_bucket': 'under_1h', 'units': 1},
            {'reason': 'unknown', 'age_bucket': 'at_least_24h', 'units': 1},
        ],
    }


def test_disabled_sweep_does_not_access_store(monkeypatch):
    monkeypatch.setenv('BATCH_PARKED_JOB_SWEEPER_ENABLED', 'false')
    sweep = ParkedSweep(None)
    sweep.tick(100_000)
    assert sweep.last_attempt_hour == -1


def test_hour_admission_rotates_cursor_and_survives_worker_restart(monkeypatch, sweep_store):
    docs = [SimpleNamespace(id=f'job-{i}', to_dict=dict) for i in range(parked_sweep.PAGE_SIZE)]
    scan = Mock(side_effect=[docs, []])
    monkeypatch.setattr(parked_sweep, 'parked_page', scan)

    ParkedSweep(sweep_store).tick(NOW)
    ParkedSweep(sweep_store).tick(NOW)

    assert scan.call_args_list == [
        call(sweep_store.client, sweep_store.namespace, expired=False, after='previous'),
        call(sweep_store.client, sweep_store.namespace, expired=True, after='last-expired'),
    ]
    state = sweep_store.client.rows[CONTROL_PATH]
    assert state['hour'] == HOUR
    assert state['cursors'] == {'quarantined': docs[-1].id, 'held_expired': None}
    assert state['latest_page_sample']['expires_at'] == (HOUR + 1) * parked_sweep.HOUR_SECONDS
    assert state['latest_page_sample']['scanned'] == {'quarantined': parked_sweep.PAGE_SIZE, 'held_expired': 0}
    assert [len(tx.sets) for tx in sweep_store.client.transactions] == [1, 1, 0]


def test_control_kill_during_scan_refuses_checkpoint(monkeypatch, sweep_store):
    def scan(client, namespace, *, expired, after):
        if expired:
            client.rows[CONTROL_PATH]['disabled'] = True
        return []

    monkeypatch.setattr(parked_sweep, 'parked_page', scan)
    ParkedSweep(sweep_store).tick(NOW)

    state = sweep_store.client.rows[CONTROL_PATH]
    assert state == {
        'hour': HOUR,
        'cursors': {'quarantined': 'previous', 'held_expired': 'last-expired'},
        'disabled': True,
    }
    assert [len(tx.sets) for tx in sweep_store.client.transactions] == [1, 0]


def test_partial_stream_failure_counts_rows_and_burns_slot(monkeypatch, sweep_store, caplog):
    def partial_stream():
        assert current_read_origin() == 'job:batch_pipeline_parked_sweep'
        yield SimpleNamespace(id='inspected', to_dict=dict)
        raise TimeoutError

    scan = Mock(return_value=partial_stream())
    monkeypatch.setattr(parked_sweep, 'parked_page', scan)
    with caplog.at_level('INFO'), pytest.raises(TimeoutError):
        ParkedSweep(sweep_store).tick(NOW)
    ParkedSweep(sweep_store).tick(NOW)

    assert 'outcome=dependency_failure scanned={"held_expired": 0, "quarantined": 1} sample=null' in caplog.text
    assert scan.call_count == 1
    assert sweep_store.client.rows[CONTROL_PATH] == {
        'hour': HOUR,
        'cursors': {'quarantined': 'previous', 'held_expired': 'last-expired'},
    }


def test_policy_only_provider_route_is_excluded(monkeypatch, sweep_store):
    def provider():
        return {'policy': {'stt_route': 'provider'}, 'owner_key': 'provider-only'}

    def gpu():
        return {'stt_route': {'stt_route': 'parakeet'}, 'policy': {'stt_route': 'provider'}, 'owner_key': 'gpu'}

    docs = [SimpleNamespace(id='provider', to_dict=provider), SimpleNamespace(id='gpu', to_dict=gpu)]
    monkeypatch.setattr(parked_sweep, 'parked_page', Mock(side_effect=[docs, []]))

    ParkedSweep(sweep_store).tick(NOW)

    sample = sweep_store.client.rows[CONTROL_PATH]['latest_page_sample']
    assert sample['scanned'] == {'quarantined': 2, 'held_expired': 0}
    assert sample['distinct_known_owners'] == 1
    assert sample['reason_age'] == [{'reason': 'unknown', 'age_bucket': 'unknown', 'units': 1}]
