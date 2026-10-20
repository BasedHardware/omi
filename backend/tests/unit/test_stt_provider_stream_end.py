"""Provider stream-end observability: closer, close-code class, vendor request id, latency.

Modulate's streaming failures (2026-10-14..20) could not be split from our own
pod restarts, and we had no vendor request id to hand them. These tests pin the
closed label vocabularies, the once-per-stream latch, and the real Modulate and
Soniox socket paths that feed it, including against a real websockets server.
"""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from utils.stt import provider_stream_end as pse
from utils.stt import soniox, streaming
from utils.stt.provider_stream_end import (
    CLOSERS,
    CODE_CLASSES,
    US_CLIENT_GONE,
    US_DRAIN,
    US_FAILOVER,
    US_TIMEOUT,
    VENDOR,
    ProviderStreamEnd,
    bounded_closer,
    bounded_request_id,
    close_code_class,
    handshake_request_id,
    note_stream_close_intent,
    teardown_closer,
    transport_closer,
)

SERVE_ERROR = 'Unable to complete the request. Please try again.'


def _end_count(provider, closer, code_class):
    return pse.OMI_STT_PROVIDER_STREAM_END_TOTAL.labels(
        provider=provider, closer=closer, code_class=code_class
    )._value.get()


def _histogram_count(histogram, provider):
    for metric in histogram.collect():
        for sample in metric.samples:
            if sample.name.endswith('_count') and sample.labels.get('provider') == provider:
                return sample.value
    return 0.0


class _Delta:
    def __init__(self, provider, closer, code_class):
        self.key = (provider, closer, code_class)
        self.before = _end_count(*self.key)

    @property
    def value(self):
        return _end_count(*self.key) - self.before


# --- closed vocabularies --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'code,expected',
    [
        (1000, '1000'),
        (1001, '1001'),
        (1006, '1006'),
        (1011, '1011'),
        (1012, 'other'),
        (1008, 'other'),
        (4000, '4xxx'),
        (4999, '4xxx'),
        (5000, 'other'),
        (None, 'none'),
        (-1, 'none'),
        (True, 'none'),
        ('1000', 'none'),
    ],
)
def test_close_code_class_is_bucketed(code, expected):
    assert close_code_class(code) == expected
    assert expected in CODE_CLASSES


def test_closer_vocabulary_is_the_five_named_closers():
    assert set(CLOSERS) == {'vendor', 'us_client_gone', 'us_drain', 'us_failover', 'us_timeout'}
    assert bounded_closer('pod_restart') == US_CLIENT_GONE
    assert bounded_closer(US_FAILOVER) == US_FAILOVER


def test_pod_restart_close_code_is_our_drain():
    assert teardown_closer(1012) == US_DRAIN
    for code in (1000, 1001, 1006, None):
        assert teardown_closer(code) == US_CLIENT_GONE


@pytest.mark.parametrize(
    'value,expected',
    [
        ('req-01HABCDEF', 'req-01HABCDEF'),
        ('Root=1-5759e988-bd862e3fe1be46a994272793', 'Root=1-5759e988-bd862e3fe1be46a994272793'),
        (12345, '12345'),
        ('someone@example.com', None),
        ('hello there transcript', None),
        ('x' * 129, None),
        ('', None),
        (None, None),
        (True, None),
        ({'nested': 'id'}, None),
    ],
)
def test_request_id_keeps_only_strict_id_shapes(value, expected):
    assert bounded_request_id(value) == expected


def test_handshake_request_id_reads_legacy_response_and_rejection_headers():
    legacy = SimpleNamespace(response_headers={'x-request-id': 'abc-123', 'cf-ray': 'ray-1'})
    assert handshake_request_id(legacy) == ('x-request-id', 'abc-123')
    rejection = SimpleNamespace(headers={'cf-ray': '8d1f-SJC'})
    assert handshake_request_id(rejection) == ('cf-ray', '8d1f-SJC')
    asyncio_client = SimpleNamespace(response=SimpleNamespace(headers={'x-amzn-trace-id': 'Root=1-ab'}))
    assert handshake_request_id(asyncio_client) == ('x-amzn-trace-id', 'Root=1-ab')
    assert handshake_request_id(object()) == (None, None)


