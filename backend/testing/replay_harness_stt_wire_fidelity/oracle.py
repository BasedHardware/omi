"""Loopback-only structural oracle for the Parakeet live-STT wire contract.

This is deliberately not a provider conformance suite.  It drives the real
backend WebSocket client and receive loop against a controlled local upstream,
then emits only bounded protocol evidence: path shape, close-code class,
ordering, schema keys, and terminal-state outcomes.  It never records PCM,
transcript text, provider bodies, IDs, headers, or credentials.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import AsyncMock, patch

import websockets

from routers.listen import receiver as listen_receiver_module
from routers.listen.receiver import ListenReceiver
from utils.stt.streaming import STTService, ParakeetWebSocketSocket, process_audio_parakeet


class OracleFailure(AssertionError):
    """A bounded protocol assertion failed."""


@dataclass
class _LoopbackParakeet:
    """A controlled local upstream that retains only safe protocol evidence."""

    scenario: str
    endpoint_path: str = "/v3/stream"
    events: list[str] = field(default_factory=list)
    connections: int = 0
    _server: Any = None
    _handler_failure: BaseException | None = None

    @property
    def api_url(self) -> str:
        if self._server is None:
            raise RuntimeError("loopback upstream has not started")
        port = int(self._server.sockets[0].getsockname()[1])
        return f"http://127.0.0.1:{port}"

    async def __aenter__(self) -> "_LoopbackParakeet":
        self._server = await websockets.serve(self._handle, "127.0.0.1", 0, max_size=1024 * 1024)
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._handler_failure is not None:
            raise self._handler_failure

    async def _handle(self, websocket: Any) -> None:
        try:
            self.connections += 1
            if websocket.path.split("?", 1)[0] != self.endpoint_path:
                raise OracleFailure("client did not use the Parakeet stream endpoint")
            self.events.append("connected")

            if self.scenario == "capacity":
                await websocket.close(code=1013, reason="capacity_full")
                self.events.append("closed_1013")
                return
            if self.scenario == "initialization":
                await websocket.close(code=1011, reason="stream_initialization_failed")
                self.events.append("closed_1011")
                return

            await websocket.send(json.dumps({"type": "ready"}))
            self.events.append("ready")
            if self.scenario == "clean_close":
                await websocket.close(code=1000, reason="complete")
                self.events.append("closed_clean")
                return

            frame_index = 0
            async for message in websocket:
                if isinstance(message, bytes):
                    frame_index += 1
                    self.events.append(f"pcm_{frame_index}")
                    await websocket.send(
                        json.dumps(
                            {
                                "text": "synthetic",
                                "start": float(frame_index),
                                "end": float(frame_index) + 0.25,
                                "speaker": "synthetic",
                            }
                        )
                    )
                    self.events.append(f"segment_{frame_index}")
                    continue
                if message == "finalize":
                    self.events.append("finalize")
                    await websocket.send(
                        json.dumps({"text": "synthetic", "start": 3.0, "end": 3.25, "speaker": "synthetic"})
                    )
                    self.events.append("finalize_tail")
                    return
                raise OracleFailure("client sent an unsupported frame class")
        except BaseException as error:
            self._handler_failure = error
            raise


@contextmanager
def _configured_parakeet_endpoint(url: str) -> Iterator[None]:
    previous = os.environ.get("HOSTED_PARAKEET_API_URL")
    os.environ["HOSTED_PARAKEET_API_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HOSTED_PARAKEET_API_URL", None)
        else:
            os.environ["HOSTED_PARAKEET_API_URL"] = previous


@contextmanager
def _bounded_evidence_logging() -> Iterator[None]:
    """Keep the executable oracle's output within its evidence allow-list."""

    loggers = [logging.getLogger("utils.stt.streaming"), logging.getLogger("utils.observability.fallback")]
    previous_levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        for logger, previous_level in zip(loggers, previous_levels):
            logger.setLevel(previous_level)


class _FallbackSocket:
    """Controlled local fallback endpoint; no provider connection is attempted."""

    def send(self, _audio: bytes) -> bool:
        return True

    def finish(self) -> None:
        return None

    def finalize(self) -> None:
        return None

    @property
    def is_connection_dead(self) -> bool:
        return False

    @property
    def death_reason(self) -> None:
        return None


