"""Loopback-only structural oracle for the LC3 frame-cadence contract.

The harness intentionally retains no audio, transcript, identifier, header,
credential, provider-body, or payload-hash evidence. It uses test-owned inert
frames only long enough to exercise the production listen decode and STT path.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import platform
import socket
import warnings
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Iterator
from unittest.mock import AsyncMock, patch

warnings.filterwarnings("ignore", message="Couldn't find ffmpeg or avconv", category=RuntimeWarning)

import lc3
import websockets

from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from utils.stt.streaming import STTService
from utils.transcribe_decisions import normalize_codec_frame


class OracleFailure(AssertionError):
    """A bounded LC3 replay contract assertion failed."""


class MutantRejected(OracleFailure):
    """The test-only decoder mutant reached the asserted contract boundary."""


class PrerequisiteFailure(RuntimeError):
    """The locked Linux x86_64 execution path is unavailable."""


class _EgressDenied(OSError):
    """The local default-deny guard blocked a non-loopback attempt."""


class _LoopbackClient:
    """Minimal listen-client surface that exposes no client identity evidence."""

    headers: dict[str, str] = {}

    def __init__(self, frames: tuple[bytes, ...], *, wait_for_provider_close: bool) -> None:
        self._frames = frames
        self._wait_for_provider_close = wait_for_provider_close
        self._index = 0
        self._upstream: Any = None
        self._stt_socket: Any = None
        self.statuses: list[dict[str, Any]] = []
        self.closes: list[tuple[int, str | None]] = []

    def bind_provider(self, upstream: Any, stt_socket: Any) -> None:
        self._upstream = upstream
        self._stt_socket = stt_socket

    async def receive(self) -> dict[str, Any]:
        if self._index < len(self._frames):
            frame = self._frames[self._index]
            self._index += 1
            if self._wait_for_provider_close and self._index == len(self._frames):
                if self._upstream is None or self._stt_socket is None:
                    raise OracleFailure("loopback client was not bound to the STT socket")
                await self._upstream.first_send.wait()
                for _ in range(200):
                    if self._stt_socket.is_connection_dead:
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise OracleFailure("provider close did not latch before the queued fourth frame")
            return {"bytes": frame}
        return {"type": "websocket.disconnect", "code": 1000}

    async def send_json(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise OracleFailure("terminal status was not an object envelope")
        self.statuses.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closes.append((code, reason))


class _LoopbackParakeet:
    """A local fake upstream that records only structural send-size evidence."""

    endpoint_path = "/v3/stream"

    def __init__(self, *, close_after_first_send: bool) -> None:
        self.close_after_first_send = close_after_first_send
        self.connections = 0
        self.audio_sizes: list[int] = []
        self.first_send = asyncio.Event()
        self._server: Any = None
        self._socket: Any = None
        self._handler_failure: BaseException | None = None

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
            if websocket.path.split("?", 1)[0] != self.endpoint_path:
                raise OracleFailure("STT client did not use the Parakeet stream endpoint")
            self.connections += 1
            self._socket = websocket
            await websocket.send(json.dumps({"type": "ready"}))
            async for message in websocket:
                if isinstance(message, bytes):
                    self.audio_sizes.append(len(message))
                    self.first_send.set()
                    if self.close_after_first_send:
                        await websocket.close(code=1011, reason="replay_terminal")
                        return
                    continue
                if message == "finalize":
                    return
                raise OracleFailure("STT client sent an unsupported frame class")
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
def _quiet_logs() -> Iterator[None]:
    """Prevent dependencies from emitting unbounded provider or payload details."""

    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


def _is_loopback_address(address: object) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    try:
        return ipaddress.ip_address(str(host).strip("[]")).is_loopback
    except ValueError:
        return False


@contextmanager
def _loopback_only_egress_guard() -> Iterator[None]:
    """Default-deny TCP egress while the real STT socket is under test."""

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection

    def guarded_connect(sock: socket.socket, address: object) -> Any:
        if not _is_loopback_address(address):
            raise _EgressDenied("replay egress denied")
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object) -> int:
        if not _is_loopback_address(address):
            return -1
        return original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_loopback_address(address):
            raise _EgressDenied("replay egress denied")
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.connect(("198.51.100.1", 9))
            except _EgressDenied:
                pass
            else:
                raise OracleFailure("loopback-only egress guard did not deny a non-loopback connection")
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection


def _static_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_linux_x86_64() -> None:
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise PrerequisiteFailure("requires Linux x86_64 with locked lc3py==1.1.3")


class _ObservedDecoder:
    """Observe output sizes while still calling the real lc3py decoder."""

    def __init__(self, decoder: Any) -> None:
        self._decoder = decoder
        self.decoded_sizes: list[int] = []

    def decode(self, data: bytes, **kwargs: Any) -> bytes:
        decoded = self._decoder.decode(data, **kwargs)
        self.decoded_sizes.append(len(decoded))
        return decoded


class _DecoderBypass:
    """Test-only mutant that returns compressed bytes in place of decoded PCM."""

    def __init__(self, encoded_frame: bytes) -> None:
        self._encoded_frame = encoded_frame
        self.calls = 0
        self.output_sizes: list[int] = []

    def decode(self, _data: bytes, **_kwargs: Any) -> bytes:
        self.calls += 1
        self.output_sizes.append(len(self._encoded_frame))
        return self._encoded_frame


def _assert_frame_cadence(*, decoded_sizes: list[int], stt_audio_sizes: list[int]) -> None:
    """Assert the decoder output and third-frame STT flush contract."""

    if decoded_sizes != [320, 320, 320, 320]:
        raise OracleFailure("LC3 decoder output did not have four canonical PCM frame sizes")
    if stt_audio_sizes != [960]:
        raise OracleFailure("three decoded frames did not produce one 960-byte third-frame flush")


async def _new_runtime(
    client: _LoopbackClient,
) -> tuple[ListenSessionRuntime, tuple[bytes, ...], dict[str, str], _ObservedDecoder]:
    """Run production admission/normalization before the receiver owns frames."""

    request = ListenRequest(
        websocket=client,
        uid="replay-harness",
        codec="lc3_fs1030",
        sample_rate=16000,
        channels=1,
        vad_gate_override="disabled",
    )
    runtime = ListenSessionRuntime(request)
    with patch("routers.listen.runtime.run_blocking", AsyncMock(return_value=False)):
        if not await runtime._admit():  # noqa: SLF001 - oracle intentionally exercises admission.
            raise OracleFailure("lc3_fs1030 admission was rejected")

    decision = normalize_codec_frame(runtime.request.codec)
    if (
        decision.codec != "lc3"
        or decision.lc3_chunk_size != 30
        or decision.lc3_frame_duration_us != 10000
        or decision.frame_size != 160
    ):
        raise OracleFailure("lc3_fs1030 did not normalize to its canonical decoder parameters")

    runtime.request = replace(runtime.request, codec=decision.codec)
    runtime.frame_size = decision.frame_size
    runtime.lc3_frame_duration_us = decision.lc3_frame_duration_us
    runtime.stt_service = STTService.parakeet
    runtime.stt_language = "en"
    runtime.stt_model = "parakeet"
    runtime.vocabulary = []
    runtime._build_components()  # noqa: SLF001 - production component construction is under test.
    runtime.receiver.initialize_decoders()
    observed_decoder = _ObservedDecoder(runtime.receiver.lc3_decoder)
    runtime.receiver.lc3_decoder = observed_decoder

    encoder = lc3.Encoder(decision.lc3_frame_duration_us, runtime.request.sample_rate, num_channels=1)
    pcm = bytes(320)
    frames = tuple(encoder.encode(pcm, decision.lc3_chunk_size, bit_depth=16) for _ in range(4))
    if any(len(frame) != 30 for frame in frames):
        raise OracleFailure("test-owned encoder did not produce canonical 30-byte LC3 frames")

    return (
        runtime,
        frames,
        {
            "codec_parameters": _static_hash(
                {
                    "channels": 1,
                    "codec": "lc3_fs1030",
                    "frame_duration_us": decision.lc3_frame_duration_us,
                    "sample_rate": runtime.request.sample_rate,
                }
            )
        },
        observed_decoder,
    )


async def _run_receiver(*, decoder_bypass: bool) -> dict[str, Any]:
    client = _LoopbackClient(frames=(), wait_for_provider_close=not decoder_bypass)
    runtime, encoded_frames, metadata_hashes, observed_decoder = await _new_runtime(client)
    client._frames = encoded_frames if not decoder_bypass else encoded_frames[:3]
    bypass_decoder: _DecoderBypass | None = None

    if decoder_bypass:
        bypass_decoder = _DecoderBypass(encoded_frames[0])
        runtime.receiver.lc3_decoder = bypass_decoder

    async with _LoopbackParakeet(close_after_first_send=not decoder_bypass) as upstream:
        with _configured_parakeet_endpoint(upstream.api_url), _loopback_only_egress_guard():
            stt_socket = await runtime.receiver._create_stt_socket(  # noqa: SLF001 - actual receiver STT creation.
                lambda _segments: None,
                runtime.request.sample_rate,
            )
            if stt_socket is None:
                raise OracleFailure("production Parakeet client did not construct a socket")
            runtime.receiver.stt_socket = stt_socket
            client.bind_provider(upstream, stt_socket)
            await asyncio.wait_for(runtime.receiver.receive_data(), timeout=8)

    if decoder_bypass:
        if bypass_decoder is None or bypass_decoder.calls != 3 or bypass_decoder.output_sizes != [30, 30, 30]:
            raise OracleFailure("decoder-bypass mutant was not invoked for each test frame")
        if upstream.audio_sizes != [90]:
            raise OracleFailure("decoder-bypass mutant did not produce the expected forced-tail STT send")
        try:
            _assert_frame_cadence(decoded_sizes=bypass_decoder.output_sizes, stt_audio_sizes=upstream.audio_sizes)
        except OracleFailure as error:
            raise MutantRejected("decoder-bypass mutant concretely violated the frame-cadence contract") from error
        raise OracleFailure("decoder-bypass mutant unexpectedly met the frame-cadence contract")

    _assert_frame_cadence(decoded_sizes=observed_decoder.decoded_sizes, stt_audio_sizes=upstream.audio_sizes)
    if upstream.connections != 1:
        raise OracleFailure("provider connection count was not exactly one")
    if len(client.statuses) != 1 or len(client.closes) != 1:
        raise OracleFailure("terminal handling did not emit exactly one status and one close")
    status = client.statuses[0]
    if status.get("type") != "service_status" or status.get("status") != "stt_failed":
        raise OracleFailure("terminal status was not the bounded live-STT status")
    if status.get("reason") != "connection_lost":
        raise OracleFailure("terminal status did not classify the closed provider connection")
    if client.closes != [(1011, "transcription_service_unavailable")]:
        raise OracleFailure("client terminal close was not 1011")

    metadata_hashes["terminal_envelope_keys"] = _static_hash(sorted(status))
    return {
        "static_metadata_hashes": metadata_hashes,
        "byte_count_buckets": ["encoded_30", "pcm_320", "stt_960"],
        "counts": {
            "decoded_frames_before_flush": 3,
            "provider_connections": upstream.connections,
            "queued_frames_after_terminal": 1,
            "stt_sends": len(upstream.audio_sizes),
            "terminal_statuses": len(client.statuses),
        },
    }


async def run_oracle() -> dict[str, Any]:
    """Execute the real and mutant paths, returning only allow-listed evidence."""

    _require_linux_x86_64()
    with _quiet_logs():
        evidence = await _run_receiver(decoder_bypass=False)
        try:
            await _run_receiver(decoder_bypass=True)
        except MutantRejected:
            pass
        else:
            raise OracleFailure("decoder-bypass mutant was not rejected")

    return {
        "oracle": "replay-lc3-frame-timing",
        "event_order": [
            "lc3_fs1030_admitted",
            "codec_normalized",
            "10ms_frame",
            "10ms_frame",
            "10ms_frame",
            "30ms_flush",
            "provider_closed",
            "queued_10ms_frame_suppressed",
            "terminal_1011",
        ],
        "media_timing_buckets": ["10ms_frame", "30ms_flush"],
        "byte_count_buckets": evidence["byte_count_buckets"],
        "counts": evidence["counts"],
        "close_enum": {"client": "1011", "provider": "closed_after_first_send"},
        "retry_enum": "no_reconnect_after_terminal",
        "egress_guard": "loopback_only_default_deny_active",
        "static_metadata_hashes": evidence["static_metadata_hashes"],
        "local_deadline": "bounded_local",
        "mutant": "decoder_bypass_rejected",
    }


def main() -> int:
    try:
        evidence = asyncio.run(run_oracle())
    except (OracleFailure, PrerequisiteFailure) as error:
        print(f"Replay LC3 frame-timing oracle failed: {type(error).__name__}")
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