@pytest.mark.parametrize(
    'error,expected',
    [
        (ConnectionClosedError(Close(1011, 'x'), None), VENDOR),
        (ConnectionClosedError(None, None), VENDOR),
        (ConnectionClosedError(None, Close(1011, 'keepalive ping timeout')), US_TIMEOUT),
        (ConnectionResetError(), VENDOR),
        (TimeoutError(), US_TIMEOUT),
        (RuntimeError('a bug of ours'), None),
        (KeyError('a bug of ours'), None),
    ],
)
def test_transport_closer_attributes_only_transport_failures(error, expected):
    assert transport_closer(error) == expected


# --- the once-per-stream latch ---------------------------------------------------------------------


def test_vendor_error_frame_is_recorded_once_with_the_vendor_close_code(caplog):
    caplog.set_level(logging.INFO, logger=pse.__name__)
    ws = SimpleNamespace(close_rcvd=Close(1011, 'private vendor body'), close_sent=Close(1000, ''))
    end = ProviderStreamEnd('modulate', SimpleNamespace(response_headers={'x-request-id': 'req-9'}))
    delta = _Delta('modulate', VENDOR, '1011')

    end.note_vendor_error('modulate_serve_error')
    end.note_intent(US_CLIENT_GONE)  # Teardown after a vendor death must not take the blame.
    assert end.record(ws) is True
    assert end.record(ws) is False

    assert delta.value == 1
    line = next(r for r in caplog.records if 'STT provider stream end' in r.getMessage())
    message = line.getMessage()
    assert line.levelno == logging.WARNING
    assert 'provider=modulate closer=vendor code_class=1011 received_code=1011 sent_code=1000' in message
    assert 'reason=modulate_serve_error request_id=req-9 request_id_header=x-request-id' in message
    assert 'private' not in caplog.text


def test_our_close_uses_the_first_intent_and_defaults_to_client_gone():
    ws = SimpleNamespace(close_rcvd=None, close_sent=Close(1000, ''))
    end = ProviderStreamEnd('soniox', None)
    end.note_intent(US_FAILOVER)
    end.note_intent(US_DRAIN)
    end.note_intent(VENDOR)  # Never an intent.
    delta = _Delta('soniox', US_FAILOVER, '1000')
    assert end.record(ws)
    assert delta.value == 1

    plain = ProviderStreamEnd('soniox', None)
    delta = _Delta('soniox', US_CLIENT_GONE, 'none')
    assert plain.record(SimpleNamespace())
    assert delta.value == 1


def test_transport_drop_without_frames_is_1006_and_a_bug_leaves_the_latch_open():
    end = ProviderStreamEnd('modulate', None)
    assert end.record(None, error=RuntimeError('ours')) is False
    assert not end.recorded
    delta = _Delta('modulate', VENDOR, '1006')
    assert end.record(None, error=ConnectionClosedError(None, None)) is True
    assert delta.value == 1


def test_unknown_provider_folds_to_the_bounded_label():
    end = ProviderStreamEnd('acme-stt', None)
    assert end.provider == 'unknown'


def test_every_exported_series_uses_closed_labels():
    providers = {'modulate', 'soniox', 'deepgram', 'parakeet', 'unknown'}
    for metric in pse.OMI_STT_PROVIDER_STREAM_END_TOTAL.collect():
        for sample in metric.samples:
            assert set(sample.labels) == {'provider', 'closer', 'code_class'}
            assert sample.labels['provider'] in providers
            assert sample.labels['closer'] in CLOSERS
            assert sample.labels['code_class'] in CODE_CLASSES
    for histogram in (pse.OMI_STT_PROVIDER_CONNECT_SECONDS, pse.OMI_STT_PROVIDER_FIRST_TEXT_SECONDS):
        for metric in histogram.collect():
            for sample in metric.samples:
                assert sample.labels['provider'] in providers


