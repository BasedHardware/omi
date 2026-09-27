"""Regression (2026-09-18 prod incident): a Deepgram account refusal is terminal,
typed, and single-shot — never a retried 'start() returned False'.

What prod showed (backend-listen, ~4.2k errors/30m for 12+h):

    ERROR:utils.stt.streaming:Deepgram connection start() returned False — connection not established
    ERROR:deepgram...abstract_sync_websocket:WebSocketException in AbstractSyncWebSocketClient.start: server rejected WebSocket connection: HTTP 402
    ERROR:deepgram...abstract_sync_websocket:WebSocketException in ListenWebSocketClient.start: server rejected WebSocket connection: HTTP 402
    ERROR:utils.stt.streaming:Deepgram start() returned False on all 3 attempts — giving up

Root cause chain, pinned by these tests:

1. ``_deepgram_options`` passed ``termination_exception_connect="true"`` (a
   string). The SDK checks it twice per connect with two different semantics:
   the shared websocket base class tests truthiness (raises, first ERROR line)
   while the ``ListenWebSocketClient.start`` wrapper re-tests with ``is True``
   (identity), so the string fails there and the exception is swallowed back
   into ``start() is False`` (second ERROR line).
2. ``connect_to_deepgram`` mapped a ``False`` start to ``None``, and
   ``connect_to_deepgram_with_backoff`` retried ``None`` three times — for a
   deterministic HTTP 401/402/403 answer no retry can change (last line).
3. The fallback helper then bucketed whatever emerged into the generic
   ``provider_5xx`` reason, so stt_selection telemetry could not name 402.

The fix: the boolean option restores the SDK's typed raise; terminal
account-state rejections surface as ``DeepgramConnectionRejection`` and skip
the retry ladder; the fallback helper records ``reason='auth'``; a session on
a language Modulate cannot serve still fails cleanly after one attempt.
"""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets.exceptions
from websockets.datastructures import Headers

import deepgram.clients.common.v1.abstract_sync_websocket as dg_abstract_socket
from deepgram import DeepgramClient, DeepgramClientOptions

from routers.listen import receiver as receiver_mod
from routers.listen.receiver import ListenReceiver
from utils.stt import provider_resilience, streaming
from utils.stt.streaming import (
    STTService,
    DeepgramConnectionRejection,
    _TERMINAL_REJECTION_STATUSES,
    _deepgram_options,
    connect_to_deepgram,
    connect_to_deepgram_with_backoff,
    deepgram_rejection_status,
    process_audio_dg,
)


class _FakeHandshakeResponse:
    """The slice of the websockets handshake response the classifier reads."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.headers = Headers()


def _invalid_status(status_code: int) -> websockets.exceptions.InvalidStatus:
    return websockets.exceptions.InvalidStatus(_FakeHandshakeResponse(status_code))


def _reject_upgrade(url: str, **kwargs: Any) -> None:
    raise _invalid_status(402)


def _refusal(status_code: int = 402) -> DeepgramConnectionRejection:
    return DeepgramConnectionRejection(f'Could not open socket: HTTP {status_code}', status_code=status_code)


class _LiveSocket:
    """Duck-typed serving socket: alive and staying that way."""

    is_connection_dead = False
    death_reason = None


class _RejectedSocket:
    """Velma's over-quota shape: the upgrade succeeds, then the stream is refused."""

    def __init__(self) -> None:
        self.death_reason = 'modulate error: Monthly usage limit reached.'
        self.finished = False

    @property
    def is_connection_dead(self) -> bool:
        return True

    def finish(self) -> None:
        self.finished = True


def _deepgram_receiver() -> SimpleNamespace:
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=STTService.deepgram,
        stt_language='en',
        stt_model='nova-3',
        vocabulary=[],
    )
    return SimpleNamespace(host=host)


def _open_breaker() -> MagicMock:
    breaker = MagicMock()
    breaker.allow_request.return_value = True
    return breaker


