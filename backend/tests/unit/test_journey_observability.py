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

    journeys.record_journey_accepted('pusher_session')
    journeys.record_journey_terminal('pusher_session', 'cancelled', 1.5)
    journeys.record_capture_finalization_reconciliation('requeued')

    accepted.labels.assert_called_once_with(journey='pusher_session')
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


def test_listener_projects_the_closed_durable_finalization_states(monkeypatch):
    durable = MagicMock()
    durable.labels.return_value = MagicMock()
    backlog = MagicMock()
    backlog.labels.return_value = MagicMock()
    monkeypatch.setattr(
        conversation_finalization.jobs_db,
        'get_finalization_job_summary',
        MagicMock(
            return_value={
                'accepted': 9,
                'success': 3,
                'failure': 1,
                'stale': 2,
                'nonterminal': 1,
                'blocked_byok': 1,
                'terminal_unknown': 1,
                'queued': 1,
                'leased': 0,
                'dead_letter': 1,
                'oldest_nonterminal_age_seconds': 12.5,
            }
        ),
    )
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_DURABLE_JOBS', durable)
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_JOB_STATUS', backlog)
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS', MagicMock())

    conversation_finalization._publish_job_metrics()

    assert {call.kwargs['state'] for call in durable.labels.call_args_list} == {
        'accepted',
        'success',
        'failure',
        'stale',
        'nonterminal',
        'blocked_byok',
        'terminal_unknown',
    }


