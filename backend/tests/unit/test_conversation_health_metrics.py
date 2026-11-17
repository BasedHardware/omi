"""Conversation-status instrumentation: clocks, committed CAS, and idle exposition."""

from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
import runpy
import json
import re

import yaml
from unittest.mock import Mock

import prometheus_client
import pytest
from prometheus_client import CollectorRegistry

from models.conversation_enums import ConversationStatus
from services import conversation_selfheal as sweep
from utils import metrics
from utils.conversations import lifecycle

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'seconds, expected',
    [
        (0, '1h'),
        (3600, '1h'),
        (3600.001, '6h'),
        (21600, '6h'),
        (21600.001, '24h'),
        (86400, '24h'),
        (86400.001, '7d'),
        (604800, '7d'),
        (604800.001, 'older'),
    ],
)
def test_terminal_age_bucket_inclusive_boundaries(seconds, expected):
    assert metrics.conversation_terminal_age_bucket(NOW - timedelta(seconds=seconds), NOW) == expected


def test_terminal_age_handles_naive_future_and_missing_clocks():
    assert metrics.conversation_terminal_age_bucket(NOW.replace(tzinfo=None), NOW) == '1h'
    assert metrics.conversation_terminal_age_bucket(NOW + timedelta(seconds=1), NOW) == '1h'
    assert metrics.conversation_terminal_age_bucket(None, NOW) is None
    assert metrics.conversation_terminal_age_bucket('invalid', NOW) is None


@pytest.mark.parametrize('claimed', [False, True])
@pytest.mark.parametrize(
    'target', [ConversationStatus.completed, ConversationStatus.failed, ConversationStatus.merging]
)
def test_transition_observes_only_winning_cas_without_an_extra_read(monkeypatch, target, claimed):
    row = {'status': 'processing' if target != ConversationStatus.merging else 'completed', 'finished_at': NOW}
    reader = Mock(return_value=row)
    claim = Mock(return_value=claimed)
    observer = Mock()
    monkeypatch.setattr(lifecycle.conversations_db, 'get_conversation', reader)
    monkeypatch.setattr(lifecycle.conversations_db, 'claim_conversation_status', claim)
    monkeypatch.setattr(metrics, 'CONVERSATION_TERMINAL_TRANSITION_TOTAL', observer)
    expected = ConversationStatus(row['status'])
    assert lifecycle.transition(None, None, target, expected=expected) is claimed
    reader.assert_called_once_with(None, None)
    claim.assert_called_once_with(None, None, expected, target, extra_updates=None)
    if claimed and target != ConversationStatus.merging:
        observer.labels.assert_called_once()
        assert observer.labels.call_args.kwargs['to_status'] == target.value
        observer.labels.return_value.inc.assert_called_once_with()
    else:
        observer.labels.assert_not_called()


def test_terminal_metric_failure_does_not_change_committed_transition(monkeypatch):
    monkeypatch.setattr(
        lifecycle.conversations_db, 'get_conversation', lambda *_: {'status': 'processing', 'finished_at': NOW}
    )
    monkeypatch.setattr(lifecycle.conversations_db, 'claim_conversation_status', lambda *_, **__: True)
    monkeypatch.setattr(metrics, 'CONVERSATION_TERMINAL_TRANSITION_TOTAL', Mock(labels=Mock(side_effect=ValueError)))
    assert lifecycle.transition(None, None, ConversationStatus.completed, expected=ConversationStatus.processing)


@pytest.mark.parametrize(
    'mode, failure, outcome', [('detect', False, 'ok'), ('detect', True, 'error'), ('off', False, 'ok')]
)
def test_tick_always_updates_deadman_and_records_bounded_outcome(monkeypatch, mode, failure, outcome):
    heartbeat, outcomes = Mock(), Mock()
    monkeypatch.setattr(metrics, 'CONVERSATION_SELFHEAL_TICK_TIMESTAMP_SECONDS', heartbeat)
    monkeypatch.setattr(metrics, 'CONVERSATION_SELFHEAL_TICK_OUTCOME_TOTAL', outcomes)

    def scan(**_):
        if failure:
            raise RuntimeError('scan unavailable')
        return {'scanned': 0, 'rows': [], 'exhausted': True}

    result = sweep.run_selfheal_tick(
        now=NOW,
        mode=mode,
        dry_run=True,
        cursor_getter=lambda **_: {},
        scan_fn=scan,
        wedge_runner=lambda **_: {},
        use_configured_uid_allowlist=False,
    )
    heartbeat.set.assert_called_once_with(NOW.timestamp())
    outcomes.labels.assert_called_once_with(outcome=outcome)
    outcomes.labels.return_value.inc.assert_called_once_with()
    assert result['errors'] == int(failure)


