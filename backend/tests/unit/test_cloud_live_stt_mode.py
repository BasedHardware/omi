"""CLOUD_LIVE_STT_MODE policy: stream default, when_watched reuse, off deferral."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.cloud_live_stt import OFF, STREAM, WHEN_WATCHED, resolve_cloud_live_stt_mode, suppresses_provider_stream
from config.live_demand import resolve_live_demand
from routers.listen import receiver as receiver_module
from routers.listen.receiver import ListenReceiver
from utils.metrics import OMI_CLOUD_LIVE_STT_MODE_SESSIONS_TOTAL, OMI_CLOUD_LIVE_STT_SAVED_SECONDS_TOTAL

ENV_NAME = 'CLOUD_LIVE_STT_MODE'


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)


def sessions_count(mode, local_preview='false'):
    return sum(
        sample.value
        for metric in OMI_CLOUD_LIVE_STT_MODE_SESSIONS_TOTAL.collect()
        for sample in metric.samples
        if sample.labels.get('mode') == mode and sample.labels.get('local_preview') == local_preview
    )


def saved_seconds(mode):
    return sum(
        sample.value
        for metric in OMI_CLOUD_LIVE_STT_SAVED_SECONDS_TOTAL.collect()
        for sample in metric.samples
        if sample.labels.get('mode') == mode
    )


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        (None, STREAM),
        ('', STREAM),
        ('stream', STREAM),
        ('STREAM', STREAM),
        (' when_watched ', WHEN_WATCHED),
        ('off', OFF),
        ('bogus', STREAM),
        ('0', STREAM),
    ],
)
def test_mode_resolution_fails_safe_to_stream(raw, expected, monkeypatch):
    if raw is not None:
        monkeypatch.setenv(ENV_NAME, raw)
    assert resolve_cloud_live_stt_mode() == expected


def test_mode_resolution_explicit_env_mapping():
    assert resolve_cloud_live_stt_mode(env={ENV_NAME: 'off'}) == OFF
    assert resolve_cloud_live_stt_mode(env={}) == STREAM


@pytest.mark.parametrize(
    ('mode', 'use_custom_stt', 'suppressed'),
    [
        (STREAM, False, False),
        (WHEN_WATCHED, False, False),
        (OFF, False, True),
        (OFF, True, False),  # BYOK custom STT is the user's own provider; never suppressed.
    ],
)
def test_suppression_matrix(mode, use_custom_stt, suppressed):
    assert suppresses_provider_stream(mode, use_custom_stt=use_custom_stt) is suppressed


def test_when_watched_reuses_live_demand_machinery():
    # No parallel switch: the existing #21481 demand routing is forced admitted.
    config = resolve_live_demand(flags={ENV_NAME: 'when_watched', 'STT_LIVE_DEMAND_ENABLED': 'false'})
    assert config.enabled and config.percent == 100
    assert config.admits('any-user')
    # Without the mode, the dark default is unchanged.
    dark = resolve_live_demand(flags={'STT_LIVE_DEMAND_ENABLED': 'false'})
    assert not dark.enabled and not dark.admits('any-user')


def make_receiver(*, use_custom_stt=False, local_preview=False, demand_totals=None):
    host = SimpleNamespace(
        request=SimpleNamespace(uid='user', sample_rate=16000, local_preview=local_preview),
        use_custom_stt=use_custom_stt,
        client_device_context=None,
    )
    host.state = SimpleNamespace(
        realtime_demand=SimpleNamespace(totals=lambda: dict(demand_totals or {})),
    )
    return SimpleNamespace(
        host=host,
        cloud_live_suppressed=False,
        _telemetry_platform=lambda: 'ios',
    )


@pytest.mark.asyncio
async def test_off_mode_persists_without_provider_stream(monkeypatch):
    monkeypatch.setenv(ENV_NAME, 'off')
    # Provider selection, demand attach and any provider dial must never run.
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', Mock())
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(side_effect=AssertionError('demand attached')))
    fake = make_receiver()
    before = sessions_count(OFF)

    assert await ListenReceiver._initialize_stt(fake)

    assert fake.cloud_live_suppressed is True
    receiver_module.capture_batch_preview.assert_called_once_with(fake.host, select_provider=False)
    assert sessions_count(OFF) == before + 1
    # A suppressed session never hands over between lanes.
    monkeypatch.setattr(
        receiver_module, 'switch_live_demand', AsyncMock(side_effect=AssertionError('switched while suppressed'))
    )
    assert await ListenReceiver._switch_live_demand(fake, 'vendor') is False


@pytest.mark.asyncio
async def test_off_mode_never_suppresses_custom_stt(monkeypatch):
    monkeypatch.setenv(ENV_NAME, 'off')
    selected = Mock()
    attached = Mock(return_value=None)
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', selected)
    monkeypatch.setattr(receiver_module, 'attach_live_demand', attached)
    fake = make_receiver(use_custom_stt=True)

    assert await ListenReceiver._initialize_stt(fake)

    assert fake.cloud_live_suppressed is False
    selected.assert_called_with(fake.host)  # provider selection ran as usual


@pytest.mark.asyncio
async def test_stream_default_behavior_unchanged(monkeypatch):
    selected = Mock()
    attached = Mock(return_value=None)
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', selected)
    monkeypatch.setattr(receiver_module, 'attach_live_demand', attached)
    fake = make_receiver(use_custom_stt=True)

    assert await ListenReceiver._initialize_stt(fake)

    assert fake.cloud_live_suppressed is False
    selected.assert_called_with(fake.host)
    attached.assert_called_once_with(fake)


@pytest.mark.asyncio
async def test_local_preview_declared_lands_in_session_counter(monkeypatch):
    monkeypatch.setenv(ENV_NAME, 'off')
    monkeypatch.setattr(receiver_module, 'capture_batch_preview', Mock())
    monkeypatch.setattr(receiver_module, 'attach_live_demand', Mock(side_effect=AssertionError))
    before = sessions_count(OFF, local_preview='true')

    assert await ListenReceiver._initialize_stt(make_receiver(local_preview=True))

    assert sessions_count(OFF, local_preview='true') == before + 1


@pytest.mark.asyncio
async def test_saved_seconds_by_mode():
    request = SimpleNamespace(sample_rate=16000)

    off = make_receiver(demand_totals={'background': 100.0, 'foreground': 50.0})
    off._cloud_live_mode = OFF
    off.cloud_live_suppressed = True
    before = saved_seconds(OFF)
    ListenReceiver._record_cloud_live_saved_seconds(off, request, 16000 * 2 * 10)
    assert saved_seconds(OFF) == pytest.approx(before + 10.0)
    # Once audio opened the deferred stream, that audio went to a provider.
    off.cloud_live_suppressed = False
    ListenReceiver._record_cloud_live_saved_seconds(off, request, 16000 * 2 * 10)
    assert saved_seconds(OFF) == pytest.approx(before + 10.0)

    watched = make_receiver(demand_totals={'background': 100.0, 'foreground': 50.0, 'visible': 5.0})
    watched._cloud_live_mode = WHEN_WATCHED
    before = saved_seconds(WHEN_WATCHED)
    ListenReceiver._record_cloud_live_saved_seconds(watched, request, 16000 * 2 * 10)
    assert saved_seconds(WHEN_WATCHED) == pytest.approx(before + 150.0)  # hidden seconds only

    stream = make_receiver()
    stream._cloud_live_mode = STREAM
    before = saved_seconds(STREAM)
    ListenReceiver._record_cloud_live_saved_seconds(stream, request, 16000 * 2 * 10)
    assert saved_seconds(STREAM) == pytest.approx(before)  # stream mode saves nothing


def test_listen_request_local_preview_defaults_false():
    from routers.listen.contracts import ListenRequest

    assert ListenRequest(websocket=None, uid='u').local_preview is False