def test_first_text_is_measured_once_from_first_audio():
    now = [100.0]
    end = ProviderStreamEnd('modulate', None, clock=lambda: now[0])
    before = _histogram_count(pse.OMI_STT_PROVIDER_FIRST_TEXT_SECONDS, 'modulate')
    now[0] = 105.0
    end.note_audio_sent()
    now[0] = 106.5
    end.note_text()
    end.note_text()
    assert _histogram_count(pse.OMI_STT_PROVIDER_FIRST_TEXT_SECONDS, 'modulate') == before + 1


def test_intent_reaches_the_provider_latch_through_listen_wrappers():
    end = ProviderStreamEnd('soniox', None)
    transport = SimpleNamespace(stream_end=end)
    idle = SimpleNamespace(_transport=transport)
    gated = SimpleNamespace(_conn=idle)
    leg = SimpleNamespace(raw=gated)
    note_stream_close_intent(leg, US_DRAIN)
    delta = _Delta('soniox', US_DRAIN, 'none')
    end.record(SimpleNamespace())
    assert delta.value == 1
    note_stream_close_intent(None, US_DRAIN)  # Never raises on a missing socket.


# --- real Modulate socket ---------------------------------------------------------------------------


class _ScriptedWebSocket:
    def __init__(self, inbound, *, close_rcvd=None):
        self._inbound = list(inbound)
        self.close_rcvd = close_rcvd
        self.close_sent = None
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.close_sent = Close(1000, '')

    def __aiter__(self):
        async def gen():
            for msg in self._inbound:
                yield json.dumps(msg)
            await asyncio.Event().wait()

        return gen()


def test_modulate_serve_error_frame_is_a_vendor_end_with_the_frame_request_id(caplog):
    caplog.set_level(logging.INFO)

    async def run():
        ws = _ScriptedWebSocket(
            [{'type': 'error', 'error': SERVE_ERROR, 'request_id': 'mod-req-77'}], close_rcvd=Close(1011, '')
        )
        sock = streaming.SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
        await asyncio.sleep(0.05)
        sock.stream_end.note_intent(US_CLIENT_GONE)
        await sock.drain_and_close()

    delta = _Delta('modulate', VENDOR, '1011')
    asyncio.run(run())
    assert delta.value == 1
    assert 'Modulate streaming error: reason=modulate_serve_error' in caplog.text
    assert 'request_id=mod-req-77' in caplog.text
    assert 'closer=vendor code_class=1011' in caplog.text


def test_modulate_normal_drain_is_our_close_with_the_session_intent():
    async def run():
        ws = _ScriptedWebSocket([{'type': 'utterance', 'utterance': {'text': 'hi', 'start_ms': 0}}, {'type': 'done'}])
        sock = streaming.SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
        await asyncio.sleep(0.05)
        note_stream_close_intent(SimpleNamespace(_conn=sock), US_DRAIN)
        await sock.drain_and_close()

    delta = _Delta('modulate', US_DRAIN, '1000')
    texts = _histogram_count(pse.OMI_STT_PROVIDER_FIRST_TEXT_SECONDS, 'modulate')
    asyncio.run(run())
    assert delta.value == 1
    assert _histogram_count(pse.OMI_STT_PROVIDER_FIRST_TEXT_SECONDS, 'modulate') == texts + 1


def test_modulate_finish_without_drain_still_records_our_close():
    async def run():
        ws = _ScriptedWebSocket([])
        sock = streaming.SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
        note_stream_close_intent(sock, US_FAILOVER)
        sock.finish()
        sock.finish()
        sock._recv_task.cancel()
        await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)

    delta = _Delta('modulate', US_FAILOVER, 'none')
    asyncio.run(run())
    assert delta.value == 1


