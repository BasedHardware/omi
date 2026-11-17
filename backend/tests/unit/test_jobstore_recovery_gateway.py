"""Approved bounded-hint contract over actual Scheduler/IndexStore source."""

from functools import partial
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

from prometheus_client import CollectorRegistry, generate_latest
import pytest

from database import batch_pipeline_shadow_hook
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.jobstore import index_store
from database.jobstore.index_store import IndexReadReason, IndexStore
from tests.unit.test_jobstore_index_recovery_cadence import LeasedPrimary, SyntheticMirror
from database import batch_pipeline_recovery_discovery as discovery
from utils.batch_pipeline import scheduler
from database.batch_pipeline_recovery_discovery import RecoveryCaller, RecoveryExposure, RecoveryQuery


@pytest.fixture
def route(monkeypatch):
    primary = LeasedPrimary()
    primary.namespace = 'batch_pipeline_prod'
    with discovery._ENTRY_LOCK:
        discovery._LAST_ENTRY.pop(('batch_pipeline_prod', RecoveryCaller.PUMP.value), None)
    primary.due = Mock(wraps=primary.due)
    clock, wall, policy, enabled, configured = [0.0], [1_800_000_010.0], ['role_minute_v1:10000'], [True], [True]
    store = IndexStore(
        SyntheticMirror(primary),
        enabled_queries={'due_leased', 'due_retry', 'due_result_ready'},
        clock=lambda: clock[0],
        recovery_policy=lambda: policy[0],
        enabled=lambda: enabled[0],
    )
    store._index.due = Mock(return_value=['deleted'])
    monkeypatch.setattr(index_store, 'production_policy_applies', lambda ns: ns == 'batch_pipeline_prod')
    monkeypatch.setattr(index_store, 'jobstore_production_mirror_configured', lambda: configured[0])
    monkeypatch.setattr(
        scheduler, 'RecoveryQuery', partial(RecoveryQuery, clock=lambda: clock[0], wall_clock=lambda: wall[0])
    )
    monkeypatch.setenv('CAPTURE_RETRY_CAP_ENFORCED', 'false')
    queue = scheduler.Scheduler(store, recovery_caller=RecoveryCaller.PUMP)
    return SimpleNamespace(
        primary=primary,
        store=store,
        queue=queue,
        clock=clock,
        wall=wall,
        policy=policy,
        enabled=enabled,
        configured=configured,
    )


def add_job(route, key='fresh'):
    route.primary.rows['jobs', key] = {
        'state': 'leased',
        'lease_until': route.wall[0] - 1,
        'attempt': 1,
        'owner_id': 'synthetic',
        'duration_seconds': 1,
    }


def count(event, source='none', reason='index', caller=RecoveryCaller.PUMP):
    return discovery.RECOVERY_DISCOVERY_TOTAL.labels(
        namespace='batch_pipeline_prod',
        caller=caller.value,
        event=event,
        source=source,
        reason=reason,
    )._value.get()


def test_qualified_production_gateway_removes_due_query_only_for_useful_hints(route):
    n, p, h = (
        count('entry', reason='entry'),
        count('primary', 'primary', 'safety_sweep'),
        count('pg_attempt', 'postgres'),
    )
    assert route.queue.recover(route.wall[0]) == 0
    add_job(route)
    route.store._index.due.return_value = ['fresh']
    assert route.queue.recover(route.wall[0]) == 1
    assert route.primary.rows['jobs', 'fresh']['state'] == 'retry'
    assert count('entry', reason='entry') == n + 2
    assert count('primary', 'primary', 'safety_sweep') == p + 1
    assert count('pg_attempt', 'postgres') == h + 1
    assert [c.args[0] for c in route.primary.due.call_args_list] == ['leased', 'retry', 'retry']


