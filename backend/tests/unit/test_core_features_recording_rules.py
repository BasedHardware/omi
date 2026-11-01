"""Keep the Core Features recording rules installable and cheap to read."""

from pathlib import Path

import yaml

RULES = Path(__file__).resolve().parents[2] / 'charts/monitoring/core-features/recording-rules.yaml'


def _document():
    return yaml.safe_load(RULES.read_text())


def test_prometheus_operator_selects_the_rule():
    metadata = _document()['metadata']
    assert metadata['namespace'] == 'prod-omi-monitoring'
    assert metadata['labels'] == {'release': 'prod-omi-kube-prometheus-stack'}


def test_rules_only_record_and_drop_instance_labels():
    (group,) = _document()['spec']['groups']
    # Tiles multiply sum_over_time by 60, so this interval is part of their arithmetic.
    assert group['interval'] == '1m'
    assert all('alert' not in rule for rule in group['rules'])
    # A label dropped here cannot be recovered later, because recorded history starts at the install.
    assert {rule['record']: rule['expr'] for rule in group['rules']} == {
        'source_outcome:omi_listen_audio_outcome:rate5m_offset5m': 'sum by (transcription_source, outcome) (rate(omi_listen_audio_outcome_total[5m] offset 5m))',
        'source:omi_listen_accepted:rate5m_offset5m': 'sum by (transcription_source) (rate(omi_listen_accepted_total[5m] offset 5m))',
        'journey_outcome:omi_journey_terminal:rate5m_offset5m': 'sum by (journey, outcome) (rate(omi_journey_terminal_total[5m] offset 5m))',
        'job_journey_outcome:omi_client_journey_terminal:rate5m_offset5m': 'sum by (job, journey, outcome) (rate(omi_client_journey_terminal_total[5m] offset 5m))',
        'lane_outcome:llm_gateway_requests:rate5m_offset5m': 'sum by (lane_id, outcome) (rate(llm_gateway_requests_total[5m] offset 5m))',
        'outcome:omi_conversation_summary_vector_upserts:rate5m_offset5m': 'sum by (outcome) (rate(omi_conversation_summary_vector_upserts_total[5m] offset 5m))',
        'event_plan:omi_subscription_events:rate5m_offset5m': 'sum by (event, plan) (rate(omi_subscription_events_total[5m] offset 5m))',
    }
