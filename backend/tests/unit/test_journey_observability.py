import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services import conversation_finalization
from utils import metrics
from utils.observability import journeys

REPO = Path(__file__).resolve().parents[3]


def _install_journey_metrics(monkeypatch):
    accepted = MagicMock()
    terminal = MagicMock()
    latency = MagicMock()
    reconciliations = MagicMock()
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_ACCEPTED_TOTAL', accepted)
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_TERMINAL_TOTAL', terminal)
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_LATENCY_SECONDS', latency)
    monkeypatch.setattr(journeys, 'OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL', reconciliations)
    accepted.labels.return_value = MagicMock()
    terminal.labels.return_value = MagicMock()
    latency.labels.return_value = MagicMock()
    reconciliations.labels.return_value = MagicMock()
    return accepted, terminal, latency, reconciliations


def test_journey_contract_uses_only_closed_privacy_safe_labels(monkeypatch):
    accepted, terminal, latency, reconciliations = _install_journey_metrics(monkeypatch)

    journeys.record_journey_accepted('chat_response')
    journeys.record_journey_terminal('pusher_session', 'cancelled', 1.5)
    journeys.record_capture_finalization_reconciliation('requeued')

    accepted.labels.assert_called_once_with(journey='chat_response')
    terminal.labels.assert_called_once_with(journey='pusher_session', outcome='cancelled')
    latency.labels.assert_called_once_with(journey='pusher_session', outcome='cancelled')
    reconciliations.labels.assert_called_once_with(outcome='requeued')
    with pytest.raises(ValueError, match='unknown journey'):
        journeys.record_journey_accepted('user-123')
    with pytest.raises(ValueError, match='unknown journey outcome'):
        journeys.record_journey_terminal('chat_response', 'raw exception text', 1.0)


def test_capture_terminal_uses_persisted_acceptance_time(monkeypatch):
    _accepted, terminal, latency, _reconciliations = _install_journey_metrics(monkeypatch)
    accepted_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    journeys.record_capture_finalization_terminal('success', accepted_at)

    terminal.labels.assert_called_once_with(journey='capture_finalization', outcome='success')
    latency.labels.assert_called_once_with(journey='capture_finalization', outcome='success')
    observed = latency.labels.return_value.observe.call_args.args[0]
    assert 4.0 <= observed <= 6.0


def test_terminal_finalization_failure_records_once_after_dead_letter(monkeypatch):
    dead_letter = MagicMock(return_value=True)
    accepted_at = datetime.now(timezone.utc) - timedelta(seconds=12)
    terminal = MagicMock()
    monkeypatch.setattr(conversation_finalization.jobs_db, 'mark_finalization_dead_letter', dead_letter)
    monkeypatch.setattr(
        conversation_finalization.jobs_db,
        'get_finalization_job',
        MagicMock(return_value={'created_at': accepted_at}),
    )
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_DEAD_LETTER_TOTAL', MagicMock())
    monkeypatch.setattr(conversation_finalization, 'record_capture_finalization_terminal', terminal)

    assert conversation_finalization.final_attempt_failed('job-1', 2, 3, 4) is True

    dead_letter.assert_called_once_with('job-1', 2, 3, 4, firestore_client=None)
    terminal.assert_called_once_with('failure', accepted_at)


def test_idle_metrics_and_monitoring_contract_distinguish_traffic_from_a_missing_scrape_source():
    exported = metrics.generate_latest().decode()
    assert 'omi_journey_accepted_total{journey="chat_response"}' in exported
    assert 'omi_journey_terminal_total{journey="pusher_session",outcome="success"}' in exported
    assert 'omi_capture_finalization_reconciliations_total{outcome="requeued"}' in exported

    monitoring = REPO / 'backend/charts/monitoring'
    split_alerts = json.loads((monitoring / 'alerts/resilience.json').read_text(encoding='utf-8'))
    combined_alerts = json.loads((monitoring / 'alert-rules.json').read_text(encoding='utf-8'))
    expected_ids = {
        'omi-journey-chat-fail',
        'omi-journey-pusher-fail',
        'omi-journey-capture-fail',
        'omi-journey-scrape-missing',
    }
    assert expected_ids <= {rule['uid'] for rule in split_alerts}
    assert expected_ids <= {rule['uid'] for rule in combined_alerts}

    product_rules = [rule for rule in split_alerts if rule['uid'] in expected_ids - {'omi-journey-scrape-missing'}]
    assert {rule['noDataState'] for rule in product_rules} == {'NoData'}
    for rule in product_rules:
        assert 'outcome=~"success|failure"' in rule['data'][0]['model']['expr']
        assert '$A >= 20 && $B > 0.10' in rule['data'][2]['model']['expression']
    scrape_rule = next(rule for rule in split_alerts if rule['uid'] == 'omi-journey-scrape-missing')
    assert scrape_rule['noDataState'] == 'Alerting'
    assert 'count by (job)' in scrape_rule['data'][0]['model']['expr']
    assert 'backend-listen-metrics|pusher-metrics' in scrape_rule['data'][0]['model']['expr']

    dashboard = json.loads(
        (monitoring / 'dashboards/omi-services/resilience-fallbacks.json').read_text(encoding='utf-8')
    )
    panel_titles = {panel['title'] for panel in dashboard['panels']}
    assert 'Journey terminal success rate (success / success + failure)' in panel_titles
    assert 'Journey acceptance-to-terminal latency (p95)' in panel_titles
    assert 'Capture finalization reconciliation and nonterminal work' in panel_titles
    success_panel = next(
        panel for panel in dashboard['panels'] if panel['title'].startswith('Journey terminal success')
    )
    assert 'and on (journey)' in success_panel['targets'][0]['expr']
