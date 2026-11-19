"""Pin the packing estimate, coverage and kill switch without a live store."""

from time import monotonic
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from config import batch_pipeline_packing as config
from database.batch_pipeline_store import FirestoreStore
from database.firestore_read_origin import current_read_origin
from database.jobstore.postgres_store import PostgresStore
from utils.batch_pipeline.packing_counterfactual import (
    PackingMetrics,
    build_pack,
    entitlement_class,
    intake_observations,
    sampled,
    source_bounds,
)


def row(segment='first', start=100, duration=100, *, key='compatible', scope='one', state='ready', **fields):
    return {
        'segment_id': segment,
        'duration_seconds': duration,
        'state': state,
        'priority': 0,
        'attempt': 1,
        'available_at': 1,
        'enqueued_at': 1,
        'packing_observation': {
            'version': 1,
            'scope': scope,
            'start': start,
            'end': start + duration,
            'key': key,
            'seconds': duration - 10,
            'entitlement': 'free',
            'age': 'under_1h',
        },
        **fields,
    }


@pytest.mark.parametrize(
    'following,gap,ceiling,predecessor,capped,reason,members',
    [
        ([row('next', 260)], 60, 600, False, False, 'exhausted', 2),
        ([row('next', 261)], 60, 600, False, False, 'gap', 1),
        ([row('next', 199)], 300, 600, False, False, 'gap', 1),
        ([row('next', 200, key='other'), row('later', 300)], 60, 600, False, False, 'incompatible_key', 1),
        ([row('next', 220, available_at=11)], 60, 600, False, False, 'not_ready', 1),
        ([row('next', 220, state='retry')], 60, 600, False, False, 'not_ready', 1),
        ([row('next', 220, duration=501)], 60, 600, False, False, 'size', 1),
        ([row('next', 220)], 60, 600, True, False, 'predecessor', 1),
        ([], 60, 600, False, True, 'scan_cap', 1),
        ([row(str(i), 200 + i * 100) for i in range(16)], 60, 3600, False, True, 'count', 16),
    ],
)
def test_first_stop_and_original_seconds(following, gap, ceiling, predecessor, capped, reason, members):
    result = build_pack(
        row(), following, when=10, max_gap=gap, max_seconds=ceiling, predecessor=predecessor, capped=capped
    )
    assert (result.stop, result.members, result.seconds) == (reason, members, 90 * members)


def test_unknown_source_has_no_eligible_seconds():
    result = build_pack(
        row(packing_observation={}), [], when=10, max_gap=60, max_seconds=600, predecessor=False, capped=False
    )
    assert (result.stop, result.members, result.seconds) == ('unknown_source', 0, 0)


@pytest.mark.parametrize(
    'invalid_duration', [{}, {'duration_seconds': float('nan')}, {'duration_seconds': float('inf')}]
)
@pytest.mark.parametrize('invalid_anchor', [True, False])
def test_unknown_duration_keeps_the_valid_prefix(invalid_duration, invalid_anchor):
    anchor, candidate = row(), row('next', 200)
    invalid = anchor if invalid_anchor else candidate
    del invalid['duration_seconds']
    invalid.update(invalid_duration)

    result = build_pack(anchor, [candidate], when=10, max_gap=60, max_seconds=600, predecessor=False, capped=False)

    assert result.stop == 'unknown_duration'
    assert (result.members, result.seconds) == ((0, 0) if invalid_anchor else (1, 90))


def test_intake_freezes_newest_source_age_and_scopes_key():
    start = 1_710_000_000
    first = SimpleNamespace(capture_at=start, duration_seconds=20, source_frames=16_000 * 15)
    newest = SimpleNamespace(capture_at=start + 900, duration_seconds=10, source_frames=16_000 * 10)
    proof = {'stt_language': 'en', 'stt_language_evidence': 'declared'}
    bounds = {
        'a': (source_bounds(first, trustworthy=True), proof),
        'b': (source_bounds(newest, trustworthy=True), proof),
    }
    assert bounds['a'][0] == (start, start + 20, 15)
    arguments = {
        'uid': 'private-owner',
        'conversation_id': 'private-conversation',
        'source': 'omi',
        'client_device_id': 'private-device',
        'client_platform': 'ios',
        'should_lock': False,
        'lane': 'fresh',
        'paths': ['wal_0_1_2.bin'],
        'intake_context': {'recording_session_id': 'private-session', 'geolocation': {'lat': 1, 'long': 2}},
    }
    common = {
        'subscription': {'plan': 'basic', 'status': 'active'},
        'protection': SimpleNamespace(level='enhanced', generation=2),
        'policy': SimpleNamespace(policy_id='policy'),
        'priority': 0,
        'release': None,
        'now': start + 4000,
        'packable': True,
    }
    a = intake_observations(arguments, bounds, **common)
    assert a['a']['age'] == a['b']['age'] == 'under_1h'
    assert a['a']['seconds'] == 15
    assert a['a']['key'] == a['b']['key']
    assert 'private-' not in str(a) and 'geolocation' not in str(a)
    changed = {**arguments, 'intake_context': {**arguments['intake_context'], 'recording_session_id': 'other'}}
    b = intake_observations(changed, bounds, **common)
    assert b['a']['scope'] != a['a']['scope'] and b['a']['key'] != a['a']['key']
    assert source_bounds(first, trustworthy=False) is None
    mixed = intake_observations(arguments, {**bounds, 'unknown': (None, {})}, **common)
    assert mixed['a']['age'] == 'unknown' and 'key' not in mixed['a']


