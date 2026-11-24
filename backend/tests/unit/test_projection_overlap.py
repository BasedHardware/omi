"""Synthetic fleet overlap, bounded telemetry and unchanged discovery semantics."""

from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from prometheus_client import CollectorRegistry, generate_latest

from database.batch_pipeline_store import FirestoreStore
from database.jobstore.dual_store import DualStore
from database.jobstore.index_store import IndexStore
from utils.batch_pipeline import projection_discovery as discovery
from utils.batch_pipeline import projection_overlap as overlap
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery


def observer():
    registry = CollectorRegistry()
    clock = Mock(return_value=1200.0)
    return overlap.OverlapObserver(registry=registry, clock=clock), registry, clock


def ranks(obs, namespace='batch_pipeline_prod', mode='legacy', slot=0):
    return obs.windows[namespace, mode, slot][1]


def test_identical_fleet_and_local_repeats_are_distinct_measures():
    fleet = [observer() for _ in range(4)]
    rows = [f'synthetic-{i}' for i in range(10000)]
    for obs, _, _ in fleet:
        obs.observe('batch_pipeline_prod', rows, 'legacy')
        obs.observe('batch_pipeline_prod', rows, 'legacy')
    union = [max(registers) for registers in zip(*(ranks(obs) for obs, _, _ in fleet))]
    assert sum(overlap.estimate(ranks(obs)) for obs, _, _ in fleet) / overlap.estimate(union) == pytest.approx(4)
    assert overlap.estimate(union) == pytest.approx(10000, rel=0.3)
    obs, registry, _ = fleet[0]
    assert (
        registry.get_sample_value(
            overlap.PREFIX + '_visits_total', {'data_namespace': 'batch_pipeline_prod', 'mode': 'legacy'}
        )
        == 20000
    )
    assert not any(isinstance(value, str) and 'synthetic' in value for value in obs.windows.values())
    assert b'synthetic' not in generate_latest(registry)


def test_disjoint_fleet_is_approximately_one_instance_per_row():
    fleet = [observer()[0] for _ in range(4)]
    for n, obs in enumerate(fleet):
        obs.observe('batch_pipeline_prod', [f'fleet-{n}-{i}' for i in range(10000)], 'legacy')
    union = [max(registers) for registers in zip(*(ranks(obs) for obs in fleet))]
    assert sum(overlap.estimate(ranks(obs)) for obs in fleet) / overlap.estimate(union) == pytest.approx(1, rel=0.3)


def test_partial_overlap_and_small_population():
    first, second = observer()[0], observer()[0]
    first.observe('batch_pipeline_prod', [f'small-{i}' for i in range(20)], 'legacy')
    second.observe('batch_pipeline_prod', [f'small-{i}' for i in range(10, 30)], 'legacy')
    union = [max(registers) for registers in zip(ranks(first), ranks(second))]
    assert overlap.estimate(union) == pytest.approx(30, rel=0.3)
    assert sum(overlap.estimate(ranks(obs)) for obs in [first, second]) / overlap.estimate(union) == pytest.approx(
        4 / 3, rel=0.3
    )
    assert overlap.estimate([0] * 64) == 0


def test_rotation_epochs_cannot_mix_old_ranks_and_empty_is_not_missing():
    obs, registry, clock = observer()
    obs.observe('batch_pipeline_prod', ['first'], 'legacy')
    clock.return_value = 1800
    obs.observe('batch_pipeline_prod', [], 'legacy')
    clock.return_value = 2400
    obs.observe('batch_pipeline_prod', [], 'legacy')
    values = [
        registry.get_sample_value(
            overlap.PREFIX + '_register',
            {'data_namespace': 'batch_pipeline_prod', 'mode': 'legacy', 'slot': '0', 'register': str(i)},
        )
        for i in range(64)
    ]
    assert overlap.decode(values, 4) == [0] * 64
    with pytest.raises(ValueError):
        overlap.decode([2 * 64 + 59] + values[1:], 4)
    with pytest.raises(ValueError):
        overlap.decode(values[:-1], 4)
    assert len(obs.windows) == 2


def test_multiprocess_max_is_union_within_epoch_and_rejects_partial_new_epoch():
    first, second = observer()[0], observer()[0]
    first.observe('batch_pipeline_prod', ['a', 'b'], 'legacy')
    second.observe('batch_pipeline_prod', ['b', 'c'], 'legacy')
    encoded = [max(2 * 64 + a, 2 * 64 + b) for a, b in zip(ranks(first), ranks(second))]
    assert overlap.decode(encoded, 2) == [max(a, b) for a, b in zip(ranks(first), ranks(second))]
    with pytest.raises(ValueError):
        overlap.decode([4 * 64] + encoded[1:], 4)
    assert overlap.decode([max(4 * 64, old) for old in encoded], 4) == [0] * 64