def test_all_currently_ineligible_hints_fall_back_before_retry_and_count_work(route):
    route.queue.recover(route.wall[0])
    add_job(route, 'uncopied')
    h = count('pg_attempt', 'postgres')
    p = count('primary', 'primary', 'hint_ineligible')
    candidates = count('candidate', 'postgres', 'no_transition')
    assert route.queue.recover(route.wall[0]) == 1
    assert route.primary.rows['jobs', 'uncopied']['state'] == 'retry'
    assert count('pg_attempt', 'postgres') == h + 1
    assert count('primary', 'primary', 'hint_ineligible') == p + 1
    assert count('candidate', 'postgres', 'no_transition') == candidates + 1
    assert [c.args[0] for c in route.primary.due.call_args_list][-2:] == ['leased', 'retry']


def test_privacy_rejected_hint_does_not_count_as_useful_or_suppress_primary(route):
    route.queue.recover(route.wall[0])
    add_job(route, 'blocked')
    add_job(route, 'uncopied')
    route.store._index.due.return_value = ['blocked']
    original = route.primary.run
    rejected = [False]

    def guarded(body):
        def commit(tx):
            outcome = body(tx)
            if outcome and not rejected[0]:
                rejected[0] = True
                raise BatchPrivacyBlocked('account_deleted')
            return outcome

        return original(commit)

    def quarantine(key, now):
        route.primary.rows['jobs', key]['state'] = 'privacy_blocked'

    route.primary.run = guarded
    route.primary.quarantine_fenced = Mock(side_effect=quarantine)
    useful = count('useful_candidate', 'postgres', 'transition')
    assert route.queue.recover(route.wall[0]) == 1
    assert route.primary.rows['jobs', 'blocked']['state'] == 'privacy_blocked'
    assert route.primary.rows['jobs', 'uncopied']['state'] == 'retry'
    assert count('useful_candidate', 'postgres', 'transition') == useful


@pytest.mark.parametrize(
    'hints', [None, 42, ('tuple',), ['', 'x'], ['same', 'same'], [None], [], list(map(str, range(100)))]
)
def test_invalid_empty_or_full_hints_use_identical_primary(route, hints):
    route.queue.recover(route.wall[0])
    add_job(route)
    route.store._index.due.return_value = hints
    assert route.queue.recover(route.wall[0]) == 1
    assert route.primary.rows['jobs', 'fresh']['state'] == 'retry'


@pytest.mark.parametrize(
    'raw',
    [
        '',
        'true',
        'role_minute_v1:10001',
        'role_minute_v1:-1',
        'role_minute_v1:１００',
        'role_minute_v1:1.0',
        ' role_minute_v1:100',
    ],
)
def test_unset_invalid_policy_never_attempts_sql(route, raw):
    route.policy[0] = raw
    route.queue.recover(route.wall[0])
    add_job(route)
    assert route.queue.recover(route.wall[0]) == 1
    route.store._index.due.assert_not_called()


@pytest.mark.parametrize('caller', [RecoveryCaller.UNKNOWN, 'pump_recovery', 'customer-id'])
def test_unknown_or_untyped_caller_cannot_take_production_exception(route, caller):
    route.queue.recover(route.wall[0], caller=caller)
    add_job(route)
    assert route.queue.recover(route.wall[0], caller=caller) == 1
    route.store._index.due.assert_not_called()


def test_generic_due_and_other_queries_stay_production_refused_even_with_policy(route):
    for _ in range(2):
        for state in ('leased', 'retry', 'result_ready'):
            assert route.store.due(state, route.wall[0]) == []
    route.store._index.due.assert_not_called()


def test_zero_exposure_is_selected_zero_and_keeps_all_work_primary(route):
    route.policy[0] = 'role_minute_v1:0'
    selected = count('selected')
    route.queue.recover(route.wall[0])
    add_job(route)
    assert route.queue.recover(route.wall[0]) == 1
    assert count('selected') == selected
    route.store._index.due.assert_not_called()


