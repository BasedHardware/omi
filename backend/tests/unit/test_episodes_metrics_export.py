"""The shared listen/API exporter registers the bounded episode moment metrics."""

import importlib
import json
from pathlib import Path

from fastapi.security import HTTPAuthorizationCredentials
from prometheus_client.parser import text_string_to_metric_families

from routers import metrics as metrics_router
from utils.episodes import metrics as episode_metrics
from utils.metrics import metrics_response


def test_shared_metrics_export_includes_episode_moment_families():
    exported = bytes(metrics_response().body).decode()

    assert '# HELP omi_episode_moment_updates_total ' in exported
    assert '# HELP omi_episode_moment_tokens_total ' in exported
    assert '# HELP omi_episode_moment_cost_usd_total ' in exported
    assert '# HELP omi_episode_moment_update_latency_seconds ' in exported
    assert 'uid=' not in exported


def test_compose_mode_metrics_are_exported_without_identity_labels():
    from utils.episodes.metrics import record_compose_reply

    record_compose_reply('full', 10, 1)
    exported = metrics_response().body.decode()
    assert '# HELP omi_episode_compose_input_tokens_total ' in exported
    assert '# HELP omi_episode_compose_tool_calls ' in exported
    assert 'uid=' not in exported


def test_pending_batch_dwell_counter_is_exported_without_identity_labels():
    from utils.episodes.metrics import record_batch_pending_overdue

    record_batch_pending_overdue()
    exported = bytes(metrics_response().body).decode()
    assert '# HELP omi_episode_batch_pending_overdue_reads_total ' in exported
    line = next(
        line for line in exported.splitlines() if line.startswith('omi_episode_batch_pending_overdue_reads_total ')
    )
    assert '{' not in line


def _sample_value(exported, metric, label, value):
    for family in text_string_to_metric_families(exported):
        for sample in family.samples:
            if sample.name == metric and sample.labels.get(label) == value:
                return sample.value
    return 0.0


def test_f_gate_counter_is_primed_and_exported_on_the_pusher_metrics_route(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'test-metrics-secret')
    exported = metrics_router.metrics(HTTPAuthorizationCredentials(scheme='Bearer', credentials='test-metrics-secret'))
    families = {family.name: family for family in text_string_to_metric_families(bytes(exported.body).decode())}
    samples = families['omi_episode_f_gate'].samples
    assert {sample.labels['reason'] for sample in samples} == episode_metrics.F_GATE_REASONS
    assert all(sample.name == 'omi_episode_f_gate_total' and set(sample.labels) == {'reason'} for sample in samples)
    # Counters are process-global and shared with other tests in the same worker: check deltas, not zeros.
    assert all(sample.value >= 0 for sample in samples)
    counter = episode_metrics.EPISODE_F_GATE_TOTAL
    assert importlib.reload(episode_metrics).EPISODE_F_GATE_TOTAL is counter
    before = _sample_value(bytes(metrics_response().body).decode(), 'omi_episode_f_gate_total', 'reason', 'other')
    episode_metrics.record_f_gate('unmapped-sensitive-value')
    exported = bytes(metrics_response().body).decode()
    assert _sample_value(exported, 'omi_episode_f_gate_total', 'reason', 'other') == before + 1
    assert 'unmapped-sensitive-value' not in exported


def test_f_metrics_are_declared_in_inventory():
    inventory = json.loads(
        (Path(__file__).resolve().parents[2] / 'charts/monitoring/metric-inventory.prod.json').read_text()
    )
    for name in ('omi_episode_f_gate_total', 'omi_episode_f_fallback_total'):
        assert name in inventory['declared_metrics']


def test_f_fallback_counter_is_primed_bounded_and_reload_safe():
    exported = bytes(metrics_response().body).decode()
    families = {family.name: family for family in text_string_to_metric_families(exported)}
    samples = families['omi_episode_f_fallback'].samples
    assert {sample.labels['site'] for sample in samples} == episode_metrics.F_FALLBACK_SITES
    assert all(sample.name == 'omi_episode_f_fallback_total' and set(sample.labels) == {'site'} for sample in samples)
    assert all(sample.value >= 0 for sample in samples)
    counter = episode_metrics.EPISODE_F_FALLBACK_TOTAL
    assert importlib.reload(episode_metrics).EPISODE_F_FALLBACK_TOTAL is counter
    before = _sample_value(exported, 'omi_episode_f_fallback_total', 'site', 'other')
    episode_metrics.record_f_fallback('unmapped-sensitive-site')
    exported = bytes(metrics_response().body).decode()
    assert _sample_value(exported, 'omi_episode_f_fallback_total', 'site', 'other') == before + 1
    assert 'unmapped-sensitive-site' not in exported