# ---------------------------------------------------------------------------
# The SDK contract: truthiness vs identity on the same option (deepgram-sdk 4.8.1)
# ---------------------------------------------------------------------------


def _sdk_connection(option_value: Any) -> Any:
    options = DeepgramClientOptions(options={'termination_exception_connect': option_value})
    return DeepgramClient('test-key', options).listen.websocket.v('1')


def test_the_real_sdk_wrapper_swallows_a_rejection_for_the_string_option():
    """Documents the prod bug at its source: 'true' is truthy but not ``is True``.

    With the string, the base class re-raises (truthy check) but
    ``ListenWebSocketClient.start`` swallows the same exception back into
    ``start() is False`` — the exact shape that produced the twin SDK ERROR
    lines plus 'start returned False' in prod.
    """
    conn = _sdk_connection('true')
    with patch.object(dg_abstract_socket, 'connect', side_effect=_reject_upgrade):
        assert conn.start({'model': 'nova-3'}) is False


def test_the_real_sdk_wrapper_raises_for_the_boolean_option():
    """With ``True`` the exception propagates out of the serving wrapper typed."""
    conn = _sdk_connection(True)
    with patch.object(dg_abstract_socket, 'connect', side_effect=_reject_upgrade):
        with pytest.raises(websockets.exceptions.InvalidStatus, match='HTTP 402'):
            conn.start({'model': 'nova-3'})


def test_the_options_pin_carries_the_identity_checked_boolean_for_hosted():
    opts = _deepgram_options('https://api.deepgram.com')
    # Identity, not equality: the SDK wrapper re-tests with `is True`, so a
    # truthy stand-in (1, 'true') would reintroduce the swallow silently.
    assert opts.options['termination_exception_connect'] is True
    assert opts.url == 'https://api.deepgram.com'
    assert 'keepalive' not in opts.options


def test_the_options_pin_carries_the_identity_checked_boolean_for_self_hosted():
    opts = _deepgram_options('https://dg.selfhosted.test')
    assert opts.options['termination_exception_connect'] is True
    assert opts.url == 'https://dg.selfhosted.test'
    assert 'keepalive' not in opts.options


def test_the_managed_hosted_client_carries_the_terminal_option(monkeypatch):
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'managed-key')
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', False)
    client = streaming._build_managed_deepgram_client()
    assert client is not None
    assert client._config.options['termination_exception_connect'] is True


def test_the_self_hosted_client_carries_the_terminal_option(monkeypatch):
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', True)
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'managed-key')
    monkeypatch.setenv('DEEPGRAM_SELF_HOSTED_URL', 'https://dg.selfhosted.test')
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', False)
    client = streaming._build_managed_deepgram_client()
    assert client is not None
    assert client._config.options['termination_exception_connect'] is True


def test_the_byok_request_client_carries_the_terminal_option(monkeypatch):
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)
    monkeypatch.setattr(streaming, 'deepgram', None)
    monkeypatch.setattr(streaming, '_managed_deepgram_ready', False)
    monkeypatch.setattr(streaming, 'get_byok_key', lambda _provider: 'byok-key')
    client = streaming._deepgram_client_for_request()
    assert client._config.api_key == 'byok-key'
    assert client._config.options['termination_exception_connect'] is True


# ---------------------------------------------------------------------------
# The rejection classifier
# ---------------------------------------------------------------------------


def test_an_invalid_key_answer_is_terminal():
    assert deepgram_rejection_status(_invalid_status(401)) == 401


def test_a_billing_answer_is_terminal():
    assert deepgram_rejection_status(_invalid_status(402)) == 402


def test_a_forbidden_answer_is_terminal():
    assert deepgram_rejection_status(_invalid_status(403)) == 403


def test_the_legacy_invalid_status_code_shape_is_terminal():
    """Older websockets transports raise ``InvalidStatusCode`` with a bare int."""
    assert deepgram_rejection_status(websockets.exceptions.InvalidStatusCode(402, Headers())) == 402