def test_labels_memory_and_clock_regression_are_bounded():
    obs, registry, clock = observer()
    for epoch in range(100):
        clock.return_value = epoch * 600
        for namespace in overlap.NAMESPACES:
            for mode in overlap.MODES:
                obs.observe(namespace, ['only-ranks-retained'], mode)
        obs.observe('unknown-customer-namespace', ['no'], 'legacy')
        obs.observe('batch_pipeline_prod', ['no'], 'unbounded-mode')
    assert len(obs.windows) == 8
    registers = [
        sample for metric in registry.collect() for sample in metric.samples if sample.name.endswith('_register')
    ]
    assert len(registers) == 512
    before = {key: (value[0], value[1][:]) for key, value in obs.windows.items()}
    clock.return_value = 1
    obs.observe('batch_pipeline_prod', ['new'], 'legacy')
    assert obs.windows == before
    assert registry.get_sample_value(overlap.PREFIX + '_skipped_total', {'reason': 'clock_regressed'}) == 1
    clock.return_value = float('nan')
    obs.observe('batch_pipeline_prod', [], 'due')
    assert registry.get_sample_value(overlap.PREFIX + '_skipped_total', {'reason': 'invalid_clock'}) == 1


@pytest.mark.parametrize('pagination', [False, True])
def test_discovery_observer_failure_preserves_query_result_cursor_and_scope(monkeypatch, pagination, caplog):
    monkeypatch.setattr(discovery, 'projection_pagination_enabled', lambda: pagination)
    monkeypatch.setattr(discovery, 'projection_striping_enabled', lambda: False)
    store = SimpleNamespace(projection_page=Mock(return_value=(['already-read'], None)))
    callback = Mock(side_effect=RuntimeError('not a discovery failure'))
    page = ProjectionDiscovery(store, on_page=callback)
    caplog.set_level('DEBUG', logger=discovery.__name__)
    assert page.next(followup_due_before=123.0) == ['already-read']
    store.projection_page.assert_called_once_with(limit=100, after=None, followup_due_before=123.0)
    callback.assert_called_once_with(['already-read'], 'due')
    assert page.after is None
    assert 'Projection discovery observer failed' in caplog.text
    assert 'not a discovery failure' not in caplog.text
    assert 'already-read' not in caplog.text


def test_legacy_nonpaginated_observes_without_extra_queries(monkeypatch):
    monkeypatch.setattr(discovery, 'projection_pagination_enabled', lambda: False)
    store = SimpleNamespace(projection_pending=Mock(return_value=['a', 'a']), projection_page=Mock())
    callback = Mock()
    assert ProjectionDiscovery(store, on_page=callback).next() == ['a', 'a']
    store.projection_pending.assert_called_once_with(limit=100)
    store.projection_page.assert_not_called()
    callback.assert_called_once_with(['a', 'a'], 'legacy')


def test_observer_wrapper_never_raises_or_logs_identifiers(monkeypatch):
    broken = SimpleNamespace(observe=Mock(side_effect=RuntimeError('sensitive')), skipped=Mock())
    monkeypatch.setattr(overlap, '_default_observer', broken)
    overlap.observe_page('batch_pipeline_prod', ['synthetic-id'], 'legacy')
    broken.skipped.labels.assert_called_once_with('observer_error')


def test_only_known_firestore_read_adapters_are_observed(monkeypatch):
    primary = object.__new__(FirestoreStore)
    primary.namespace = 'batch_pipeline_prod'
    mirror = object.__new__(DualStore)
    mirror.primary = primary
    index = object.__new__(IndexStore)
    index.primary = primary
    callback = Mock()
    monkeypatch.setattr(overlap, 'observe_page', callback)
    for store in [primary, mirror]:
        overlap.observer_for_store(store)(['synthetic'], 'legacy')
    assert callback.call_count == 2
    for store in [index, SimpleNamespace(namespace='batch_pipeline_prod')]:
        assert overlap.observer_for_store(store) is None


def test_new_families_survive_existing_cloud_run_keep_filter():
    backend = Path(__file__).resolve().parents[2]
    rules = yaml.safe_load((backend / 'deploy/cloud_run_gmp_sync.yaml').read_text())['spec']['endpoints'][0][
        'metricRelabeling'
    ]
    _, registry, _ = observer()
    obs = overlap.OverlapObserver(registry=CollectorRegistry())
    obs.observe('batch_pipeline_prod', ['synthetic'], 'legacy')
    for metric in obs.registers.collect():
        for sample in metric.samples:
            labels = {'__name__': sample.name, **sample.labels}
            for rule in rules:
                value = ';'.join(labels.get(label, '') for label in rule['sourceLabels'])
                matched = bool(re.fullmatch(rule['regex'], value))
                if rule['action'] == 'keep':
                    assert matched
                elif rule['action'] == 'drop':
                    assert not matched


@pytest.mark.parametrize('missing', [None, True, '0', float('inf'), float('nan')])
def test_decode_rejects_missing_or_nonnumeric_samples(missing):
    with pytest.raises(ValueError):
        overlap.decode([missing] + [0] * 63, 0)


@pytest.mark.parametrize('disabled', ['0', 'off', 'false', 'no'])
def test_disabled_observer_is_unwired_and_creates_no_metrics(monkeypatch, disabled):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_OVERLAP_DIAGNOSTICS', disabled)
    primary = object.__new__(FirestoreStore)
    primary.namespace = 'batch_pipeline_prod'
    constructor = Mock(side_effect=AssertionError('diagnostic metrics must remain unconstructed'))
    monkeypatch.setattr(overlap, 'OverlapObserver', constructor)
    assert overlap.observer_for_store(primary) is None
    constructor.assert_not_called()
