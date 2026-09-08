import pytest

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
