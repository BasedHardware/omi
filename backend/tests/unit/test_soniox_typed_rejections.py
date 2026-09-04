"""Soniox in-stream rejections must keep their type, severity, and fleet effect.

Production evidence (backend-listen, GCP 2026-08-30/31, Loop S sensor):
``ERROR:utils.stt.soniox:Soniox streaming error:`` was the #4 error signature,
~52 events per 30-minute window, three distinct provider shapes sharing one
free-text line: 400 ``invalid_request "No audio received"`` (×42, the VAD gate
starving the socket), 402 ``organization_balance_exhausted`` (×7, the account
cannot serve ANY stream), 413 ``max_duration_reached`` (×3, documented
rotation). The socket laundered all three into one death reason, the terminal
path collapsed them to ``connection_lost``, the 402's ``exhausted`` text
matched neither 'limit' nor 'quota' so fallback telemetry filed it as
``provider_5xx``, and a balance-exhausted provider kept accepting connects —
so mid-session failover quietly moved every session to the next provider and
selection never learned, handing each NEW session straight back to the
provider refusing to serve it.

Failure-Class: FC-typed-failure-collapsed-to-generic — instance fix in the
class canonized by #11487, in the live-STT boundary instead of the proactive
lane. The typed rejection the provider already produced must survive to every
consumer: the log severity (only a 402 is a provider fault worth paging on),
the bounded terminal-failure reason vocabulary, the fallback-reason
classification, the provider label, and — for the one shape that is fleet
evidence (402) — the process-local selection circuit, opened at the failover
seam that would otherwise swallow it.

These tests drive the REAL ``SafeSonioxSocket`` receive loop (synthetic
provider frames), the REAL failover method on ``ListenReceiver``, the REAL
death monitor, and the REAL terminal/send paths from ``utils.stt.live_failure``
— only the process-global circuit opener is patched, at its lazy-import seam.
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.listen import receiver as receiver_mod
from routers.listen.receiver import ListenReceiver
from utils.stt import live_failure
from utils.stt.live_failure import (
    LIVE_STT_FAILURE_CLOSE_CODE,
    live_stt_terminal_reason,
    note_typed_provider_death,
    send_live_stt_audio,
    terminate_live_stt_session,
)
from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome, bounded_provider
from utils.stt.soniox import (
    SONIOX_DEATH_ACCOUNT_STATE,
    SONIOX_DEATH_IDLE_TIMEOUT,
    SONIOX_DEATH_ROTATION,
    SafeSonioxSocket,
    soniox_death_reason,
)
from utils.stt.streaming import STTService, _fallback_failure_reason
from utils.stt.vad_gate import GatedSTTSocket


class FakeWebSocket:
    """Provider WebSocket yielding a scripted inbound frame list."""

    def __init__(self, inbound):
        self._inbound = list(inbound)
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            for msg in self._inbound:
                yield json.dumps(msg)

        return gen()


def _drive_socket(frames, *, wait: float = 0.05):
    """Run a real SafeSonioxSocket over the scripted frames and return it."""

    def run():
        captured = []

        async def main():
            ws = FakeWebSocket(frames)
            sock = SafeSonioxSocket(ws, captured.append, asyncio.get_running_loop())
            await asyncio.sleep(wait)
            return sock

        return asyncio.run(main())

    return run()


def _frame(code, error_type, message):
    return {'error_code': code, 'error_type': error_type, 'error_message': message}


# ---------------------------------------------------------------------------
# soniox_death_reason: bound the provider's own typed frame, degrading safely.
# ---------------------------------------------------------------------------


def test_a_402_balance_exhausted_frame_classifies_as_account_state():
    assert soniox_death_reason(402, 'organization_balance_exhausted') == SONIOX_DEATH_ACCOUNT_STATE


def test_a_400_no_audio_frame_classifies_as_idle_timeout():
    assert soniox_death_reason(400, 'invalid_request') == SONIOX_DEATH_IDLE_TIMEOUT


def test_a_413_max_duration_frame_classifies_as_documented_rotation():
    assert soniox_death_reason(413, 'max_duration_reached') == SONIOX_DEATH_ROTATION


def test_unknown_shapes_degrade_to_connection_lost():
    """A new provider error shape must not grow metric cardinality per message."""
    assert soniox_death_reason(500, 'internal_server_error') == 'connection_lost'
    assert soniox_death_reason('not-a-code', 'whatever') == 'connection_lost'
    assert soniox_death_reason(None, None) == 'connection_lost'


def test_the_error_type_match_tolerates_provider_casing():
    assert soniox_death_reason(402, 'Organization_Balance_Exhausted') == SONIOX_DEATH_ACCOUNT_STATE


# ---------------------------------------------------------------------------
# Severity: only an account-state refusal is a provider fault worth an ERROR.
# ---------------------------------------------------------------------------


def test_a_402_frame_logs_at_error_as_a_provider_fault(caplog):
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = _drive_socket([_frame(402, 'organization_balance_exhausted', 'Organization balance exhausted.')])
    assert sock.is_connection_dead
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'Soniox streaming error:' in r.message]
    assert errors, 'a 402 account-state refusal must stay an ERROR: it is the outage signal'


def test_an_idle_timeout_frame_logs_at_warning_not_error(caplog):
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        _drive_socket([_frame(400, 'invalid_request', 'No audio received')])
    assert [r.levelname for r in caplog.records if 'Soniox' in r.message] == ['WARNING']


def test_a_rotation_frame_logs_at_warning_not_error(caplog):
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        _drive_socket([_frame(413, 'max_duration_reached', 'Maximum duration reached')])
    assert [r.levelname for r in caplog.records if 'Soniox' in r.message] == ['WARNING']


def test_the_raw_provider_frame_stays_on_the_death_latch():
    """The typed reason bounds telemetry; the raw text stays on the latch for logs."""
    sock = _drive_socket([_frame(402, 'organization_balance_exhausted', 'Organization balance exhausted.')])
    assert '402' in (sock.death_reason or '')
    assert 'organization_balance_exhausted' in (sock.death_reason or '')
    assert sock.typed_death_reason == SONIOX_DEATH_ACCOUNT_STATE


def test_a_live_socket_reports_no_typed_reason():
    sock = _drive_socket(
        [{'tokens': [{'text': 'hi', 'is_final': True, 'speaker': 1, 'start_ms': 0, 'duration_ms': 100}]}]
    )
    assert not sock.is_connection_dead
    assert sock.typed_death_reason is None


# ---------------------------------------------------------------------------
# The VAD gate must not erase the typed rejection of the socket it wraps.
# ---------------------------------------------------------------------------


def test_the_vad_gate_proxies_the_typed_death_reason():
    dead = _drive_socket([_frame(402, 'organization_balance_exhausted', 'Organization balance exhausted.')])
    gated = GatedSTTSocket(dead)
    assert gated.typed_death_reason == SONIOX_DEATH_ACCOUNT_STATE
    assert gated.is_connection_dead


def test_the_gate_reports_none_for_an_untyped_wrapped_socket():
    class UntypedSocket:
        is_connection_dead = False
        death_reason = None

    gated = GatedSTTSocket(UntypedSocket())
    assert gated.typed_death_reason is None


# ---------------------------------------------------------------------------
# live_stt_terminal_reason: every terminal funnel reports the provider's type.
# ---------------------------------------------------------------------------


def test_a_terminal_funnel_prefers_the_typed_rejection_over_its_vantage_point():
    sock = SimpleNamespace(typed_death_reason='soniox_rotation')
    assert live_stt_terminal_reason(sock, 'connection_lost') == 'soniox_rotation'


def test_an_unknown_typed_value_is_bounded_to_the_fallback():
    sock = SimpleNamespace(typed_death_reason='not-a-known-reason')
    assert live_stt_terminal_reason(sock, 'send_failed') == 'send_failed'


def test_a_socket_without_a_latch_falls_back_cleanly():
    assert live_stt_terminal_reason(object(), 'connection_lost') == 'connection_lost'


# ---------------------------------------------------------------------------
# Fleet evidence: a 402 refusal must reach the selection circuit.
# ---------------------------------------------------------------------------


def _circuit_recorder():
    calls = []

    def fake_opener(provider, *, reason):
        calls.append((provider, reason))
        return True

    return calls, fake_opener


def test_a_typed_account_state_death_opens_the_selection_circuit():
    calls, opener = _circuit_recorder()
    sock = SimpleNamespace(typed_death_reason=SONIOX_DEATH_ACCOUNT_STATE)
    with patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
        assert note_typed_provider_death(sock, 'soniox') is True
    assert calls == [('soniox', 'soniox_account_state')]


def test_session_scoped_typed_deaths_do_not_bench_the_provider():
    """Idle-timeout and rotation are evidence about one session, not the provider."""
    calls, opener = _circuit_recorder()
    with patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
        assert (
            note_typed_provider_death(SimpleNamespace(typed_death_reason=SONIOX_DEATH_IDLE_TIMEOUT), 'soniox') is False
        )
        assert note_typed_provider_death(SimpleNamespace(typed_death_reason=SONIOX_DEATH_ROTATION), 'soniox') is False
        assert note_typed_provider_death(SimpleNamespace(typed_death_reason=None), 'soniox') is False
    assert calls == []


@pytest.mark.asyncio
async def test_terminate_with_account_state_opens_the_circuit_and_reports_the_typed_reason(monkeypatch):
    websocket = AsyncMock()
    session = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1001, live_transcription_attempt=None)
    failure = TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='soniox', retryable=True)
    recorded = []
    monkeypatch.setattr(live_failure, 'record_live_stt_failure', lambda **labels: recorded.append(labels))
    calls, opener = _circuit_recorder()

    with patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
        sent = await terminate_live_stt_session(
            websocket, session, failure=failure, reason='soniox_account_state', platform='ios'
        )

    assert sent is True
    assert session.stt_terminal_failure is True
    assert session.close_code == LIVE_STT_FAILURE_CLOSE_CODE
    event = websocket.send_json.await_args.args[0]
    assert event['reason'] == 'soniox_account_state'
    assert event['provider'] == 'soniox'
    assert recorded[0]['phase'] == 'connection'
    assert calls == [('soniox', 'soniox_account_state')]


@pytest.mark.asyncio
async def test_terminate_with_a_session_scoped_reason_does_not_open_the_circuit(monkeypatch):
    websocket = AsyncMock()
    session = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1001)
    monkeypatch.setattr(live_failure, 'record_live_stt_failure', lambda **labels: None)
    calls, opener = _circuit_recorder()

    with patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_failure.live_stt_upstream_failure('soniox'),
            reason='soniox_idle_timeout',
            platform='ios',
        )

    assert calls == []
    assert websocket.send_json.await_args.args[0]['reason'] == 'soniox_idle_timeout'


@pytest.mark.asyncio
async def test_the_audio_send_path_terminates_with_the_typed_reason():
    """The send path is often the first observer of death; it must not collapse the type."""

    class DeadTypedSocket:
        is_connection_dead = True
        typed_death_reason = 'soniox_account_state'

        def send(self, _audio):
            raise AssertionError('a dead socket must not be sent to')

    websocket = AsyncMock()
    session = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1001)
    with patch.object(live_failure, 'record_live_stt_failure'):
        sent = await send_live_stt_audio(
            websocket,
            session,
            stt_socket=DeadTypedSocket(),
            audio=b'\x01\x00',
            provider='soniox',
            platform='ios',
        )

    assert sent is False
    assert session.stt_terminal_failure is True
    assert websocket.send_json.await_args.args[0]['reason'] == 'soniox_account_state'


# ---------------------------------------------------------------------------
# The failover seam: a session that SURVIVES a 402 still teaches selection.
# ---------------------------------------------------------------------------


class TypedFakeSocket:
    def __init__(self, *, dead: bool, typed: str | None = None):
        self._dead = dead
        self.typed_death_reason = typed
        self.finished = False
        self.sent = []

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    def send(self, audio: bytes) -> bool:
        if self._dead:
            return False
        self.sent.append(audio)
        return True

    def finish(self) -> None:
        self.finished = True


def _receiver_with_dead_soniox(replacement):
    host = MagicMock()
    host.is_multi_channel = False
    host.use_custom_stt = False
    host.state.active = True
    host.state.stt_terminal_failure = False
    host.language = 'en'
    host.multi_lang_enabled = True
    host.stt_service = STTService.soniox

    receiver = ListenReceiver(host, [], {})
    receiver.stt_socket = TypedFakeSocket(dead=True, typed=SONIOX_DEATH_ACCOUNT_STATE)
    receiver.vad_gate = None
    receiver._stt_rebuild = (lambda _s: None, lambda _s: None, 16000)
    receiver._create_stt_socket = AsyncMock(return_value=replacement)
    return receiver


@pytest.mark.asyncio
async def test_failover_on_a_typed_402_death_opens_the_selection_circuit():
    """The session survives on the next provider; the circuit must still learn.

    This is the invisible-outage seam: without it, a balance-exhausted provider
    accepts every connect, refuses every stream, and selection keeps choosing
    it because each dying session's replacement connects successfully.
    """
    healthy = TypedFakeSocket(dead=False)
    receiver = _receiver_with_dead_soniox(healthy)
    calls, opener = _circuit_recorder()

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.deepgram, 'en', 'dg-nova-3'),
    ), patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
        assert await receiver._failover_stt_socket() is True

    assert receiver.stt_socket is healthy
    assert calls == [('soniox', 'soniox_account_state')]


@pytest.mark.asyncio
async def test_failover_on_an_untyped_death_leaves_the_circuit_alone():
    receiver = _receiver_with_dead_soniox(TypedFakeSocket(dead=False))
    receiver.stt_socket = TypedFakeSocket(dead=True, typed=None)
    calls, opener = _circuit_recorder()

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.deepgram, 'en', 'dg-nova-3'),
    ), patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
        assert await receiver._failover_stt_socket() is True

    assert calls == []


@pytest.mark.asyncio
async def test_the_death_monitor_terminalizes_with_the_typed_reason():
    """The monitor's vantage point is only 'the socket died'; the socket knows why."""

    async def wait(_seconds):
        return True  # end the monitor loop after one poll

    host = SimpleNamespace(
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        request=SimpleNamespace(websocket=object()),
        client_device_context=SimpleNamespace(platform='ios'),
        stt_service=STTService.soniox,
        wait=wait,
    )
    monitor_self = SimpleNamespace(
        host=host,
        stt_socket=SimpleNamespace(is_connection_dead=True, typed_death_reason='soniox_rotation'),
    )
    monitor_self._serving_provider = lambda: ListenReceiver._serving_provider(monitor_self)

    async def _no_failover():
        return False

    monitor_self._failover_stt_socket = _no_failover

    with patch.object(receiver_mod, 'terminate_live_stt_session', new=AsyncMock()) as terminate:
        await ListenReceiver._monitor_stt_death(monitor_self)

    assert terminate.await_args.kwargs['reason'] == 'soniox_rotation'


# ---------------------------------------------------------------------------
# Provider vocabulary and fallback-reason classification.
# ---------------------------------------------------------------------------


def test_live_provider_tokens_survive_bounded_provider():
    """Terminal-failure metrics used to report provider='unknown' for every soniox death."""
    assert bounded_provider('soniox') == 'soniox'
    assert bounded_provider('deepgram_cloud') == 'deepgram_cloud'
    assert bounded_provider('user-supplied-provider') == 'unknown'


def test_soniox_402_text_classifies_as_quota_not_provider_5xx():
    """Fallback telemetry filed a balance-exhausted account as a server fault."""
    assert (
        _fallback_failure_reason(RuntimeError('402 organization_balance_exhausted: Organization balance exhausted.'))
        == 'quota'
    )
    assert _fallback_failure_reason(RuntimeError('Internal server error')) == 'provider_5xx'