class _ClientSocket:
    """Local listen-client stand-in that retains only the safe public envelope."""

    def __init__(self) -> None:
        self.statuses: list[dict[str, Any]] = []
        self.closes: list[tuple[int, str | None]] = []

    async def send_json(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise OracleFailure("terminal status did not use an object envelope")
        self.statuses.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closes.append((code, reason))


def _receiver_host(client: _ClientSocket, *, stt_service: STTService = STTService.parakeet) -> Any:
    return SimpleNamespace(
        stt_service=stt_service,
        stt_language="en",
        stt_model="parakeet",
        vocabulary=[],
        use_custom_stt=False,
        is_multi_channel=False,
        session_id="synthetic-session",
        request=SimpleNamespace(
            vad_gate_override=None,
            sample_rate=16000,
            uid="synthetic-uid",
            websocket=client,
        ),
        state=SimpleNamespace(
            active=True,
            close_code=0,
            stt_terminal_failure=False,
            live_transcription_attempt=None,
        ),
        transcripts=SimpleNamespace(enqueue=lambda _segments: None),
        client_device_context=SimpleNamespace(platform="test"),
        spawn=lambda _task, **_kwargs: None,
        wait=lambda _seconds: asyncio.sleep(0, result=True),
    )


def _assert_terminal_failure(client: _ClientSocket) -> tuple[str, ...]:
    if len(client.statuses) != 1 or len(client.closes) != 1:
        raise OracleFailure("terminal failure did not emit exactly one status and one close")
    status = client.statuses[0]
    if status.get("type") != "service_status" or status.get("status") != "stt_failed":
        raise OracleFailure("terminal failure did not use the bounded STT status")
    if status.get("reason") not in {"initialization_failed", "connection_lost"}:
        raise OracleFailure("terminal failure did not use a documented reason")
    if client.closes != [(1011, "transcription_service_unavailable")]:
        raise OracleFailure("terminal failure did not use the documented client close")
    return tuple(sorted(status))


async def _wait_for_dead(socket: ParakeetWebSocketSocket) -> None:
    for _ in range(20):
        if socket.is_connection_dead:
            return
        await asyncio.sleep(0.05)
    raise OracleFailure("clean provider close did not latch terminal state")


async def _normal_wire_scenario() -> dict[str, Any]:
    callback_order: list[int] = []
    callback_key_sets: list[tuple[str, ...]] = []

    def receive(segments: list[dict[str, Any]]) -> None:
        for segment in segments:
            keys = tuple(sorted(segment))
            if keys != ("end", "speaker", "start", "text"):
                raise OracleFailure("provider segment schema changed unexpectedly")
            callback_key_sets.append(keys)
            callback_order.append(int(segment["start"]))

    async with _LoopbackParakeet("normal") as upstream:
        with _configured_parakeet_endpoint(upstream.api_url):
            socket = await process_audio_parakeet(receive, language="en", sample_rate=16000, channels=1)
            if socket is None:
                raise OracleFailure("production Parakeet client did not construct a socket")
            if not socket.send(bytes(32)) or not socket.send(bytes(64)):
                raise OracleFailure("production Parakeet client rejected synthetic PCM")
            socket.finalize()
            await asyncio.wait_for(socket.drain_and_close(), timeout=7)

        expected_events = [
            "connected",
            "ready",
            "pcm_1",
            "segment_1",
            "pcm_2",
            "segment_2",
            "finalize",
            "finalize_tail",
        ]
        if upstream.events != expected_events:
            raise OracleFailure("ready/frame/finalize ordering changed")
        if callback_order != [1, 2, 3]:
            raise OracleFailure("receiver did not preserve segment and finalize-tail order")
        if upstream.connections != 1:
            raise OracleFailure("normal stream made an unexpected connection attempt")

        return {
            "endpoint_path": upstream.endpoint_path,
            "event_order": upstream.events,
            "callback_schema_keys": sorted(set(callback_key_sets)),
            "callback_order": callback_order,
            "connection_attempts": upstream.connections,
        }


async def _capacity_fallback_scenario() -> dict[str, Any]:
    client = _ClientSocket()
    host = _receiver_host(client)
    receiver = ListenReceiver(host, [], {})
    fallback = AsyncMock(return_value=_FallbackSocket())

    async with _LoopbackParakeet("capacity") as upstream:
        with _configured_parakeet_endpoint(upstream.api_url), patch.object(
            listen_receiver_module, "process_audio_modulate", fallback
        ):
            result = await receiver._create_stt_socket(lambda _segments: None, 16000)

        if not isinstance(result, _FallbackSocket) or host.stt_service != STTService.modulate:
            raise OracleFailure("capacity rejection did not select the documented fallback")
        fallback.assert_awaited_once()
        if upstream.connections != 1 or upstream.events != ["connected", "closed_1013"]:
            raise OracleFailure("capacity fallback made an unexpected primary connection attempt")

        return {
            "close_code_class": 1013,
            "fallback_attempts": fallback.await_count,
            "connection_attempts": upstream.connections,
        }


async def _initialization_failure_scenario() -> dict[str, Any]:
    client = _ClientSocket()
    host = _receiver_host(client)
    receiver = ListenReceiver(host, [], {})
    unavailable_fallback = AsyncMock(side_effect=RuntimeError("controlled_local_fallback_unavailable"))

    async with _LoopbackParakeet("initialization") as upstream:
        with _configured_parakeet_endpoint(upstream.api_url), patch.object(
            listen_receiver_module, "process_audio_modulate", unavailable_fallback
        ), patch.object(listen_receiver_module, "should_initialize_vad_gate", return_value=False):
            initialized = await receiver.initialize_stt()

        if initialized:
            raise OracleFailure("1011 initialization failure unexpectedly initialized STT")
        unavailable_fallback.assert_awaited_once()
        status_keys = _assert_terminal_failure(client)
        if client.statuses[0].get("reason") != "initialization_failed":
            raise OracleFailure("1011 initialization failure used the wrong terminal reason")
        if upstream.connections != 1 or upstream.events != ["connected", "closed_1011"]:
            raise OracleFailure("1011 initialization failure made an unexpected primary connection attempt")

        return {
            "close_code_class": 1011,
            "fallback_attempts": unavailable_fallback.await_count,
            "status_schema_keys": status_keys,
            "terminal_close_code": client.closes[0][0],
            "connection_attempts": upstream.connections,
        }


async def _clean_close_scenario() -> dict[str, Any]:
    client = _ClientSocket()
    host = _receiver_host(client)
    receiver = ListenReceiver(host, [], {})

    async with _LoopbackParakeet("clean_close") as upstream:
        with _configured_parakeet_endpoint(upstream.api_url):
            socket = await process_audio_parakeet(lambda _segments: None, language="en", sample_rate=16000, channels=1)
            if socket is None:
                raise OracleFailure("production Parakeet client did not construct a socket")
            await _wait_for_dead(socket)
            receiver.stt_socket = socket
            await receiver._monitor_stt_death("parakeet")
            status_keys = _assert_terminal_failure(client)
            await asyncio.wait_for(socket.drain_and_close(), timeout=2)

        if upstream.connections != 1 or upstream.events != ["connected", "ready", "closed_clean"]:
            raise OracleFailure("clean close retried or used an unexpected wire path")

        return {
            "close_code_class": 1000,
            "terminal_latched": socket.is_connection_dead,
            "status_schema_keys": status_keys,
            "terminal_close_code": client.closes[0][0],
            "connection_attempts": upstream.connections,
        }


async def run_oracle() -> dict[str, Any]:
    """Run every bounded local fake-upstream scenario and return safe evidence."""

    with _bounded_evidence_logging():
        return {
            "oracle": "replay-stt-wire-fidelity",
            "scenarios": {
                "ready_frame_finalize": await _normal_wire_scenario(),
                "capacity_fallback": await _capacity_fallback_scenario(),
                "initialization_failure": await _initialization_failure_scenario(),
                "clean_close_terminal": await _clean_close_scenario(),
            },
        }


def main() -> int:
    try:
        evidence = asyncio.run(run_oracle())
    except Exception as error:
        print(f"Replay STT wire-fidelity oracle failed: {type(error).__name__}")
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