def test_idle_metrics_and_monitoring_contract_distinguish_traffic_from_a_missing_scrape_source():
    exported = metrics.generate_latest().decode()
    assert 'omi_journey_accepted_total{journey="chat_response"}' in exported
    assert 'omi_live_stt_accepted_total' in exported
    assert 'omi_queue_oldest_ready_age_seconds' in exported
    assert 'omi_queue_oldest_ready_age_seconds{' not in exported
    assert 'omi_live_stt_terminal_total' in exported
    assert 'omi_journey_terminal_total{journey="pusher_session",outcome="success"}' in exported
    assert 'omi_capture_finalization_reconciliations_total{outcome="requeued"}' in exported
    assert 'listen_finalization_stale_processing_reconciliations_total{outcome="completed"}' in exported
    assert 'listen_finalization_stale_processing_reconciliations_total{outcome="error"}' in exported
    assert 'listen_finalization_stale_processing_reconciliations_total{outcome="migrated"}' in exported

    monitoring = REPO / 'backend/charts/monitoring'
    split_alerts = json.loads((monitoring / 'alerts/resilience.json').read_text(encoding='utf-8'))
    combined_alerts = json.loads((monitoring / 'alert-rules.json').read_text(encoding='utf-8'))
    expected_ids = {
        'omi-journey-chat-fail',
        'omi-journey-pusher-fail',
        'omi-journey-live-transcription-fail',
        'omi-journey-capture-fail',
        'omi-capture-finalization-dead-emission',
        'omi-journey-scrape-missing',
    }
    assert expected_ids <= {rule['uid'] for rule in split_alerts}
    assert expected_ids <= {rule['uid'] for rule in combined_alerts}

    product_rule_ids = expected_ids - {'omi-journey-scrape-missing', 'omi-capture-finalization-dead-emission'}
    product_rules = [rule for rule in split_alerts if rule['uid'] in product_rule_ids]
    for rule in product_rules:
        if rule['uid'] == 'omi-journey-capture-fail':
            assert 'listen_finalization_durable_jobs' in rule['data'][0]['model']['expr']
        elif rule['uid'] == 'omi-journey-live-transcription-fail':
            assert rule['data'][0]['model']['expr'] == 'sum(increase(omi_live_stt_accepted_total[30m]))'
            assert 'omi_live_stt_terminal_total{outcome="failure"}' in rule['data'][1]['model']['expr']
        else:
            assert 'outcome=~"success|failure"' in rule['data'][0]['model']['expr']
        assert '$A >= 20 && $B > 0.10' in rule['data'][2]['model']['expression']
    live_transcription_rule = next(
        rule for rule in product_rules if rule['uid'] == 'omi-journey-live-transcription-fail'
    )
    assert live_transcription_rule['noDataState'] == 'OK'
    assert live_transcription_rule['annotations']['__panelId__'] == '10'
    assert all(
        rule['noDataState'] == 'NoData'
        for rule in product_rules
        if rule['uid'] != 'omi-journey-live-transcription-fail'
    )
    scrape_rule = next(rule for rule in split_alerts if rule['uid'] == 'omi-journey-scrape-missing')
    assert scrape_rule['noDataState'] == 'Alerting'
    assert 'count by (job)' in scrape_rule['data'][0]['model']['expr']
    assert 'backend-listen-metrics|pusher-metrics' in scrape_rule['data'][0]['model']['expr']

    dashboard = json.loads(
        (monitoring / 'dashboards/omi-services/resilience-fallbacks.json').read_text(encoding='utf-8')
    )
    panel_titles = {panel['title'] for panel in dashboard['panels']}
    assert 'Journey terminal success rate (success / success + failure)' in panel_titles
    assert 'Live STT attempt failure rate (failure / accepted)' in panel_titles
    assert 'Journey acceptance-to-terminal latency (p95)' in panel_titles
    assert 'Capture finalization durable projection and nonterminal work' in panel_titles
    assert 'LLM gateway LKG serving share (rollout exposure)' in panel_titles
    live_stt_panel = next(
        panel for panel in dashboard['panels'] if panel['title'].startswith('Live STT attempt failure')
    )
    generic_terminal_panel = next(panel for panel in dashboard['panels'] if panel['id'] == 7)
    assert generic_terminal_panel['title'] == 'Journey terminal success rate (success / success + failure)'
    assert 'omi_journey_terminal_total{outcome=~"success|failure"}' in generic_terminal_panel['targets'][0]['expr']
    assert 'and on (journey)' in generic_terminal_panel['targets'][0]['expr']
    assert live_stt_panel['id'] == 10
    assert live_stt_panel['gridPos'] == {'h': 8, 'w': 24, 'x': 0, 'y': 40}
    assert 'omi_live_stt_terminal_total{outcome="failure"}' in live_stt_panel['targets'][0]['expr']
    assert 'omi_live_stt_accepted_total' in live_stt_panel['targets'][0]['expr']
    capture_rule = next(rule for rule in split_alerts if rule['uid'] == 'omi-journey-capture-fail')
    assert 'listen_finalization_durable_jobs' in capture_rule['data'][0]['model']['expr']
    assert 'max by (state)' in capture_rule['data'][0]['model']['expr']
    assert 'clamp_min(delta' in capture_rule['data'][1]['model']['expr']
    projection_panel = next(panel for panel in dashboard['panels'] if panel['id'] == 9)
    assert projection_panel['targets'][0]['expr'] == 'max by (state) (listen_finalization_durable_jobs)'
    dead_emission_rule = next(rule for rule in split_alerts if rule['uid'] == 'omi-capture-finalization-dead-emission')
    assert 'max(listen_finalization_durable_jobs{state="accepted"})' in dead_emission_rule['data'][0]['model']['expr']
    assert 'max by (state)' in dead_emission_rule['data'][1]['model']['expr']
    assert dead_emission_rule['data'][2]['model']['expression'] == '$A >= 5 && $B == 0'
    lkg_panel = next(panel for panel in dashboard['panels'] if panel['id'] == 11)
    assert 'route_serving_class="lkg"' in lkg_panel['targets'][0]['expr']
    assert 'fallback_used' not in lkg_panel['targets'][0]['expr']


def test_omi_queue_family_is_not_zero_initialised():
    exported = metrics.generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{' not in exported
    monitoring = REPO / 'backend/charts/monitoring'
    split = json.loads((monitoring / 'alerts/resilience.json').read_text(encoding='utf-8'))
    rule = next(item for item in split if item['uid'] == 'omi-queue-oldest-ready')
    assert rule['noDataState'] == 'Alerting'