def test_a_rate_limit_is_not_terminal():
    """429 can clear between attempts — it must keep the retry budget."""
    assert deepgram_rejection_status(_invalid_status(429)) is None


def test_a_server_error_is_not_terminal():
    assert deepgram_rejection_status(_invalid_status(503)) is None


def test_a_timeout_is_not_terminal():
    assert deepgram_rejection_status(asyncio.TimeoutError()) is None


def test_a_plain_websocket_failure_is_not_terminal():
    assert deepgram_rejection_status(websockets.exceptions.WebSocketException('handshake timed out')) is None


def test_a_missing_status_attribute_is_never_terminal():
    assert deepgram_rejection_status(SimpleNamespace()) is None


def test_a_non_integer_status_is_never_terminal():
    assert deepgram_rejection_status(SimpleNamespace(response=SimpleNamespace(status_code='402'))) is None


def test_the_typed_error_itself_reclassifies_to_its_status():
    """Layered handlers can ask the typed error for its status without the chain."""
    assert deepgram_rejection_status(_refusal(402)) == 402


def test_the_terminal_status_set_is_exactly_the_account_state_trio():
    """Family-membership pin: widening (e.g. adding 429) would end transient recovery."""
    assert _TERMINAL_REJECTION_STATUSES == frozenset({401, 402, 403})


def test_the_typed_rejection_is_an_error_callers_already_handle():
    """Every existing ``except Exception`` seam keeps working — no new crash path."""
    assert issubclass(DeepgramConnectionRejection, RuntimeError)
    assert isinstance(_refusal(), Exception)


# ---------------------------------------------------------------------------
# connect_to_deepgram: the typed wrap at the catch boundary
# ---------------------------------------------------------------------------


def _client_raising(exception: BaseException) -> MagicMock:
    client = MagicMock()
    client.listen.websocket.v.return_value.start.side_effect = exception
    return client


def test_a_refused_upgrade_raises_typed_with_status_and_cause():
    boom = _invalid_status(402)
    with patch.object(streaming, '_deepgram_client_for_request', return_value=_client_raising(boom)):
        with pytest.raises(DeepgramConnectionRejection) as caught:
            connect_to_deepgram(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-3',
            )
    assert caught.value.status_code == 402
    assert caught.value.__cause__ is boom
    assert 'HTTP 402' in str(caught.value)


def test_a_transient_handshake_failure_keeps_the_generic_wrap():
    boom = websockets.exceptions.WebSocketException('connection timed out')
    with patch.object(streaming, '_deepgram_client_for_request', return_value=_client_raising(boom)):
        with pytest.raises(Exception, match='Could not open socket: WebSocketException'):
            connect_to_deepgram(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-3',
            )


def test_a_refusal_no_longer_logs_the_false_start_shape(caplog):
    """The prod signature 'start() returned False' must not exist for a 402."""
    with caplog.at_level(logging.INFO, logger='utils.stt.streaming'):
        with patch.object(
            streaming, '_deepgram_client_for_request', return_value=_client_raising(_invalid_status(402))
        ):
            with pytest.raises(DeepgramConnectionRejection):
                connect_to_deepgram(
                    on_message=MagicMock(),
                    on_error=MagicMock(),
                    language='en',
                    sample_rate=16000,
                    channels=1,
                    model='nova-3',
                )
    assert not [r for r in caplog.records if 'returned False' in r.getMessage()]


# ---------------------------------------------------------------------------
# connect_to_deepgram_with_backoff: the retry budget
# ---------------------------------------------------------------------------


