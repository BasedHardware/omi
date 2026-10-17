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


def test_family_clients_are_lazy_and_constructed_once_under_concurrency(monkeypatch):
    factory = Mock(side_effect=lambda **kwargs: Mock(**kwargs))
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=factory))
    monkeypatch.setenv('POSTHOG_PRODUCT_CAPTURE_TOKEN', ' phc_product_capture ')
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'disabled')
    monkeypatch.setenv('POSTHOG_EVENTS_API_KEY', 'phc_events')
    monkeypatch.setenv('POSTHOG_BILLING_API_KEY', 'phc_billing')
    factory.assert_not_called()
    events = ['Example', 'Billing Subscription Started', 'MCP Tool Use Succeeded'] * 12
    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(telemetry.get_server_posthog_client, events))
    assert len({id(client) for client in clients}) == 3
    assert factory.call_count == 3
    configuration = {call.kwargs['project_api_key']: call.kwargs for call in factory.call_args_list}
    assert configuration['phc_product_capture']['sync_mode'] is False
    assert configuration['phc_events']['sync_mode'] is False
    assert configuration['phc_billing']['sync_mode'] is True
    assert all(config['max_queue_size'] == 1000 for config in configuration.values())
    # Integration and extraction share the product family, not another SDK.
    assert telemetry.get_server_posthog_client('Integration Sync Succeeded') is clients[0]
    assert telemetry.get_server_posthog_client('Conversation Memories Extracted') is clients[0]
    assert factory.call_count == 3


@pytest.mark.parametrize('key', ['disabled', 'placeholder-phc_private', 'phx_personal'])
def test_invalid_keys_never_construct_sdk_or_leak(monkeypatch, caplog, key):
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', key)
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: pytest.fail('invalid SDK construction'))
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})
    if key != 'disabled':
        assert key not in caplog.text


def test_disabled_product_capture_token_does_not_fall_back_to_project_key(monkeypatch):
    monkeypatch.setenv('POSTHOG_PRODUCT_CAPTURE_TOKEN', 'disabled')
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'phc_project')
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: pytest.fail('invalid SDK construction'))
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})


def test_absent_product_capture_token_keeps_project_and_legacy_fallback_order(monkeypatch):
    assert telemetry._capture_project_key('Example') is None
    monkeypatch.setenv('POSTHOG_API_KEY', 'phc_legacy')
    assert telemetry._capture_project_key('Example') == 'phc_legacy'
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'phc_project')
    assert telemetry._capture_project_key('Example') == 'phc_project'


def test_product_capture_token_wins_over_disabled_project_key(monkeypatch):
    factory = Mock(return_value=Mock())
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=factory))
    monkeypatch.setenv('POSTHOG_PRODUCT_CAPTURE_TOKEN', 'phc_product_capture')
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'disabled')
    assert telemetry.emit_product_event(uid='u', event='Example', properties={})
    factory.assert_called_once()
    assert factory.call_args.kwargs['project_api_key'] == 'phc_product_capture'


def test_capture_failure_and_queue_rejection_are_not_success():
    fake = Mock()
    telemetry.set_product_telemetry_client_for_tests(fake)
    fake.capture.side_effect = RuntimeError('secret')
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})
    fake.capture.side_effect = None
    fake.capture.return_value = (False, {})
    assert not telemetry.emit_product_event(uid='u', event='Example', properties={})


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


def test_disabled_project_with_valid_billing_key_enables_billing_only(monkeypatch):
    from utils import integration_telemetry

    sdk = Mock()
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=factory))
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'disabled')
    monkeypatch.setenv('POSTHOG_BILLING_API_KEY', 'phc_billing')
    # Construct billing first: its cached SDK must not enable any
    # other family, including the per-success MCP marker.
    assert telemetry.emit_product_event(uid='u', event='Billing Subscription Started', properties={})
    for event in (
        'Example',
        'Conversation Memories Extracted',
        'MCP Active',
        'MCP Tool Call',
        'MCP Tool Use Succeeded',
    ):
        assert not telemetry.emit_product_event(uid='u', event=event, properties={})
    integration_telemetry.emit_posthog_event('u', 'Integration Sync Succeeded', {})
    factory.assert_called_once()
    assert factory.call_args.kwargs['project_api_key'] == 'phc_billing'
    sdk.capture.assert_called_once()
    assert sdk.capture.call_args.kwargs['event'] == 'Billing Subscription Started'
    assert sdk.capture.call_args.kwargs['properties']['emitter'] == 'server'


