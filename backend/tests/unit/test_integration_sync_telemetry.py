import ast
from pathlib import Path

import httpx
import pytest
from utils.integration_telemetry import (
    GOOGLE_CALENDAR,
    X,
    IntegrationTelemetryContext,
    emit_sync_failed,
    emit_sync_succeeded,
    set_posthog_client_for_tests,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class FakePosthog:
    def __init__(self):
        self.calls = []

    def capture(self, *, distinct_id, event, properties):
        self.calls.append({'distinct_id': distinct_id, 'event': event, 'properties': properties})


@pytest.fixture(autouse=True)
def reset_posthog_client():
    set_posthog_client_for_tests(None)
    yield
    set_posthog_client_for_tests(None)


def _function_calls(path: str, function_name: str) -> set[str]:
    tree = ast.parse((BACKEND_DIR / path).read_text())
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == function_name:
            return {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            }
    raise AssertionError(f'{function_name} not found in {path}')


def test_sync_success_telemetry_emits_bounded_posthog_payload(monkeypatch):
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)
    monkeypatch.setenv('OMI_ENV_STAGE', 'test')

    emit_sync_succeeded(
        IntegrationTelemetryContext(
            integration_name=GOOGLE_CALENDAR,
            operation='fetch_events',
            uid='uid-123',
            app_platform='macos',
            app_version='1.2.3',
            app_build='456',
        ),
        item_count=27,
    )

    assert fake.calls == [
        {
            'distinct_id': 'uid-123',
            'event': 'Integration Sync Succeeded',
            'properties': {
                'integration_name': 'Google Calendar',
                'provider': 'Google Calendar',
                'operation': 'fetch_events',
                'status': 'succeeded',
                'error_bucket': 'none',
                'provider_status_code': None,
                'retryable': False,
                'environment': 'test',
                'app_platform': 'macos',
                'app_version': '1.2.3',
                'app_build': '456',
                'item_count': '11_100',
            },
        }
    ]


def test_sync_failure_telemetry_buckets_provider_errors_without_raw_body():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)
    request = httpx.Request('GET', 'https://api.x.com/2/users/me')
    response = httpx.Response(429, request=request, text='raw token abc123456789 and private body')
    error = httpx.HTTPStatusError('429 Too Many Requests raw token abc123456789', request=request, response=response)

    emit_sync_failed(
        IntegrationTelemetryContext(integration_name=X, operation='fetch_tweets', uid='uid-456'),
        error,
    )

    props = fake.calls[0]['properties']
    assert fake.calls[0]['event'] == 'Integration Sync Failed'
    assert props['integration_name'] == 'X'
    assert props['operation'] == 'fetch_tweets'
    assert props['error_bucket'] == 'rate_limited'
    assert props['provider_status_code'] == 429
    assert props['retryable'] is True
    assert 'raw token' not in str(props)


def test_failure_telemetry_ignores_non_integer_status_codes():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)

    class WeirdProviderError(Exception):
        status_code = 'not-a-status'

    emit_sync_failed(
        IntegrationTelemetryContext(integration_name=X, operation='fetch_tweets', uid='uid-789'),
        WeirdProviderError('provider failed'),
    )

    props = fake.calls[0]['properties']
    assert props['provider_status_code'] is None
    assert props['error_bucket'] == 'unknown'


def test_x_connector_sync_paths_keep_success_and_failure_telemetry_probe():
    calls = _function_calls('utils/x_connector.py', 'sync_x_for_user')

    assert 'emit_sync_attempted' in calls
    assert 'emit_sync_succeeded' in calls
    assert 'emit_sync_failed' in calls


def test_calendar_sync_paths_keep_success_and_failure_telemetry_probe():
    route_calls = _function_calls('routers/google_calendar.py', 'list_google_calendar_events')
    auto_link_calls = _function_calls('utils/conversations/calendar_linking.py', 'get_overlapping_calendar_event')
    tool_calls = _function_calls('utils/retrieval/tools/calendar_tools.py', 'get_calendar_events_tool')

    for calls in (route_calls, auto_link_calls, tool_calls):
        assert 'emit_sync_attempted' in calls
        assert 'emit_sync_succeeded' in calls
        assert 'emit_sync_failed' in calls