async def _backoff(connect_side_effect: Any, **kwargs: Any):
    """Drive the real backoff loop; return (result, error, connect mock, sleeper)."""
    with (
        patch.object(streaming, 'connect_to_deepgram', side_effect=connect_side_effect) as connect,
        patch('utils.stt.streaming.asyncio.sleep', new=AsyncMock()) as sleeper,
    ):
        result, error = None, None
        try:
            result = await connect_to_deepgram_with_backoff(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-3',
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — the test asserts on the type it receives
            error = exc
    return result, error, connect, sleeper


async def test_a_terminal_rejection_raises_after_one_attempt_without_backoff():
    _, error, connect, sleeper = await _backoff(_refusal(402))
    assert isinstance(error, DeepgramConnectionRejection)
    assert error.status_code == 402
    assert connect.call_count == 1
    sleeper.assert_not_awaited()


async def test_a_terminal_rejection_is_logged_once(caplog):
    """Prod tripled every refusal into 3+ lines per session; one line is enough."""
    with caplog.at_level(logging.ERROR, logger='utils.stt.streaming'):
        _, error, connect, sleeper = await _backoff(_refusal(402))
    assert isinstance(error, DeepgramConnectionRejection)
    assert connect.call_count == 1 and sleeper.await_count == 0
    terminal_lines = [r for r in caplog.records if 'rejected terminally' in r.getMessage()]
    assert len(terminal_lines) == 1
    assert '402' in terminal_lines[0].getMessage()


async def test_retryable_none_results_still_exhaust_to_none():
    """The retryable half of the contract is untouched: None still means retry."""
    result, error, connect, sleeper = await _backoff([None, None, None])
    assert result is None and error is None
    assert connect.call_count == 3
    assert sleeper.await_count == 2


async def test_a_transient_failure_still_walks_the_full_ladder():
    _, error, connect, sleeper = await _backoff([Exception('dg down'), Exception('dg down'), Exception('dg down')])
    assert isinstance(error, Exception)
    assert 'dg down' in str(error)
    assert connect.call_count == 3
    assert sleeper.await_count == 2


async def test_a_transient_failure_still_recovers_on_a_later_attempt():
    result, error, connect, _ = await _backoff([None, None, 'healthy-conn'])
    assert result == 'healthy-conn' and error is None
    assert connect.call_count == 3


async def test_a_refusal_between_transient_failures_skips_the_remaining_retries():
    _, error, connect, sleeper = await _backoff([Exception('dg down'), _refusal(402)])
    assert isinstance(error, DeepgramConnectionRejection)
    assert connect.call_count == 2
    assert sleeper.await_count == 1


async def test_a_session_end_flip_still_takes_precedence_over_the_next_attempt():
    """The pre-attempt is_active guard is untouched: an ended session exits quietly.

    Pins that the typed arm did not move the session-end check out of the loop
    head — a transient failure followed by a session end still returns None.
    """
    active = [True]

    async def flip_during_backoff(duration):
        active[0] = False

    with (
        patch.object(streaming, 'connect_to_deepgram', side_effect=Exception('dg down')) as connect,
        patch('utils.stt.streaming.asyncio.sleep', side_effect=flip_during_backoff),
    ):
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-3',
            retries=3,
            is_active=lambda: active[0],
        )
    assert result is None
    assert connect.call_count == 1


async def test_a_refusal_already_paid_for_outlives_a_session_end_flag():
    """A refusal observed on a completed attempt surfaces even if the session
    just ended — ops must see the true cause, not a silent None."""
    active = [True]
    with (
        patch.object(streaming, 'connect_to_deepgram', side_effect=_refusal(402)) as connect,
        patch('utils.stt.streaming.asyncio.sleep', new=AsyncMock()),
    ):
        with pytest.raises(DeepgramConnectionRejection):
            await connect_to_deepgram_with_backoff(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-3',
                retries=3,
                is_active=lambda: active[0],
            )
    assert connect.call_count == 1


async def test_the_rejection_survives_the_blocking_offload():
    """The typed class must cross the real run_blocking executor seam intact."""
    with patch.object(streaming, 'connect_to_deepgram', side_effect=_refusal(402)):
        with pytest.raises(DeepgramConnectionRejection):
            await connect_to_deepgram_with_backoff(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-3',
            )