def test_dev_gateway_is_default_closed_until_explicit_policy(route):
    route.primary.namespace = 'batch_pipeline_dev'
    store = IndexStore(SyntheticMirror(route.primary), enabled_queries={'due_leased'}, clock=lambda: route.clock[0])
    store._index.due = Mock(return_value=['fresh'])
    queue = scheduler.Scheduler(store, recovery_caller=RecoveryCaller.PUMP)
    assert queue.recover(route.wall[0]) == 0
    add_job(route)
    assert queue.recover(route.wall[0]) == 1
    store._index.due.assert_not_called()
    assert [c.args[0] for c in route.primary.due.call_args_list] == ['leased', 'retry', 'leased', 'retry']


def test_context_cannot_silently_complete_hints_without_candidate_feedback(route):
    with pytest.raises(RuntimeError, match='require current-candidate feedback'):
        with RecoveryQuery(route.primary, route.wall[0], 100, RecoveryCaller.PUMP) as query:
            query.from_pg = True


def test_context_guard_preserves_an_original_candidate_failure(route):
    with pytest.raises(ValueError, match='original candidate failure'):
        with RecoveryQuery(route.primary, route.wall[0], 100, RecoveryCaller.PUMP) as query:
            query.from_pg = True
            raise ValueError('original candidate failure')


def test_invocation_gap_and_cutoff_age_include_actual_migration_delay(route):
    def histogram_value(metric, suffix):
        return sum(
            s.value
            for m in metric.collect()
            for s in m.samples
            if s.name.endswith(suffix) and s.labels == {'namespace': 'batch_pipeline_prod', 'caller': 'pump_recovery'}
        )

    gaps = histogram_value(discovery.CALLER_GAP_SECONDS, '_count')
    ages = histogram_value(discovery.CUTOFF_AGE_SECONDS, '_sum')
    original = route.primary.run

    def slow_migration(body):
        route.clock[0] += 2
        route.wall[0] += 2
        return original(body)

    route.primary.run = slow_migration
    route.queue.recover(route.wall[0])
    route.queue.recover(route.wall[0])
    assert histogram_value(discovery.CALLER_GAP_SECONDS, '_count') == gaps + 1
    assert histogram_value(discovery.CUTOFF_AGE_SECONDS, '_sum') == ages + 4


def test_all_ineligible_feedback_retains_both_optional_parity_observations(route):
    observed = []
    route.store._observe = lambda *args: observed.append(args)
    route.queue.recover(route.wall[0])
    observed.clear()
    route.queue.recover(route.wall[0])
    # PG leased, feedback primary leased, then canonical retry.
    assert [args[1][0] for args in observed] == ['leased', 'leased', 'retry']


@pytest.mark.parametrize('change', ['policy', 'minute', 'kill', 'target', 'deadline'])
def test_live_revocation_and_expiry_during_sql_force_primary(route, change):
    route.queue.recover(route.wall[0])
    add_job(route)

    def read(*args):
        if change == 'policy':
            route.policy[0] = ''
        if change == 'minute':
            route.wall[0] += 60
        if change == 'kill':
            route.enabled[0] = False
        if change == 'target':
            route.configured[0] = False
        if change == 'deadline':
            route.clock[0] += 60
        return ['fresh']

    route.store._index.due.side_effect = read
    assert route.queue.recover(route.wall[0]) == 1
    assert [c.args[0] for c in route.primary.due.call_args_list][-2:] == ['leased', 'retry']


def test_failed_feedback_primary_prevents_retry_and_remains_due(route):
    route.queue.recover(route.wall[0])
    route.primary.due.side_effect = RuntimeError('primary failed')
    with pytest.raises(RuntimeError, match='primary failed'):
        route.queue.recover(route.wall[0])
    assert 'due_leased' not in route.store._last_sweep
    route.primary.due.side_effect = None
    route.store._index.due.reset_mock()
    route.queue.recover(route.wall[0])
    route.store._index.due.assert_not_called()


