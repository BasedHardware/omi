from __future__ import annotations

import logging

from llm_gateway.gateway import metrics


class _MetricChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self):
        self.parent.increments.append(self.labels)

    def observe(self, value):
        self.parent.observations.append((self.labels, value))


class _Metric:
    def __init__(self):
        self.increments: list[dict[str, str]] = []
        self.observations: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels):
        return _MetricChild(self, labels)


def test_stream_terminal_metric_exposes_bounded_surface_phase_and_byok_source(monkeypatch):
    requests = _Metric()
    latency = _Metric()
    ttfb = _Metric()
    monkeypatch.setattr(metrics, 'REQUESTS_TOTAL', requests)
    monkeypatch.setattr(metrics, 'REQUEST_LATENCY_SECONDS', latency)
    monkeypatch.setattr(metrics, 'STREAM_TTFB_SECONDS', ttfb)

    metrics.observe_route_result(
        metrics.time_request() - 2.0,
        lane_id='omi:auto:chat-agent',
        route_artifact_id='route.chat_agent.model_config.001',
        provider='anthropic',
        model='claude-sonnet-5',
        credential_source='service_forwarded_byok',
        used_lkg=False,
        fallback_used=False,
        fallback_reason=None,
        outcome='error',
        error_class='transport_midstream',
        request_id='936c2c10-c509-41f1-95cf-2162710d5ac8',
        api_surface='anthropic_messages',
        streaming=True,
        phase='midstream',
        ttfb_seconds=0.42,
        budget_source='route_default',
        output_budget='le_128',
        completion_size='le_256',
        finish_reason='length',
    )

    labels = requests.increments[0]
    assert labels['api_surface'] == 'anthropic_messages'
    assert labels['streaming'] == 'true'
    assert labels['phase'] == 'midstream'
    assert labels['credential_source'] == 'service_forwarded_byok'
    assert labels['budget_source'] == 'route_default'
    assert labels['output_budget'] == 'le_128'
    assert labels['completion_size'] == 'le_256'
    assert labels['finish_reason'] == 'length'
    assert 'request_id' not in labels
    assert latency.observations[0][0] == labels
    assert ttfb.observations == [
        (
            {
                'api_surface': 'anthropic_messages',
                'provider': 'anthropic',
                'credential_source': 'service_forwarded_byok',
            },
            0.42,
        )
    ]


def test_observation_failure_warning_is_rate_limited_and_payload_free(monkeypatch, caplog):
    monkeypatch.setattr(metrics, '_last_observation_warning_at', 0.0)

    with caplog.at_level(logging.WARNING, logger=metrics.logger.name):
        metrics.report_observation_failure(api_surface='anthropic_messages', request_id='request-1')
        metrics.report_observation_failure(api_surface='anthropic_messages', request_id='request-2')

    matching = [record.message for record in caplog.records if 'llm_gateway_observation_failed' in record.message]
    assert matching == ['llm_gateway_observation_failed request_id=request-1 surface=anthropic_messages']


def test_terminal_errors_are_warning_logs_with_only_bounded_failure_fields(monkeypatch, caplog):
    requests = _Metric()
    latency = _Metric()
    monkeypatch.setattr(metrics, 'REQUESTS_TOTAL', requests)
    monkeypatch.setattr(metrics, 'REQUEST_LATENCY_SECONDS', latency)

    with caplog.at_level(logging.WARNING, logger=metrics.logger.name):
        metrics.observe_route_result(
            metrics.time_request(),
            lane_id='omi:auto:conv-structure',
            route_artifact_id='route.conv_structure.model_config.001',
            provider='none',
            model='none',
            credential_source='service_forwarded_byok',
            used_lkg=False,
            fallback_used=False,
            fallback_reason='byok_auth',
            outcome='error',
            error_class='credential_failure',
            request_id='936c2c10-c509-41f1-95cf-2162710d5ac8',
            api_surface='openai_chat_completions',
            streaming=False,
            phase='before_output',
        )

    matching = [record.message for record in caplog.records if 'llm_gateway_terminal' in record.message]
    assert matching == [
        'llm_gateway_terminal request_id=936c2c10-c509-41f1-95cf-2162710d5ac8 '
        'surface=openai_chat_completions streaming=false phase=before_output '
        'lane=omi:auto:conv-structure route=route.conv_structure.model_config.001 '
        'provider=none model=none credential_source=service_forwarded_byok outcome=error '
        'error_class=credential_failure failure_class=byok_auth fallback_used=false budget_source=none '
        'output_budget=none completion_size=unknown finish_reason=unknown ttfb_seconds=none'
    ]


def test_pre_route_rejection_metric_has_only_bounded_contract_labels(monkeypatch, caplog):
    rejections = _Metric()
    monkeypatch.setattr(metrics, 'REQUEST_REJECTIONS_TOTAL', rejections)

    with caplog.at_level(logging.WARNING, logger=metrics.logger.name):
        metrics.observe_request_rejection(
            api_surface='openai_chat_completions',
            error_class='invalid_request',
            request_id='5d1baae6-c824-4988-adc3-ae82df35cfa5',
        )

    assert rejections.increments == [
        {
            'api_surface': 'openai_chat_completions',
            'error_class': 'invalid_request',
        }
    ]
    assert [record.message for record in caplog.records if 'llm_gateway_request_rejected' in record.message] == [
        'llm_gateway_request_rejected request_id=5d1baae6-c824-4988-adc3-ae82df35cfa5 '
        'surface=openai_chat_completions error_class=invalid_request'
    ]