async def test_process_audio_dg_propagates_the_typed_rejection_rather_than_none():
    with patch.object(streaming, 'connect_to_deepgram_with_backoff', side_effect=_refusal(402)):
        with pytest.raises(DeepgramConnectionRejection):
            await process_audio_dg(stream_transcript=MagicMock(), language='en', sample_rate=16000, channels=1)


# ---------------------------------------------------------------------------
# connect_stt_socket_with_fallback: the typed arm, the auth reason, the circuit
# ---------------------------------------------------------------------------


async def test_the_fallback_chain_names_an_account_refusal_as_auth():
    modulate_socket = _LiveSocket()
    breaker = _open_breaker()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', breaker),
        patch.object(streaming, 'record_fallback') as record,
    ):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(side_effect=_refusal(402)),
            connect_modulate=AsyncMock(return_value=modulate_socket),
        )
    assert socket is modulate_socket
    assert service == STTService.modulate
    assert record.call_args.kwargs['reason'] == 'auth'
    assert record.call_args.kwargs['outcome'] == 'recovered'
    breaker.record_failure.assert_called_once_with()


async def test_an_exhausted_chain_still_counts_the_refusal_on_the_circuit():
    """No fallback legs: the helper's contract raise surfaces and the circuit still counts the refusal."""
    breaker = _open_breaker()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', breaker),
        patch.object(streaming, 'record_fallback') as record,
        pytest.raises(RuntimeError, match='No STT fallback provider was configured'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(side_effect=_refusal(402)),
        )
    breaker.record_failure.assert_called_once_with()
    record.assert_not_called()  # the telemetry loop never ran — no legs were configured


async def test_the_next_leg_telemetry_carries_the_auth_reason_forward():
    """The leg AFTER the refusal reports why the chain is on it — not 5xx."""
    parakeet_socket = _LiveSocket()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', _open_breaker()),
        patch.object(streaming, 'record_fallback') as record,
    ):
        _, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(side_effect=_refusal(402)),
            connect_modulate=AsyncMock(side_effect=RuntimeError('modulate exploded')),
            connect_parakeet=AsyncMock(return_value=parakeet_socket),
        )
    assert service == STTService.parakeet
    modulate_leg, parakeet_leg = [call.kwargs for call in record.call_args_list]
    assert (modulate_leg['from_mode'], modulate_leg['to_mode'], modulate_leg['reason'], modulate_leg['outcome']) == (
        'deepgram',
        'modulate',
        'auth',
        'exhausted',
    )
    assert (parakeet_leg['from_mode'], parakeet_leg['to_mode'], parakeet_leg['reason'], parakeet_leg['outcome']) == (
        'modulate',
        'parakeet',
        'provider_5xx',
        'recovered',
    )


async def test_a_deployment_without_modulate_walks_straight_to_parakeet_on_a_refusal():
    """No Modulate leg (e.g. a `multi` language) must not strand the refusal."""
    parakeet_socket = _LiveSocket()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', _open_breaker()),
        patch.object(streaming, 'record_fallback'),
    ):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(side_effect=_refusal(402)),
            connect_modulate=None,
            connect_parakeet=AsyncMock(return_value=parakeet_socket),
        )
    assert socket is parakeet_socket
    assert service == STTService.parakeet


async def test_a_typed_rejection_opens_the_deepgram_circuit_at_threshold():
    clock = [100.0]
    breaker = provider_resilience.ProviderCircuitBreaker(
        failure_threshold=1, cooldown_seconds=30.0, clock=lambda: clock[0]
    )
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', breaker),
        patch.object(streaming, 'record_fallback'),
        pytest.raises(RuntimeError, match='No STT fallback provider was configured'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(side_effect=_refusal(402)),
        )
    assert breaker.state == 'open'
    assert breaker.allow_request() is False


