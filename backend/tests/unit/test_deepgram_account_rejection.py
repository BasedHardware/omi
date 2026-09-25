"""Regression: a spent managed Deepgram key must not burn the log budget for days.

2026-09-14..18 the prod backend-listen kept dialing Deepgram cloud with an
exhausted account: every connect surfaced only as SDK ERROR lines
("server rejected WebSocket connection: HTTP 402", ~90k/hour at peak) while
``start()`` just returned ``False`` and the per-connect retry loop multiplied
the attempts. The fallback chain still served the sessions — so users kept
working while the vendor outage generated the log volume of an incident.

Contract under test: an HTTP 402 is account-level evidence. The Deepgram
connect path must classify it (from the only seam that carries the status —
the SDK's ERROR log), refuse to per-connect retry it, hold the provider out
of selection for the account cooldown instead of the 30s connect cooldown,
and let the session walk to the next configured provider.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.listen import receiver as receiver_mod
from routers.listen.receiver import ListenReceiver
from utils.stt import provider_resilience
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.streaming import STTService, ProviderAccountRejection
from utils.stt import streaming


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _soniox_primary_receiver():
    host = SimpleNamespace(
        state=SimpleNamespace(active=True),
        stt_service=STTService.soniox,
        stt_language='en',
        stt_model='soniox',
        vocabulary=[],
    )
    return SimpleNamespace(host=host)


def _live_socket():
    return SimpleNamespace(is_connection_dead=False, death_reason=None)


class _RejectedSocket:
    """Velma shape: upgrade accepted, stream then refused."""

    def __init__(self, reason: str = 'modulate error: Monthly usage limit reached.') -> None:
        self.death_reason = reason
        self.finished = False

    @property
    def is_connection_dead(self) -> bool:
        return True

    def finish(self) -> None:
        self.finished = True


@contextmanager
def _deepgram_sdk_reports_402():
    """Feed the capture handler the way the real SDK reports a spent key.

    The deepgram SDK catches the WebSocket handshake failure internally and
    logs ``WebSocketException ... server rejected WebSocket connection:
    HTTP 402`` at ERROR on its own logger; ``start()`` then returns False.
    """
    logger = logging.getLogger('deepgram')
    record = logging.LogRecord(
        'deepgram',
        logging.ERROR,
        'deepgram.clients.common.v1.abstract_sync_websocket',
        1,
        'WebSocketException in ListenWebSocketClient.start: server rejected WebSocket connection: HTTP 402',
        None,
        None,
    )
    captures = [h for h in logger.handlers if isinstance(h, streaming._DeepgramRejectionCapture)]
    assert captures, 'deepgram logger is missing the rejection capture handler'
    captures[0].emit(record)
    try:
        yield
    finally:
        streaming._last_deepgram_log_rejection[:] = [0.0, '']


def _account_circuit() -> ProviderCircuitBreaker:
    return ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0, account_cooldown_seconds=1800.0)


# --- classification: the SDK log seam is the only carrier of the status ------


def test_an_http_402_in_the_sdk_log_classifies_as_an_account_rejection():
    with _deepgram_sdk_reports_402():
        rejection = streaming._classify_provider_account_rejection(
            'deepgram', streaming._last_deepgram_log_rejection[1]
        )
    assert rejection is not None
    assert rejection.provider == 'deepgram'
    assert '402' in rejection.status


def test_a_plain_5xx_log_text_does_not_classify_as_an_account_rejection():
    assert streaming._classify_provider_account_rejection('deepgram', 'internal server error') is None
    assert streaming._classify_provider_account_rejection('deepgram', 'HTTP 4029 oops') is None


@pytest.mark.anyio
async def test_the_connect_path_raises_account_rejection_instead_of_retrying(monkeypatch):
    monkeypatch.setattr(streaming, '_deepgram_circuit', _account_circuit())
    with _deepgram_sdk_reports_402():
        with pytest.raises(ProviderAccountRejection):
            await streaming.connect_to_deepgram_with_backoff(
                lambda *a, **k: None,
                lambda *a, **k: None,
                'en',
                16000,
                1,
                'nova-3',
            )


@pytest.mark.anyio
async def test_a_stale_or_absent_sdk_error_does_not_block_the_normal_connect():
    """Outside the capture window a healthy connect path stays untouched."""
    client = MagicMock()
    connection = client.listen.websocket.v.return_value
    connection.start.return_value = True
    with patch.object(streaming, '_deepgram_client_for_request', return_value=client):
        socket = await streaming.connect_to_deepgram_with_backoff(
            lambda *a, **k: None, lambda *a, **k: None, 'en', 16000, 1, 'nova-3'
        )
    assert socket is connection


# --- the account cooldown holds the provider out of selection ---------------


@pytest.mark.anyio
async def test_a_402_deepgram_leg_opens_the_account_cooldown_and_serves_from_parakeet(monkeypatch):
    """Velma-primary session: dead Deepgram leg is skipped for 30m, Parakeet serves."""
    monkeypatch.setattr(streaming, '_deepgram_circuit', _account_circuit())
    monkeypatch.setattr(
        streaming, '_modulate_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    )
    monkeypatch.setattr(
        streaming, '_parakeet_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    )
    parakeet_socket = _live_socket()

    socket, service = await streaming.connect_stt_socket_with_fallback(
        primary_service=STTService.modulate,
        connect_primary=AsyncMock(return_value=_RejectedSocket()),
        connect_deepgram=AsyncMock(side_effect=ProviderAccountRejection('deepgram', 'HTTP 402 payment required')),
        connect_parakeet=AsyncMock(return_value=parakeet_socket),
    )

    assert socket is parakeet_socket
    assert service == STTService.parakeet
    assert streaming._deepgram_circuit.state == 'open'
    assert streaming._deepgram_circuit.account_cooldown_seconds_remaining > 1790.0


@pytest.mark.anyio
async def test_a_spent_402_leg_is_not_dialed_again_while_the_account_cooldown_holds(monkeypatch):
    """Second session after the cooldown opened: the dg leg is skipped entirely."""
    monkeypatch.setattr(streaming, '_deepgram_circuit', _account_circuit())
    monkeypatch.setattr(
        streaming, '_soniox_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    )
    monkeypatch.setattr(
        streaming, '_modulate_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    )
    streaming._deepgram_circuit.record_account_rejection()

    dg_leg = AsyncMock(side_effect=AssertionError('402 account must not be re-dialed'))
    modulate_socket = _live_socket()

    socket, service = await streaming.connect_stt_socket_with_fallback(
        primary_service=STTService.soniox,
        connect_primary=AsyncMock(return_value=None),
        connect_deepgram=dg_leg,
        connect_modulate=AsyncMock(return_value=modulate_socket),
    )

    dg_leg.assert_not_awaited()
    assert socket is modulate_socket
    assert service == STTService.modulate


def test_the_account_cooldown_outlasts_the_connect_cooldown_window():
    """At t=60s a 30s connect circuit would re-dial; the account circuit must not."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3, cooldown_seconds=30.0, account_cooldown_seconds=1800.0, clock=lambda: now[0]
    )
    circuit.record_account_rejection()
    now[0] = 60.0
    assert circuit.allow_request() is False
    now[0] = 1799.0
    assert circuit.allow_request() is False
    now[0] = 1800.0
    assert circuit.allow_request() is True