def test_factory_bypass_entry_and_primary_failure_invalidate_cached_gateway(route):
    route.queue.recover(route.wall[0])
    n = count('entry', reason='entry')
    primary_queue = scheduler.Scheduler(route.primary, recovery_caller=RecoveryCaller.PUMP)
    route.primary.due.side_effect = RuntimeError('bypass failed')
    with pytest.raises(RuntimeError, match='bypass failed'):
        primary_queue.recover(route.wall[0])
    route.primary.due.side_effect = None
    route.store._index.due.reset_mock()
    route.queue.recover(route.wall[0])
    route.store._index.due.assert_not_called()
    assert count('entry', reason='entry') == n + 2


def test_entry_counter_survives_failure_before_factory_dispatch(route):
    n = count('entry', reason='entry')
    route.primary.run = Mock(side_effect=RuntimeError('migration failed'))
    with pytest.raises(RuntimeError, match='migration failed'):
        route.queue.recover(route.wall[0])
    assert count('entry', reason='entry') == n + 1
    route.store._index.due.assert_not_called()


def test_exposure_unit_is_exact_and_restart_replica_stable():
    wall = 1_800_000_010
    text = f'omi:recovery-hints:role-minute:v1:batch_pipeline_prod:pump_recovery:{wall // 60}'
    bucket = int(hashlib.sha256(text.encode('ascii')).hexdigest(), 16) % 10000
    for _replica_or_restart in range(3):
        assert not RecoveryExposure(bucket).selected('batch_pipeline_prod', RecoveryCaller.PUMP, wall)
        assert RecoveryExposure(bucket + 1).selected('batch_pipeline_prod', RecoveryCaller.PUMP, wall + 1)
    assert not RecoveryExposure(0).selected('batch_pipeline_prod', RecoveryCaller.PUMP, wall)
    assert RecoveryExposure(10000).selected('batch_pipeline_prod', RecoveryCaller.PUMP, wall)


def test_collectors_export_actual_bypass_freshness_in_every_mode(route, monkeypatch):
    primary_queue = scheduler.Scheduler(route.primary, recovery_caller=RecoveryCaller.PUMP)
    for mode in ('firestore', 'shadow', 'index', 'invalid'):
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', mode)
        primary_queue.recover(route.wall[0])
        registry = CollectorRegistry()
        for collector in batch_pipeline_shadow_hook.shadow_parity_collectors():
            registry.register(collector)
        exported = generate_latest(registry).decode()
        assert 'omi_jobstore_recovery_discovery_total' in exported
        assert 'omi_jobstore_recovery_caller_gap_seconds' in exported
        assert 'omi_jobstore_index_primary_scan_success_timestamp_seconds' in exported
    for metric in discovery.RECOVERY_DISCOVERY_TOTAL.collect():
        for sample in metric.samples:
            assert sample.labels['namespace'] in {'batch_pipeline_dev', 'batch_pipeline_prod', 'other'}
            assert sample.labels['caller'] in {c.value for c in RecoveryCaller}


@pytest.mark.parametrize('newer', ['full', 'failed'])
def test_older_primary_result_cannot_overwrite_newer_backlog_or_failure(route, newer):
    calls = [0]

    def read(*args):
        calls[0] += 1
        if calls[0] == 1:
            try:
                route.store._primary_due('leased', route.wall[0], 2, 'due_leased', IndexReadReason.SAFETY_SWEEP)
            except RuntimeError:
                pass
            return []
        if newer == 'failed':
            raise RuntimeError('newer failed')
        return ['one', 'two']

    route.primary.due.side_effect = read
    route.store._primary_due('leased', route.wall[0], 2, 'due_leased', IndexReadReason.SAFETY_SWEEP)
    if newer == 'full':
        assert route.store._leased_backlog
    else:
        assert 'due_leased' not in route.store._last_sweep