@pytest.mark.parametrize('scan_returned', [False, True])
def test_selfheal_exports_existing_window_values_and_retains_them_on_failed_scan(monkeypatch, scan_returned):
    holding, oldest, over_12h, outcomes = Mock(), Mock(), Mock(), Mock()
    for name, metric in (
        ('CONVERSATION_STALE_CONTENT_HOLDING', holding),
        ('CONVERSATION_STALE_CONTENT_OLDEST_AGE_SECONDS', oldest),
        ('CONVERSATION_STALE_CONTENT_OVER_12H', over_12h),
        ('CONVERSATION_SELFHEAL_TICK_OUTCOME_TOTAL', outcomes),
    ):
        monkeypatch.setattr(metrics, name, metric)
    metrics.observe_conversation_selfheal_tick(
        {'content_holding': 321, 'oldest_age_seconds': 50000, 'content_holding_over_12h': 12, 'errors': 1},
        NOW,
        scan_returned=scan_returned,
    )
    outcomes.labels.assert_called_once_with(outcome='partial' if scan_returned else 'error')
    for metric, value in ((holding, 321), (oldest, 50000), (over_12h, 12)):
        if scan_returned:
            metric.set.assert_called_once_with(value)
        else:
            metric.set.assert_not_called()


def test_v3_counter_registration_zero_initializes_all_five_outcomes(monkeypatch):
    registry = CollectorRegistry()
    for name in ('Counter', 'Histogram', 'Gauge'):
        monkeypatch.setattr(prometheus_client, name, partial(getattr(prometheus_client, name), registry=registry))
    runpy.run_path(str(Path(__file__).resolve().parents[2] / 'utils/conversations/v3/metrics.py'))
    samples = [
        sample
        for family in registry.collect()
        for sample in family.samples
        if sample.name == 'omi_conversations_v3_reconciles_total'
    ]
    assert {sample.labels['outcome'] for sample in samples} == {
        'busy',
        'committed',
        'error',
        'outline_fallback',
        'dispatch_error',
    }
    assert all(sample.value == 0 for sample in samples)


def test_health_families_survive_both_production_exporters_and_the_sync_sidecar():
    backend = Path(__file__).resolve().parents[2]
    names = (
        'omi_conversation_stale_content_holding',
        'omi_conversation_stale_content_oldest_age_seconds',
        'omi_conversation_stale_content_over_12h',
        'omi_conversation_selfheal_tick_timestamp_seconds',
        'omi_conversation_selfheal_tick_outcome_total',
        'omi_conversation_terminal_transition_total',
        'omi_conversations_v3_reconciles_total',
    )
    config = yaml.safe_load((backend / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    keep = next(rule for rule in config['spec']['endpoints'][0]['metricRelabeling'] if rule['action'] == 'keep')
    for profile in ('prod_omi_cloud_run_metrics_exporter.yaml', 'prod_sync_omi_cloud_run_metrics_exporter.yaml'):
        path = backend / 'charts/monitoring/prometheus-stackdriver-exporter' / profile
        prefixes = yaml.safe_load(path.read_text())['stackdriver']['metrics']['prefixes']
        for name in names:
            assert re.fullmatch(keep['regex'], name), name
            assert any(f'prometheus.googleapis.com/{name}/'.startswith(prefix) for prefix in prefixes), (profile, name)


def test_status_pages_have_the_requested_thresholds_and_match_both_exports():
    monitoring = Path(__file__).resolve().parents[2] / 'charts/monitoring'
    split = {rule['uid']: rule for rule in json.loads((monitoring / 'alerts/resilience.json').read_text())}
    combined = {rule['uid']: rule for rule in json.loads((monitoring / 'alert-rules.json').read_text())}
    for uid, expression, threshold, duration in (
        ('omi-conversation-stale-content', 'max(omi_conversation_stale_content_holding)', 200, '30m'),
        (
            'omi-conversation-selfheal-deadman',
            '(time() - max(omi_conversation_selfheal_tick_timestamp_seconds)) or vector(1e9)',
            3600,
            '10m',
        ),
    ):
        rule = split[uid]
        assert combined[uid] == rule
        assert rule['data'][0]['model']['expr'] == expression
        assert rule['data'][2]['model']['conditions'][0]['evaluator'] == {'params': [threshold], 'type': 'gt'}
        assert rule['for'] == duration
        assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
        assert rule['isPaused'] is False
        assert not rule['notification_settings'].get('mute_time_intervals')