def test_one_half_open_success_closes_the_account_circuit_when_the_bill_is_paid():
    circuit = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0, account_cooldown_seconds=1800.0)
    circuit.record_account_rejection()
    assert circuit.state == 'open'
    circuit.record_success()
    assert circuit.state == 'closed'


def test_a_failed_account_probe_reopens_for_the_full_account_cooldown():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3, cooldown_seconds=30.0, account_cooldown_seconds=1800.0, clock=lambda: now[0]
    )
    circuit.record_account_rejection()
    now[0] = 1800.0
    assert circuit.allow_request() is True  # the single half-open probe
    circuit.record_failure()
    assert circuit.state == 'open'
    assert circuit.account_cooldown_seconds_remaining > 1790.0


def test_the_account_cooldown_fails_validation_when_not_positive():
    with pytest.raises(ValueError):
        ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30.0, account_cooldown_seconds=0)


# --- the session-level chain: the 2026-09 storm path stays user-serving -----


@pytest.mark.anyio
async def test_soniox_primary_with_a_402_deepgram_hop_condemns_it_and_raises_when_exhausted(monkeypatch):
    """The 2026-09 storm path, worst case: soniox miss, velma down, dg 402, no parakeet leg.

    The soniox branch wires only Modulate and Deepgram as fallback legs, so a
    402 on the last leg exhausts the chain and the session still fails — but
    the spent key is condemned for the account cooldown, so the NEXT sessions
    skip Deepgram instead of re-dialing it (the 4-day 90k-errors/hour burn).
    """
    monkeypatch.setattr(streaming, '_deepgram_circuit', _account_circuit())
    monkeypatch.setattr(
        streaming, '_soniox_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    )
    monkeypatch.setattr(
        streaming, '_modulate_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    )
    receiver = _soniox_primary_receiver()

    with (
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05),
        patch.object(receiver_mod, 'process_audio_soniox', new=AsyncMock(return_value=None)),
        patch.object(receiver_mod, 'process_audio_modulate', new=AsyncMock(return_value=None)),
        patch.object(
            receiver_mod,
            'process_audio_dg',
            new=AsyncMock(side_effect=ProviderAccountRejection('deepgram', 'HTTP 402 payment required')),
        ),
        patch.object(streaming, '_deepgram_is_available', return_value=True),
        patch.object(streaming, 'deepgram_fallback_model', return_value='nova-3'),
        patch.object(streaming, 'record_fallback'),
    ):
        # The mocked dg leg raises what the real connect path produces once it
        # classifies the SDK's "HTTP 402" log (covered by the connect tests above).
        with pytest.raises(ProviderAccountRejection):
            await ListenReceiver._create_stt_socket(receiver, MagicMock(), 16000)

    assert streaming._deepgram_circuit.state == 'open'
    assert streaming._deepgram_circuit.account_cooldown_seconds_remaining > 1790.0