def test_modulate_connect_latency_and_rejection_request_id(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger=pse.__name__)
    monkeypatch.setenv('MODULATE_API_KEY', 'test-key')
    ws = _ScriptedWebSocket([])

    async def connect(*_args, **_kwargs):
        return ws

    async def rejected(*_args, **_kwargs):
        error = RuntimeError('handshake refused')
        error.status_code = 503
        error.headers = {'x-request-id': 'edge-503-1'}
        raise error

    async def run(connector):
        monkeypatch.setattr(streaming.websockets, 'connect', connector)
        sock = await streaming.process_audio_modulate(lambda _s: None, 16000, 'en')
        sock._recv_task.cancel()
        sock._send_task.cancel()
        await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)

    before = _histogram_count(pse.OMI_STT_PROVIDER_CONNECT_SECONDS, 'modulate')
    asyncio.run(run(connect))
    assert _histogram_count(pse.OMI_STT_PROVIDER_CONNECT_SECONDS, 'modulate') == before + 1

    with pytest.raises(RuntimeError):
        asyncio.run(run(rejected))
    assert 'STT provider connect rejected provider=modulate status=503 request_id=edge-503-1' in caplog.text
    assert 'test-key' not in caplog.text


# --- real Soniox socket against a real websockets server ---------------------------------------------


def test_soniox_vendor_close_frame_and_handshake_request_id_over_a_real_websocket(caplog, monkeypatch):
    monkeypatch.setattr(soniox, 'resilient_reconnect_enabled', lambda: True)
    caplog.set_level(logging.INFO)

    async def run():
        async def provider(ws):
            await ws.close(code=1011, reason='private_provider_body')

        async with websockets.serve(provider, '127.0.0.1', 0, extra_headers={'X-Request-Id': 'snx-42'}) as server:
            port = server.sockets[0].getsockname()[1]
            async with websockets.connect(f'ws://127.0.0.1:{port}') as ws:
                socket = soniox.SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
                try:
                    await asyncio.wait_for(socket._recv_task, timeout=3)
                finally:
                    socket._send_task.cancel()
                    await asyncio.gather(socket._send_task, return_exceptions=True)
                await socket.drain_and_close()  # Teardown after the vendor close counts nothing new.

    delta = _Delta('soniox', VENDOR, '1011')
    asyncio.run(run())
    assert delta.value == 1
    assert 'closer=vendor code_class=1011 received_code=1011' in caplog.text
    assert 'request_id=snx-42 request_id_header=x-request-id' in caplog.text
    assert 'private_provider_body' not in caplog.text


def test_soniox_keepalive_timeout_is_ours():
    async def run():
        class Provider:
            close_rcvd = None
            close_sent = None

            async def send(self, data):
                await asyncio.Event().wait()

            def __aiter__(self):
                async def receive():
                    raise ConnectionClosedError(None, Close(1011, 'keepalive ping timeout'))
                    yield ''

                return receive()

        socket = soniox.SafeSonioxSocket(Provider(), lambda _: None, asyncio.get_running_loop())
        try:
            await asyncio.wait_for(socket._recv_task, timeout=3)
        finally:
            socket._send_task.cancel()
            await asyncio.gather(socket._send_task, return_exceptions=True)

    delta = _Delta('soniox', US_TIMEOUT, '1011')
    asyncio.run(run())
    assert delta.value == 1


def test_soniox_planned_idle_close_is_our_timeout_not_a_vendor_drop():
    async def run():
        ws = _ScriptedWebSocket([])
        socket = soniox.SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
        socket._planned_close = True
        note_stream_close_intent(socket, US_TIMEOUT)
        socket._mark_dead('ws recv closed: x', transport_error=ConnectionClosedError(Close(1000, ''), None))
        await socket.drain_and_close()

    delta = _Delta('soniox', US_TIMEOUT, '1000')
    asyncio.run(run())
    assert delta.value == 1
