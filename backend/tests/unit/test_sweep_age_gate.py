"""Non-mutating re-wake admission: queue scope, age boundary and rollback."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from config.policy import sweep_age
from tests.unit.test_sync_reprocess_coalesce import state, sweep_query  # noqa: F401
from utils.enrichment import outbox
from utils.observability.sweep_age import SKIPPED, skip_ancient


@pytest.mark.parametrize('queue', ['provider-stt', 'enrichment-fresh'])
@pytest.mark.parametrize('raw', ['', 'invalid', 'nan', 'inf', '-1', '0', '3651'])
def test_malformed_age_config_uses_default(monkeypatch, queue, raw):
    name = 'BATCH_PIPELINE_' + queue.upper().replace('-', '_') + '_SWEEP_MAX_AGE_DAYS'
    monkeypatch.setenv(name, raw)
    assert sweep_age.max_age_seconds(queue) == 14 * 86400


@pytest.mark.parametrize('raw', ['', 'invalid', 'false', '0', 'on'])
def test_only_off_disables_gate(monkeypatch, raw):
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', raw)
    assert sweep_age.enabled()


@pytest.mark.parametrize('queue,field', [('provider-stt', 'created_at'), ('enrichment-fresh', 'first_pending_at')])
@pytest.mark.parametrize('value', [None, 'bad', True, 0, -1, float('nan'), float('inf')])
def test_unknown_age_keeps_wake(queue, field, value):
    assert not skip_ancient({field: value}, queue, now=2_000_000)


@pytest.fixture(scope='module')
def served_provider_stt_sweep_days() -> str:
    """Read immutable deployment config once, outside the six age-boundary calls."""
    import yaml

    from pathlib import Path

    manifest = yaml.safe_load((Path(__file__).parents[2] / 'deploy' / 'runtime_env.yaml').read_text())
    found = []

    def walk(node, service=None):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == 'BATCH_PIPELINE_PROVIDER_STT_SWEEP_MAX_AGE_DAYS' and isinstance(value, dict):
                    found.append(str(value.get('value')))
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(manifest)
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize(
    'age_days,skipped', [(13.5, False), (14.5, False), (28.5, False), (29.08, False), (29.9, False), (30.5, True)]
)
def test_served_provider_stt_gate_repairs_held_rows_but_never_past_the_staged_audio(
    monkeypatch, served_provider_stt_sweep_days, age_days, skipped
):
    """Lost-wake repair lasts while the staged audio can be fetched, and no longer."""
    from utils.batch_pipeline.input_retention import TERMINAL_SECONDS

    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_STT_SWEEP_MAX_AGE_DAYS', served_provider_stt_sweep_days)
    # Repair must outlast the pipeline's own 29-day end, where a 2 h hold can still come due,
    # and stop at the staging bucket's 30-day lifecycle (deploy/storage-lifecycle/retention_contract.json).
    assert TERMINAL_SECONDS + 7200 < sweep_age.max_age_seconds('provider-stt') <= 30 * 86400
    now = 100 * 86400.0
    assert skip_ancient({'created_at': now - age_days * 86400}, 'provider-stt', now=now) is skipped


@pytest.mark.parametrize(
    'age,setting,skipped', [(15, 'on', True), (1, 'on', False), (14, 'on', False), (15, 'off', False)]
)
@pytest.mark.parametrize('injected', [False, True])
def test_enrichment_sweep_skips_without_mutation(state, sweep_query, monkeypatch, age, setting, skipped, injected):
    rows, tasks = state
    now = 2_000_000.0
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', setting)
    monkeypatch.delenv('BATCH_PIPELINE_ENRICHMENT_FRESH_SWEEP_MAX_AGE_DAYS', raising=False)
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    outbox.mark('u', 'c', 'en', now=now - age * 86400)
    row_id = outbox.key('u', 'c')
    rows[row_id]['dispatch']['queue'] = 'enrichment-fresh'
    original = deepcopy(rows)
    tasks.clear()
    sweep_query.stream.side_effect = lambda: [
        SimpleNamespace(id=key, to_dict=lambda key=key: deepcopy(rows[key])) for key in rows
    ]
    counter = SKIPPED.labels(queue='enrichment-fresh', reason='max_age')
    before = counter._value.get()
    kwargs = {'wake': lambda row: tasks.append(deepcopy(row))} if injected else {}
    result = outbox.sweep(now=now, **kwargs)
    assert result == {'repaired': 0 if skipped else 1, 'error': 0}
    assert len(tasks) == (0 if skipped else 1)
    assert counter._value.get() - before == int(skipped)
    if skipped:
        assert rows == original


def test_existing_parking_precedes_ancient_fresh_sweep(state, sweep_query, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'on')
    outbox.mark('u', 'c', 'en', now=100)
    key = outbox.key('u', 'c')
    rows[key]['dispatch']['queue'] = 'enrichment-fresh'
    original = deepcopy(rows)
    tasks.clear()
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    sweep_query.stream.side_effect = lambda: [SimpleNamespace(id=key, to_dict=lambda: deepcopy(rows[key]))]
    assert outbox.sweep(now=2_000_000) == {'repaired': 0, 'error': 0}
    parked = rows[key]
    assert parked['age_gate_parked'] and parked['dormant'] and parked['due_at'] is None
    assert parked['deferred_reason'] == 'age_gate_72h' and not tasks
    assert parked['first_pending_at'] == original[key]['first_pending_at']
    assert parked['version'] == original[key]['version']
    assert parked['uid'] == original[key]['uid']


def test_other_enrichment_queues_keep_old_behavior(state, sweep_query, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'on')
    outbox.mark('u', 'c', 'en', now=100)
    tasks.clear()
    assert outbox.sweep(now=2_000_000) == {'repaired': 1, 'error': 0}
    assert len(tasks) == 1


@pytest.mark.parametrize('config', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_skip_counter_passes_existing_gmp_keep_lists(config):
    import re
    from pathlib import Path
    import yaml

    path = Path(__file__).resolve().parents[2] / 'deploy' / config
    monitoring = yaml.safe_load(path.read_text())
    rules = monitoring['spec']['endpoints'][0]['metricRelabeling']
    metric = 'omi_batch_pipeline_sweep_skipped_total'
    for rule in rules:
        if rule.get('sourceLabels') == ['__name__']:
            matched = re.fullmatch(rule['regex'], metric) is not None
            if rule['action'] == 'keep':
                assert matched
            elif rule['action'] == 'drop':
                assert not matched


def test_per_queue_limits_are_independent(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_STT_SWEEP_MAX_AGE_DAYS', '20')
    monkeypatch.setenv('BATCH_PIPELINE_ENRICHMENT_FRESH_SWEEP_MAX_AGE_DAYS', '7')
    assert sweep_age.max_age_seconds('provider-stt') == 20 * 86400
    assert sweep_age.max_age_seconds('enrichment-fresh') == 7 * 86400


def test_enrichment_cas_rechecks_row_age(state, sweep_query, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'on')
    outbox.mark('u', 'c', 'en', now=100)
    key = outbox.key('u', 'c')
    rows[key]['dispatch']['queue'] = 'enrichment-fresh'
    original = deepcopy(rows)
    # The query snapshot is not authoritative: repair must check the CAS row too.
    sweep_query.stream.side_effect = lambda: [SimpleNamespace(id=key, to_dict=lambda: {})]
    tasks.clear()
    assert outbox.sweep(now=2_000_000, wake=lambda row: tasks.append(row)) == {'repaired': 0, 'error': 0}
    assert rows == original and not tasks


def test_off_restores_existing_parking_policy(state, sweep_query, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'off')
    outbox.mark('u', 'c', 'en', now=100)
    key = outbox.key('u', 'c')
    rows[key]['dispatch']['queue'] = 'enrichment-fresh'
    tasks.clear()
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    sweep_query.stream.side_effect = lambda: [SimpleNamespace(id=key, to_dict=lambda: deepcopy(rows[key]))]
    assert outbox.sweep(now=2_000_000) == {'repaired': 0, 'error': 0}
    assert rows[key]['age_gate_parked'] and not tasks


def test_new_mark_on_ancient_open_fresh_row_is_rewoken(state, sweep_query, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'on')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    now = 2_000_000.0
    outbox.mark('u', 'c', 'en', now=100)
    key = outbox.key('u', 'c')
    rows[key]['dispatch']['queue'] = 'enrichment-fresh'
    first_pending = rows[key]['first_pending_at']
    outbox.mark('u', 'c', 'en', now=now - 3600)
    outbox.mark('u', 'c', 'en', now=now - 7200)  # Delayed older append cannot regress the age.
    assert rows[key]['first_pending_at'] == first_pending
    assert rows[key]['latest_pending_at'] == now - 3600
    tasks.clear()  # The coalesced mark's previous named task was lost.
    sweep_query.stream.side_effect = lambda: [SimpleNamespace(id=key, to_dict=lambda: deepcopy(rows[key]))]
    counter = SKIPPED.labels(queue='enrichment-fresh', reason='max_age')
    before = counter._value.get()
    assert outbox.sweep(now=now) == {'repaired': 1, 'error': 0}
    assert len(tasks) == 1 and counter._value.get() == before


def test_ancient_fresh_sweep_runs_privacy_retirement_before_age_skip(state, sweep_query, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'on')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    outbox.mark('u', 'c', 'en', now=100)
    key = outbox.key('u', 'c')
    rows[key]['dispatch']['queue'] = 'enrichment-fresh'
    tasks.clear()
    sweep_query.stream.side_effect = lambda: [SimpleNamespace(id=key, to_dict=lambda: deepcopy(rows[key]))]
    counter = SKIPPED.labels(queue='enrichment-fresh', reason='max_age')
    before = counter._value.get()

    from database.outbox_firestore import FirestoreEnrichmentOutbox
    from unittest.mock import Mock

    probe = Mock(return_value=True)
    adapter = FirestoreEnrichmentOutbox(privacy_blocked=probe)
    assert outbox.sweep(now=2_000_000, discard=adapter._blocked) == {
        'repaired': 0,
        'error': 0,
        'discarded': 1,
        'expired': 0,
    }
    assert not rows and not tasks and counter._value.get() == before
    probe.assert_called_once_with('u', {'conversation_id': 'c'})
