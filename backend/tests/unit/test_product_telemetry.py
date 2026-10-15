import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils import product_telemetry as telemetry


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    telemetry.set_product_telemetry_client_for_tests(None)
    for key in (*telemetry._CAPTURE_KEYS, 'POSTHOG_INTERNAL_UIDS', 'POSTHOG_TEST_UIDS', 'OMI_ENV_STAGE', 'ENVIRONMENT'):
        monkeypatch.delenv(key, raising=False)
    yield
    telemetry.set_product_telemetry_client_for_tests(None)


def test_defaults_privacy_and_roster(monkeypatch):
    fake = Mock()
    telemetry.set_product_telemetry_client_for_tests(fake)
    monkeypatch.setenv('POSTHOG_INTERNAL_UIDS', ' staff,other ')
    monkeypatch.setenv('POSTHOG_TEST_UIDS', 'tester')
    for uid in ('staff', 'tester', 'omi-release-probe', 'cfc_synthetic', 'external'):
        assert telemetry.emit_product_event(
            uid=uid,
            event='Example',
            properties={
                'uid': uid,
                'conversation_id': 'private',
                'query': 'private',
                'count': 2,
            },
        )
    props = [call.kwargs['properties'] for call in fake.capture.call_args_list]
    assert props[0] == {
        'count': 2,
        'internal': True,
        'source_platform': 'unknown',
        'test': False,
        'emitter': 'server',
        'environment': 'unknown',
    }
    assert all(p['test'] for p in props[1:4])
    assert 'internal' not in props[4]


@pytest.mark.parametrize('platform', sorted(telemetry.SOURCE_PLATFORMS))
def test_request_context_and_background_propagation(platform):
    from utils.executors import submit_with_context

    with ThreadPoolExecutor(max_workers=1) as executor:
        with telemetry.product_telemetry_context(
            headers={
                'x-app-platform': platform,
                'x-build-channel': 'testflight',
                'x-internal': 'true',
            }
        ):
            props = submit_with_context(executor, telemetry.server_event_properties, 'u', {}).result()
            assert props['source_platform'] == platform
            assert props['build_channel'] == 'testflight'
            assert 'internal' not in props
            assert props['test'] is False
            assert (
                telemetry.server_event_properties('u', {'source_platform': 'android'})['source_platform'] == 'android'
            )
        assert telemetry.server_event_properties('u', {})['source_platform'] == 'unknown'


def test_concurrent_requests_cannot_leak_context():
    async def request(platform):
        with telemetry.product_telemetry_context(headers={'x-app-platform': platform}):
            await asyncio.sleep(0)
            return telemetry.server_event_properties('u', {})['source_platform']

    async def run():
        return await asyncio.gather(request('ios'), request('web'))

    assert asyncio.run(run()) == ['ios', 'web']


def test_invalid_metadata_is_bounded():
    props = telemetry.server_event_properties(
        'u', {'app_platform': 'Darwin', 'build_channel': 'private@example.com', 'internal': 'true'}
    )
    assert props['source_platform'] == 'unknown'
    assert 'build_channel' not in props
    assert 'internal' not in props


def test_single_client_key_precedence_and_lazy_concurrent_construction(monkeypatch):
    sdk = Mock()
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=factory))
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'disabled')
    monkeypatch.setenv('POSTHOG_EVENTS_API_KEY', ' phc_events ')
    monkeypatch.setenv('POSTHOG_BILLING_API_KEY', 'phc_billing')
    with ThreadPoolExecutor(max_workers=4) as executor:
        clients = list(executor.map(lambda _: telemetry.get_server_posthog_client(), range(12)))
    assert all(client is clients[0] for client in clients)
    factory.assert_called_once_with(
        project_api_key='phc_events', host='https://app.posthog.com', sync_mode=True, timeout=2, max_retries=0
    )


@pytest.mark.parametrize('key', ['disabled', 'placeholder-phc_private', 'phx_personal'])
def test_invalid_keys_never_construct_sdk_or_leak(monkeypatch, caplog, key):
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', key)
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: pytest.fail('invalid SDK construction'))
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})
    if key != 'disabled':
        assert key not in caplog.text


def test_capture_failure_and_queue_rejection_are_not_success():
    fake = Mock()
    telemetry.set_product_telemetry_client_for_tests(fake)
    fake.capture.side_effect = RuntimeError('secret')
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})
    fake.capture.side_effect = None
    fake.capture.return_value = (False, {})
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})


def test_nonbilling_delivery_is_offloaded_and_billing_is_synchronous(monkeypatch):
    from utils import executors

    sdk = Mock()
    submit = Mock()
    monkeypatch.setattr(executors, 'submit_with_context', submit)
    client = telemetry._ServerCaptureClient(sdk)
    client.capture(event='Example')
    sdk.capture.assert_not_called()
    submit.assert_called_once()
    submit.call_args.args[1]()
    sdk.capture.assert_called_once_with(event='Example')
    client.capture(event='Billing Subscription Started')
    assert sdk.capture.call_count == 2


def test_emitters_route_through_shared_capture():
    from utils import integration_telemetry

    fake = Mock()
    telemetry.set_product_telemetry_client_for_tests(fake)
    integration_telemetry.emit_posthog_event('u', 'Integration Sync Succeeded', {'app_platform': 'ios'})
    integration_telemetry.emit_posthog_event('u', 'Integration Auth Refresh Succeeded', {'source_platform': 'mcp'})
    assert fake.capture.call_args_list[0].kwargs['properties']['source_platform'] == 'ios'
    assert fake.capture.call_args_list[1].kwargs['properties']['source_platform'] == 'mcp'
    assert all(call.kwargs['properties']['emitter'] == 'server' for call in fake.capture.call_args_list)


def test_closed_experiment_names_survive_but_raw_identifiers_do_not():
    assert (
        telemetry.server_event_properties('u', {'experiment_id': 'EXP-001-day3-reengagement'})['experiment_id']
        == 'EXP-001-day3-reengagement'
    )
    assert 'experiment_id' not in telemetry.server_event_properties('u', {'experiment_id': 'private-uid'})


def test_queue_budget_rejects_without_blocking_and_releases_after_delivery(monkeypatch):
    from threading import BoundedSemaphore
    from utils import executors

    queued = []
    monkeypatch.setattr(executors, 'submit_with_context', lambda executor, fn: queued.append(fn))
    sdk = Mock()
    client = telemetry._ServerCaptureClient(sdk)
    client.pending = BoundedSemaphore(1)
    assert client.capture(event='Example') is True
    assert client.capture(event='Example') is False
    queued.pop()()
    assert client.capture(event='Example') is True
    queued.pop()()