@pytest.mark.parametrize(
    'configured,enabled',
    [
        ({'POSTHOG_EVENTS_API_KEY': 'phc_mcp'}, {'MCP Tool Use Succeeded'}),
        ({'POSTHOG_BILLING_API_KEY': 'phc_billing'}, {'Billing Subscription Started'}),
        ({'POSTHOG_PROJECT_API_KEY': 'phc_product'}, {'Example'}),
        ({'POSTHOG_API_KEY': 'phc_legacy'}, {'Example'}),
        ({'POSTHOG_PROJECT_API_KEY': 'disabled', 'POSTHOG_API_KEY': 'phc_legacy'}, set()),
        (
            {
                'POSTHOG_PROJECT_API_KEY': 'phc_product',
                'POSTHOG_BILLING_API_KEY': 'disabled',
                'POSTHOG_EVENTS_API_KEY': 'disabled',
            },
            {'Example'},
        ),
    ],
)
def test_family_enablement_never_falls_back_across_families(monkeypatch, configured, enabled):
    sdk = Mock()
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=factory))
    for name, value in configured.items():
        monkeypatch.setenv(name, value)
    for event in ('Example', 'Billing Subscription Started', 'MCP Tool Use Succeeded'):
        assert telemetry.emit_product_event(uid='u', event=event, properties={}) is (event in enabled)
    assert {call.kwargs['event'] for call in sdk.capture.call_args_list} == enabled
    assert factory.call_count == bool(enabled)


def test_real_family_sdks_keep_keys_and_capture_independently_of_blocked_billing(monkeypatch):
    from threading import Event
    import posthog.client as sdk_module
    import posthog.consumer as consumer_module

    keys = {
        'Example': 'phc_product',
        'Billing Subscription Started': 'phc_billing',
        'MCP Tool Use Succeeded': 'phc_mcp',
    }
    for name, value in zip(
        ('POSTHOG_PROJECT_API_KEY', 'POSTHOG_BILLING_API_KEY', 'POSTHOG_EVENTS_API_KEY'), keys.values()
    ):
        monkeypatch.setenv(name, value)
    billing_started, release_billing = Event(), Event()
    delivered = {key: Event() for key in keys.values()}
    clients = []
    captures = []
    original_sdk = sdk_module.Client

    def factory(**kwargs):
        sdk = original_sdk(**kwargs)
        clients.append(sdk)
        return sdk

    def capture_transport(api_key, host, **kwargs):
        if api_key == 'phc_billing':
            billing_started.set()
            assert release_billing.wait(10)
        for message in kwargs['batch']:
            assert api_key == keys[message['event']]
            assert not any(key in repr(message) for key in keys.values())
            captures.append((message['event'], api_key))
        delivered[api_key].set()

    monkeypatch.setattr(telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=factory))
    monkeypatch.setattr(sdk_module, 'batch_post', capture_transport)
    monkeypatch.setattr(consumer_module, 'batch_post', capture_transport)
    with ThreadPoolExecutor(max_workers=3) as executor:
        billing = executor.submit(
            telemetry.emit_product_event, uid='u', event='Billing Subscription Started', properties={}
        )
        try:
            assert billing_started.wait(10)
            for event in ('Example', 'MCP Tool Use Succeeded'):
                # Construction and capture both finish while billing's network
                # call is blocked. Native SDK consumers also deliver independently.
                assert executor.submit(telemetry.emit_product_event, uid='u', event=event, properties={}).result(5)
                assert delivered[keys[event]].wait(10)
            assert not billing.done()
        finally:
            release_billing.set()
        assert billing.result(5)
    for client in clients:
        if not client.sync_mode:
            client.shutdown()
    assert len(clients) == 3
    assert len(captures) == 3
    assert {client.api_key for client in clients} == set(keys.values())


def test_sdk_delivery_error_callback_reports_without_batch_content(caplog, monkeypatch):
    fallback = Mock()
    monkeypatch.setattr(telemetry, '_fallback', fallback)
    telemetry._capture_error(RuntimeError('private'), [{'content': 'secret-batch'}])
    fallback.assert_called_once()
    assert 'private' not in caplog.text
    assert 'secret-batch' not in caplog.text