async def test_the_open_circuit_shields_the_account_from_a_second_refusal():
    """A dead account gets a 30s breather instead of a connect per session."""
    clock = [100.0]
    breaker = provider_resilience.ProviderCircuitBreaker(
        failure_threshold=1, cooldown_seconds=30.0, clock=lambda: clock[0]
    )
    modulate_socket = _LiveSocket()
    connect_primary = AsyncMock(side_effect=_refusal(402))
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', breaker),
        patch.object(streaming, 'record_fallback') as record,
    ):
        with pytest.raises(RuntimeError, match='No STT fallback provider was configured'):
            await streaming.connect_stt_socket_with_fallback(
                primary_service=STTService.deepgram, connect_primary=connect_primary
            )
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=connect_primary,
            connect_modulate=AsyncMock(return_value=modulate_socket),
        )
    connect_primary.assert_awaited_once()  # the shield, not the refusal, stopped attempt 2
    assert socket is modulate_socket
    assert service == STTService.modulate
    assert record.call_args.kwargs['reason'] == 'circuit_open'


async def test_the_circuit_recovers_when_a_later_session_connects_healthy():
    """The breather ends on time: a healthy connect closes the breaker again."""
    clock = [100.0]
    breaker = provider_resilience.ProviderCircuitBreaker(
        failure_threshold=1, cooldown_seconds=30.0, clock=lambda: clock[0]
    )
    dg_socket = _LiveSocket()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', breaker),
        patch.object(streaming, 'record_fallback'),
    ):
        with pytest.raises(RuntimeError, match='No STT fallback provider was configured'):
            await streaming.connect_stt_socket_with_fallback(
                primary_service=STTService.deepgram, connect_primary=AsyncMock(side_effect=_refusal(402))
            )
        clock[0] += 31.0  # cooldown elapsed → half-open probe
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(return_value=dg_socket),
        )
    assert socket is dg_socket
    assert service == STTService.deepgram
    assert breaker.state == 'closed'


async def test_a_refusal_never_opens_the_parakeet_circuit():
    """Circuit independence survives the new typed arm."""
    deepgram_breaker = _open_breaker()
    parakeet_breaker = _open_breaker()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(streaming, '_deepgram_circuit', deepgram_breaker),
        patch.object(streaming, '_parakeet_circuit', parakeet_breaker),
        patch.object(streaming, 'record_fallback'),
    ):
        await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.deepgram,
            connect_primary=AsyncMock(side_effect=_refusal(402)),
            connect_modulate=AsyncMock(return_value=_LiveSocket()),
        )
    parakeet_breaker.allow_request.assert_not_called()
    parakeet_breaker.record_failure.assert_not_called()
    parakeet_breaker.record_success.assert_not_called()


# ---------------------------------------------------------------------------
# The receiver path
# ---------------------------------------------------------------------------


async def test_a_refusal_on_a_non_modulate_language_terminates_after_one_attempt():
    """The short-circuit branch has no chain to walk: one attempt, typed raise."""
    receiver = _deepgram_receiver()
    with (
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(side_effect=_refusal(402))) as dg,
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock()) as modulate,
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=False),
        pytest.raises(DeepgramConnectionRejection),
    ):
        await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)
    dg.assert_awaited_once()
    modulate.assert_not_awaited()


async def test_a_refusal_on_a_modulate_language_session_still_reaches_parakeet():
    """The typed raise enters the same chain the None path used to enter."""
    receiver = _deepgram_receiver()
    parakeet_socket = _LiveSocket()
    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_dg', new=AsyncMock(side_effect=_refusal(402))),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=_RejectedSocket())),
        patch.object(receiver_mod, 'process_audio_parakeet', new=AsyncMock(return_value=parakeet_socket)),
        patch.object(receiver_mod, 'modulate_is_configured_fallback', return_value=True),
        patch.object(receiver_mod, 'parakeet_is_configured_fallback', return_value=True),
        patch.object(streaming, '_deepgram_circuit', _open_breaker()),
        patch.object(streaming, 'record_fallback'),
    ):
        socket = await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)
    assert socket is parakeet_socket
    assert receiver.host.stt_service == STTService.parakeet
    assert receiver.host.stt_model == 'parakeet'
