"""Fixtures for the Firestore caller-label overflow alert.

The alert is the guard for silent attribution folding: once the bounded caller
set is full, a new well-formed ``module:function`` label is folded to ``other``
and ``omi_firestore_caller_label_overflow_total`` increments. These fixtures
drive the real probe to produce that fold, then evaluate the committed Grafana
rule through the offline backtest harness. They also prove the enable selector
and the paused switch both disable the rule and that restoring them re-enables
it.

No production data is claimed here. The counter is new in this program, so the
rule's ``evaluated_bad``/``evaluated_good`` annotations record these fixture
values and say so; a live backtest belongs to the approved roll.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from database import firestore_document_probe as probe

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / 'backend/charts/monitoring'
SCRIPT = REPO / 'backend/scripts/alert_backtest.py'
UID = 'omi-firestore-caller-overflow'

_spec = importlib.util.spec_from_file_location('alert_backtest', SCRIPT)
backtest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backtest)


def _split():
    return {rule['uid']: rule for rule in json.loads((MONITORING / 'alerts/firestore.json').read_text())}


def _combined():
    return {rule['uid']: rule for rule in json.loads((MONITORING / 'alert-rules.json').read_text())}


def _rule():
    return _split()[UID]


def _nodes(rule):
    return {node['refId']: node['model'] for node in rule['data']}


def _other_reads():
    total = 0.0
    for family in probe.FIRESTORE_BILLED_READS_BY_CALLER.collect():
        for sample in family.samples:
            if sample.name.endswith('_total') and sample.labels.get('caller') == 'other':
                total += sample.value
    return total


def _overflow():
    return float(probe.FIRESTORE_CALLER_LABEL_OVERFLOW._value.get() or 0)


def _evaluate(rule, other_rate, overflow_rate, enable=1):
    return backtest.evaluate(
        rule,
        {
            'A': {(): [other_rate]},
            'B': {(): [overflow_rate]},
            'D': {(): [enable]},
        },
    )


def test_rule_is_identical_in_both_exports_and_enabled_by_default():
    split, combined = _split(), _combined()
    assert split[UID] == combined[UID]
    rule = split[UID]
    assert rule['isPaused'] is False
    assert rule['labels']['kill_switch'] == UID
    assert rule['labels']['tier'] == 'agent'
    assert rule['labels']['audience'] == 'agent'
    assert rule['noDataState'] == 'OK'
    assert rule['for'] == '5m'


def test_expression_is_the_done_check_query_plus_the_overflow_counter():
    rule = _rule()
    nodes = _nodes(rule)
    assert nodes['A']['expr'] == (
        'sum(rate(omi_firestore_billed_reads_by_caller_total{caller="other"}[5m])) or vector(0)'
    )
    assert nodes['B']['expr'] == 'sum(rate(omi_firestore_caller_label_overflow_total[5m])) or vector(0)'
    assert nodes['C']['expression'] == '$A > 0 || $B > 0'
    assert nodes['D']['expr'] == 'vector(1)'
    assert nodes['E']['expression'] == '$C * $D'
    assert nodes['F']['type'] == 'threshold'
    assert nodes['F']['expression'] == 'E'
    assert nodes['F']['conditions'][0]['evaluator'] == {'params': [0], 'type': 'gt'}


def test_both_read_arms_use_the_managed_datasource():
    # The in-cluster Cloud Run bridge keeps only documents_per_operation and
    # read_operations_total, so a local-prometheus rule is blind to Cloud Run.
    rule = _rule()
    for node in rule['data']:
        if node['refId'] in ('A', 'B'):
            assert node['datasourceUid'] == 'gmp-cloud-run'
            assert node['model']['datasource'] == {'type': 'prometheus', 'uid': 'gmp-cloud-run'}


def test_selector_node_carries_a_grafana_valid_relative_time_range():
    """Grafana rejects a datasource-backed query with a 0s..0s window (SCA-2055).

    The selector stays ``vector(1)`` on the local Prometheus datasource and keeps
    the same 15-minute window as the two read arms, so enabling and disabling
    it means only swapping the expression to ``vector(0)``.
    """
    rule = _rule()
    nodes = {node['refId']: node for node in rule['data']}
    selector = nodes['D']
    assert selector['datasourceUid'] == 'prometheus'
    assert selector['model']['expr'] == 'vector(1)'
    assert selector['relativeTimeRange'] == {'from': 900, 'to': 0}
    for ref_id in ('A', 'B', 'D'):
        assert nodes[ref_id]['relativeTimeRange'] == {'from': 900, 'to': 0}, ref_id
    for ref_id in ('C', 'E', 'F'):
        assert nodes[ref_id]['datasourceUid'] == '__expr__'
        assert nodes[ref_id]['relativeTimeRange'] == {'from': 0, 'to': 0}, ref_id


def test_custom_registry_processes_export_the_overflow_counter():
    # The batch pipeline worker and record-seal worker serve COLLECTORS on a
    # private registry, not the default REGISTRY.
    from prometheus_client import CollectorRegistry
    from prometheus_client.parser import text_string_to_metric_families
    from prometheus_client import generate_latest
    from utils.observability.firestore_probe_export import register_probe_collectors

    registry = CollectorRegistry()
    register_probe_collectors(registry)
    names = {family.name for family in text_string_to_metric_families(generate_latest(registry).decode())}
    assert 'omi_firestore_caller_label_overflow' in names
    assert 'omi_firestore_billed_reads_by_caller' in names


def test_overflow_fires_and_clean_labels_resolve(monkeypatch):
    rule = _rule()
    saved = set(probe._known_callers)
    monkeypatch.setattr(probe, 'MAX_CALLERS', 1)
    probe._known_callers.clear()
    try:
        overflow_before, other_before = _overflow(), _other_reads()

        # A full set: the first caller is named, the second folds to other.
        assert probe.bound_caller('database.memories:get_memories') == 'database.memories:get_memories'
        assert probe.bound_caller('database.chat:get_messages') == 'other'
        probe._record(('users', 'u1', 'memory_items'), True, caller='other')

        overflow_delta = _overflow() - overflow_before
        other_delta = _other_reads() - other_before
        assert overflow_delta == 1
        assert other_delta == 1
        assert _evaluate(rule, other_delta, overflow_delta) == {(): 1}

        # Clean labels: the set is not full, so the caller is named and neither
        # the overflow counter nor the other bucket moves in the window.
        probe._known_callers.clear()
        monkeypatch.setattr(probe, 'MAX_CALLERS', 1536)
        overflow_before, other_before = _overflow(), _other_reads()
        assert probe.bound_caller('database.memories:get_memories') == 'database.memories:get_memories'
        assert probe.bound_caller('database.chat:get_messages') == 'database.chat:get_messages'
        assert _overflow() - overflow_before == 0
        assert _other_reads() - other_before == 0
        assert _evaluate(rule, 0, 0) == {(): 0}
    finally:
        probe._known_callers.clear()
        probe._known_callers.update(saved)


def test_enable_selector_disables_and_re_enables_the_rule():
    rule = _rule()
    # Enabled by default: overflow fires.
    assert _evaluate(rule, 1, 1, enable=1) == {(): 1}
    # Disabled: the same overflow resolves.
    assert _evaluate(rule, 1, 1, enable=0) == {(): 0}
    # Re-enabled: it fires again.
    assert _evaluate(rule, 1, 1, enable=1) == {(): 1}


def test_pending_and_resolution_episode():
    # The 5m pending is real: a sustained fold fires after five minutes and
    # resolves when the fold stops.
    rule = _rule()
    samples = [(t, {(): 1.0 if t <= 420 else 0.0}) for t in range(0, 600, 60)]
    result = backtest.episodes(rule, samples, 0, 540, 60)
    assert result['episodes'] == 1
    assert result['longest_seconds'] == 180


def _fires(rule):
    """Grafana evaluates an unpaused rule; a paused rule never produces an instance."""
    if rule['isPaused']:
        return {}
    return backtest.evaluate(rule, {'A': {(): [1]}, 'B': {(): [1]}, 'D': {(): [1]}})


def test_paused_switch_disables_and_re_enables_the_rule():
    rule = _rule()
    assert rule['isPaused'] is False
    assert _fires(rule) == {(): 1}
    paused = {**rule, 'isPaused': True}
    assert paused['isPaused'] is True
    assert _fires(paused) == {}
    assert _fires({**paused, 'isPaused': False}) == {(): 1}


def test_annotations_name_the_exact_switch_and_re_enable_path():
    annotations = _rule()['annotations']
    assert 'vector(1)' in annotations['kill_switch']
    assert 'vector(0)' in annotations['kill_switch']
    assert 'isPaused' in annotations['kill_switch']
    assert 'provision_monitoring_alerts.py' in annotations['kill_switch']
    assert 'Fixture' in annotations['evaluated_bad']
    assert 'Fixture' in annotations['evaluated_good']


def test_verification_annotation_refuses_to_read_absence_as_zero():
    """An empty series is the healthy state, not a measured clean reading."""
    verification = _rule()['annotations']['verification']
    assert 'no series' in verification
    assert 'never as a measured clean zero' in verification


@pytest.mark.parametrize('export', ['split', 'combined'])
def test_rule_passes_the_offline_admission_lint(export):
    rules = _split() if export == 'split' else _combined()
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    assert not backtest.lint({UID: rules[UID]}, inventory)['failures']
