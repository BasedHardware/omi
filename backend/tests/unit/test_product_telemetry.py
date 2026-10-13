import logging
from types import SimpleNamespace

import pytest

from utils import product_telemetry
from utils.product_telemetry import emit_product_event, set_product_telemetry_client_for_tests


class _FakePosthog:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.events = []

    def capture(self, **event):
        if self.fail:
            raise RuntimeError('posthog unavailable')
        self.events.append(event)


@pytest.fixture(autouse=True)
def _reset_client():
    yield
    set_product_telemetry_client_for_tests(None)


def test_product_event_uses_uid_only_as_distinct_id_and_drops_null_properties(monkeypatch):
    fake = _FakePosthog()
    set_product_telemetry_client_for_tests(fake)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')

    emit_product_event(
        uid='user-1',
        event='Transcript Started',
        properties={'recording_id': 'recording-1', 'conversation_id': None},
    )

    assert fake.events == [
        {
            'distinct_id': 'user-1',
            'event': 'Transcript Started',
            'properties': {'recording_id': 'recording-1', 'environment': 'dev'},
        }
    ]


def test_product_event_is_fail_open():
    set_product_telemetry_client_for_tests(_FakePosthog(fail=True))

    emit_product_event(uid='user-1', event='Transcript Failed', properties={})


def _reject_sdk(name):
    raise AssertionError(f'must not construct SDK for {name}')


@pytest.mark.parametrize('raw_key', ['disabled', '  disabled\n', 'placeholder-phc_leak'])
def test_invalid_billing_project_key_is_absent_and_logged_once(monkeypatch, caplog, raw_key):
    set_product_telemetry_client_for_tests(None)
    monkeypatch.setenv('POSTHOG_BILLING_API_KEY', raw_key)
    monkeypatch.delenv('POSTHOG_PROJECT_API_KEY', raising=False)
    monkeypatch.delenv('POSTHOG_API_KEY', raising=False)
    monkeypatch.setattr(product_telemetry.importlib, 'import_module', _reject_sdk)

    with caplog.at_level(logging.WARNING, logger='utils.product_telemetry'):
        assert product_telemetry._get_billing_client() is None
        assert product_telemetry._get_billing_client() is None
        emit_product_event(uid='user-1', event='Billing Subscription Started', properties={})

    warnings = [
        record
        for record in caplog.records
        if record.name == 'utils.product_telemetry' and record.levelno >= logging.WARNING
    ]
    assert [record.getMessage() for record in warnings] == ['billing telemetry disabled: invalid project key']
    assert all(not record.args for record in warnings)
    # The warning text itself contains the word "disabled". Any other key bytes must stay out.
    if raw_key != 'disabled':
        assert raw_key not in caplog.text
    assert 'phc_' not in caplog.text


def test_missing_billing_key_does_not_log_invalid_project_key(monkeypatch, caplog):
    set_product_telemetry_client_for_tests(None)
    for name in ('POSTHOG_BILLING_API_KEY', 'POSTHOG_PROJECT_API_KEY', 'POSTHOG_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(product_telemetry.importlib, 'import_module', _reject_sdk)

    with caplog.at_level(logging.WARNING, logger='utils.product_telemetry'):
        assert product_telemetry._get_billing_client() is None

    assert caplog.records == []


def test_invalid_billing_key_falls_through_to_public_project_key(monkeypatch, caplog):
    set_product_telemetry_client_for_tests(None)
    created = []

    class Client:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setenv('POSTHOG_BILLING_API_KEY', 'disabled')
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', '  phc_shared-project \n')
    monkeypatch.delenv('POSTHOG_HOST', raising=False)
    monkeypatch.setattr(product_telemetry.importlib, 'import_module', lambda _: SimpleNamespace(Posthog=Client))
    with caplog.at_level(logging.WARNING, logger='utils.product_telemetry'):
        client = product_telemetry._get_billing_client()

    assert client is not None
    assert created == [
        {
            'project_api_key': 'phc_shared-project',
            'host': 'https://app.posthog.com',
            'sync_mode': True,
            'timeout': 2,
            'max_retries': 0,
        }
    ]
    assert caplog.records == []
    assert 'disabled' not in caplog.text