def test_unidentified_stripe_status_is_unknown():
    stripe = {'plan': 'operator', 'status': 'active', 'stripe_subscription_id': 's', 'current_period_end': 20}
    assert entitlement_class('u', stripe, None, 10) == 'unknown'
    assert entitlement_class('u', stripe, 'trial', 10) == 'trial'
    assert entitlement_class('u', stripe, 'conversion', 10) == 'paid'
    assert entitlement_class('omi-release-probe', stripe, None, 10) == 'exempt'


@pytest.mark.parametrize('raw,rate', [('0', 0.0), ('0.01', 0.01), ('NaN', 0.001), ('0.1', 0.001), ('bad', 0.001)])
def test_rate_is_bounded(monkeypatch, raw, rate):
    monkeypatch.setenv('BATCH_PIPELINE_PACKING_SAMPLE_RATE', raw)
    assert config.sample_rate() == rate
    assert sampled('00000000', rate) == (rate > 0)
    assert not sampled('ffffffff', rate)


def test_firestore_probe_has_one_bounded_unretried_stream(monkeypatch):
    emulator_host = '127.0.0.1:1'
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', emulator_host)
    client = Mock(_emulator_host=emulator_host)
    query = client.collection.return_value
    for method in ('where', 'order_by', 'select', 'limit'):
        getattr(query, method).return_value = query
    query.stream.return_value = []
    store = FirestoreStore('batch_pipeline_test_probe', firestore_client=client)

    assert store.packing_candidates('owner') == []
    query.limit.assert_called_once_with(config.PAGE_ROWS)
    query.stream.assert_called_once_with(timeout=config.READ_TIMEOUT_SECONDS, retry=None)


def test_postgres_probe_uses_only_an_idle_connection_with_a_statement_deadline():
    connection = Mock()
    connection.transaction.return_value = nullcontext()
    connection.execute.return_value.fetchall.return_value = []
    pool = Mock()
    pool.connection.return_value = nullcontext(connection)
    store = PostgresStore('batch_pipeline_test_probe', pool=pool, customer_client=None)

    assert store.packing_candidates('owner') == []
    pool.connection.assert_called_once_with(timeout=0, existing_only=True)
    assert connection.execute.call_count == 2
    assert connection.execute.call_args_list[0].args == (
        f'SET LOCAL statement_timeout = {int(config.READ_TIMEOUT_SECONDS * 1000)}',
    )


@pytest.mark.parametrize('receipt_attempt,members', [(1, 2), (2, 1)])
def test_projected_read_origin_grid_and_completion_labels(monkeypatch, receipt_attempt, members):
    monkeypatch.setenv('BATCH_PIPELINE_PACKING_SAMPLE_RATE', '0.001')
    registry = CollectorRegistry()
    metrics = PackingMetrics(registry)
    anchor = row(state='leased')

    def candidates(owner):
        assert owner == 'private-owner'
        assert current_read_origin() == 'job:batch_packing_counterfactual'
        return [anchor, row('next', 260, state='leased'), row('new-arrival', 400, enqueued_at=11)]

    store = SimpleNamespace(packing_candidates=candidates)
    metrics._read(store, 'private-owner', 'first', 0, 1, 10, 3600, monotonic(), {'next': receipt_attempt})
    metrics.complete(anchor['packing_observation'])
    assert registry.get_sample_value('omi_batch_pipeline_packing_due_depth_sum', {'coverage': 'complete'}) == members
    assert registry.get_sample_value('omi_batch_pipeline_packing_capture_gap_seconds_sum', {'kind': 'gap'}) == 60
    for gap in config.GAP_SECONDS:
        for size in config.PACK_SECONDS:
            labels = {'gap': str(gap), 'size': str(size)}
            assert registry.get_sample_value('omi_batch_pipeline_packing_members_sum', labels) == members
            assert (
                registry.get_sample_value('omi_batch_pipeline_packing_eligible_seconds_total', labels) == 90 * members
            )
    for event in ('leased_sample', 'completed'):
        labels = {'event': event, 'entitlement': 'free', 'source_age': 'under_1h'}
        assert registry.get_sample_value('omi_batch_pipeline_packing_cohort_units_total', labels) == 1

    monkeypatch.setenv('BATCH_PIPELINE_PACKING_SAMPLE_RATE', '0')
    metrics._read(store, 'does-not-read', 'first', 0, 1, 10, 3600, monotonic(), {})
    metrics.complete(anchor['packing_observation'])
    assert registry.get_sample_value('omi_batch_pipeline_packing_samples_total', {'outcome': 'stale'}) is None
    assert registry.get_sample_value('omi_batch_pipeline_packing_samples_total', {'outcome': 'unavailable'}) is None
