#!/usr/bin/env python3
"""Prove one deployed managed realtime-provider turn without exposing credentials.

The probe mints a short-lived provider credential from the deployed desktop
backend, opens the provider's direct WebSocket path, commits a fixed harmless
text fixture, and waits for the provider's terminal response event. It accepts
only a mode-0600 Firebase ID-token file so callers never put a bearer token in a
command line, environment dump, or log.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import stat
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

MINT_PATH = "/v2/realtime/session"
OPENAI_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-2"
GEMINI_URL_PREFIX = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained"
OPENAI_TOKEN_PREFIX = "ek_"
GEMINI_TOKEN_PREFIX = "auth_tokens/"
PROBE_INPUT = "Reply with exactly OMI_PROVIDER_PROBE_OK."
MAX_TOKEN_CHARS = 8192
MAX_HTTP_RESPONSE_BYTES = 128 * 1024
MAX_HANDSHAKE_BYTES = 32 * 1024
MAX_WEBSOCKET_MESSAGE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 25.0


@dataclass(frozen=True)
class ProbeConfig:
    provider: str
    base_url: str
    bearer_token: str | None
    timeout_seconds: float


class ProbeFailure(RuntimeError):
    def __init__(self, failure_class: str, *, retryable: bool = False):
        super().__init__(failure_class)
        self.failure_class = failure_class
        self.retryable = retryable


def _read_bearer_token(path: Path | None) -> str | None:
    if path is None:
        return None
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_mode & 0o077:
            return None
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            token = handle.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return token if 0 < len(token) <= MAX_TOKEN_CHARS else None


def _normalize_base_url(value: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        return None
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def config_from_args(args: argparse.Namespace) -> ProbeConfig:
    return ProbeConfig(
        provider=args.provider,
        base_url=_normalize_base_url(args.backend_base_url) or "",
        bearer_token=_read_bearer_token(args.bearer_token_file),
        timeout_seconds=args.timeout_seconds,
    )


def _emit(provider: str, step: str, status: str, failure_class: str) -> None:
    print(f"provider={provider} step={step} status={status} class={failure_class}", flush=True)


def _classify_http_error(status_code: int) -> ProbeFailure:
    if 400 <= status_code < 500:
        return ProbeFailure("mint_http_4xx")
    if 500 <= status_code < 600:
        return ProbeFailure("upstream_5xx", retryable=True)
    return ProbeFailure("mint_http_unexpected")


def _mint_provider_token(config: ProbeConfig) -> str:
    if not config.base_url or not config.bearer_token:
        raise ProbeFailure("configuration")
    body = json.dumps({"provider": config.provider}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}{MINT_PATH}",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {config.bearer_token}",
            "Content-Type": "application/json",
        },
    )
    payload_bytes = b""
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            if int(response.status) < 200 or int(response.status) >= 300:
                raise _classify_http_error(int(response.status))
            payload_bytes = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise _classify_http_error(error.code) from error
    except (socket.timeout, TimeoutError):
        raise ProbeFailure("timeout", retryable=True)
    except (urllib.error.URLError, OSError, ValueError):
        raise ProbeFailure("mint_transport")

    if len(payload_bytes) > MAX_HTTP_RESPONSE_BYTES:
        raise ProbeFailure("mint_schema")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeFailure("mint_schema")
    finally:
        payload_bytes = b""
    if not isinstance(payload, dict):
        raise ProbeFailure("mint_schema")
    token = payload.get("token")
    expected_prefix = OPENAI_TOKEN_PREFIX if config.provider == "openai" else GEMINI_TOKEN_PREFIX
    valid = payload.get("provider") == config.provider and isinstance(token, str) and token.startswith(expected_prefix)
    if not valid or len(token) > MAX_TOKEN_CHARS:
        raise ProbeFailure("mint_schema")
    return token


class ProviderWebSocket:
    def __init__(self, url: str, headers: dict[str, str], timeout_seconds: float):
        self.url = url
        self.headers = headers
        self.timeout_seconds = timeout_seconds
        self._socket: socket.socket | ssl.SSLSocket | None = None
        self._closed = False
        self._fragment_opcode: int | None = None
        self._fragments: list[bytes] = []

    def connect(self) -> None:
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme != "wss" or not parsed.hostname:
            raise ProbeFailure("connect_failed")
        try:
            tcp_socket = socket.create_connection((parsed.hostname, parsed.port or 443), self.timeout_seconds)
            tls_socket = ssl.create_default_context().wrap_socket(tcp_socket, server_hostname=parsed.hostname)
            tls_socket.settimeout(self.timeout_seconds)
            self._socket = tls_socket
            self._perform_handshake(parsed)
        except ProbeFailure:
            self.close()
            raise
        except (socket.timeout, TimeoutError) as error:
            self.close()
            raise ProbeFailure("timeout", retryable=True) from error
        except (OSError, ssl.SSLError, ValueError) as error:
            self.close()
            raise ProbeFailure("connect_failed") from error

    def _perform_handshake(self, parsed: urllib.parse.SplitResult) -> None:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        host = parsed.hostname or ""
        if parsed.port and parsed.port != 443:
            host = f"{host}:{parsed.port}"
        websocket_key = base64.b64encode(os.urandom(16)).decode("ascii")
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {websocket_key}",
            "Sec-WebSocket-Version: 13",
        ]
        for name, value in self.headers.items():
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise ProbeFailure("connect_failed")
            lines.append(f"{name}: {value}")
        self._send_raw(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        raw_response = self._read_until_headers_complete()
        try:
            header_text = raw_response.decode("iso-8859-1")
            status_line = header_text.split("\r\n", 1)[0]
            status_code = int(status_line.split()[1])
        except (UnicodeDecodeError, IndexError, ValueError):
            raise ProbeFailure("connect_failed")
        if status_code != 101:
            if 500 <= status_code < 600:
                raise ProbeFailure("upstream_5xx", retryable=True)
            if 400 <= status_code < 500:
                raise ProbeFailure("connect_http_4xx")
            raise ProbeFailure("connect_failed")

    def _read_until_headers_complete(self) -> bytes:
        response = bytearray()
        while b"\r\n\r\n" not in response:
            if len(response) >= MAX_HANDSHAKE_BYTES:
                raise ProbeFailure("connect_failed")
            response.extend(self._recv_exact(1))
        return bytes(response)

    def _send_raw(self, payload: bytes) -> None:
        if self._socket is None:
            raise ProbeFailure("connect_failed")
        self._socket.sendall(payload)

    def _recv_exact(self, size: int) -> bytes:
        if self._socket is None:
            raise ProbeFailure("connect_failed")
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise ProbeFailure("connect_failed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def send_json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_WEBSOCKET_MESSAGE_BYTES:
            raise ProbeFailure("commit_failed")
        try:
            self._send_frame(0x1, encoded)
        except (socket.timeout, TimeoutError) as error:
            raise ProbeFailure("timeout", retryable=True) from error
        except (OSError, ssl.SSLError) as error:
            raise ProbeFailure("provider_transport") from error

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        length = len(payload)
        frame = bytearray([0x80 | opcode])
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._send_raw(bytes(frame))

    def receive_json(self) -> dict[str, Any]:
        while True:
            opcode, finished, payload = self._receive_frame()
            if opcode == 0x8:
                raise ProbeFailure("connect_failed")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x0:
                if self._fragment_opcode is None:
                    raise ProbeFailure("provider_event_error")
                self._fragments.append(payload)
                if not finished:
                    continue
                opcode = self._fragment_opcode
                payload = b"".join(self._fragments)
                self._fragment_opcode = None
                self._fragments.clear()
            elif not finished:
                if opcode not in (0x1, 0x2):
                    raise ProbeFailure("provider_event_error")
                self._fragment_opcode = opcode
                self._fragments = [payload]
                continue
            if opcode not in (0x1, 0x2):
                continue
            try:
                decoded = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ProbeFailure("provider_event_error")
            if not isinstance(decoded, dict):
                raise ProbeFailure("provider_event_error")
            return decoded

    def _receive_frame(self) -> tuple[int, bool, bytes]:
        first, second = self._recv_exact(2)
        finished = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        if length > MAX_WEBSOCKET_MESSAGE_BYTES:
            raise ProbeFailure("provider_event_error")
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, finished, payload

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._socket is not None:
                self._send_frame(0x8, b"")
        except (OSError, ProbeFailure):
            pass
        finally:
            if self._socket is not None:
                self._socket.close()
                self._socket = None


def _receive_until(websocket: ProviderWebSocket, timeout_seconds: float, matcher: Any) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeFailure("timeout", retryable=True)
        if websocket._socket is not None:
            websocket._socket.settimeout(remaining)
        try:
            event = websocket.receive_json()
        except (socket.timeout, TimeoutError) as error:
            raise ProbeFailure("timeout", retryable=True) from error
        except (OSError, ssl.SSLError) as error:
            raise ProbeFailure("provider_transport") from error
        if event.get("type") == "error" or "error" in event:
            raise ProbeFailure("provider_event_error")
        if matcher(event):
            return


def _openai_websocket(token: str, timeout_seconds: float) -> ProviderWebSocket:
    websocket = ProviderWebSocket(
        OPENAI_URL,
        {"Authorization": f"Bearer {token}"},
        timeout_seconds,
    )
    try:
        websocket.connect()
        websocket.send_json(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": "Return the requested deterministic response.",
                    "output_modalities": ["text"],
                },
            }
        )
        _receive_until(websocket, timeout_seconds, lambda event: event.get("type") == "session.updated")
        return websocket
    except Exception:
        websocket.close()
        raise


def _gemini_websocket(token: str, timeout_seconds: float) -> ProviderWebSocket:
    query = urllib.parse.urlencode({"access_token": token})
    websocket = ProviderWebSocket(f"{GEMINI_URL_PREFIX}?{query}", {}, timeout_seconds)
    try:
        websocket.connect()
        websocket.send_json(
            {
                "setup": {
                    "model": "models/gemini-3.1-flash-live-preview",
                    "generationConfig": {"responseModalities": ["AUDIO"], "temperature": 0.0},
                    "systemInstruction": {"parts": [{"text": "Return the requested deterministic response."}]},
                }
            }
        )
        _receive_until(websocket, timeout_seconds, lambda event: "setupComplete" in event)
        return websocket
    except Exception:
        websocket.close()
        raise


def run_probe(config: ProbeConfig) -> int:
    if config.provider not in {"openai", "gemini"} or not config.base_url or not config.bearer_token:
        _emit(config.provider, "authenticate", "FAIL", "configuration")
        return 1
    _emit(config.provider, "authenticate", "PASS", "none")
    provider_token = ""
    current_step = "mint"
    try:
        provider_token = _mint_provider_token(config)
        _emit(config.provider, "mint", "PASS", "none")
        if config.provider == "openai":
            current_step = "connect"
            websocket = _openai_websocket(provider_token, config.timeout_seconds)
            _emit(config.provider, "connect", "PASS", "none")
            try:
                current_step = "commit"
                websocket.send_json(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": PROBE_INPUT}],
                        },
                    }
                )
                websocket.send_json(
                    {"type": "response.create", "response": {"output_modalities": ["text"]}}
                )
                _emit(config.provider, "commit", "PASS", "none")
                current_step = "response"

                def response_completed(event: dict[str, Any]) -> bool:
                    if event.get("type") != "response.done":
                        return False
                    response = event.get("response")
                    return isinstance(response, dict) and response.get("status") == "completed"

                _receive_until(websocket, config.timeout_seconds, response_completed)
                _emit(config.provider, "response", "PASS", "none")
            finally:
                websocket.close()
        else:
            current_step = "connect"
            websocket = _gemini_websocket(provider_token, config.timeout_seconds)
            _emit(config.provider, "connect", "PASS", "none")
            try:
                current_step = "commit"
                websocket.send_json({"realtimeInput": {"activityStart": {}}})
                websocket.send_json({"realtimeInput": {"text": PROBE_INPUT}})
                websocket.send_json({"realtimeInput": {"activityEnd": {}}})
                _emit(config.provider, "commit", "PASS", "none")
                current_step = "response"
                _receive_until(
                    websocket,
                    config.timeout_seconds,
                    lambda event: isinstance(event.get("serverContent"), dict)
                    and event["serverContent"].get("turnComplete") is True,
                )
                _emit(config.provider, "response", "PASS", "none")
            finally:
                websocket.close()
    except ProbeFailure as error:
        _emit(config.provider, current_step, "FAIL", error.failure_class)
        return 75 if error.retryable else 1
    except (socket.timeout, TimeoutError):
        _emit(config.provider, current_step, "FAIL", "timeout")
        return 75
    except (OSError, ssl.SSLError):
        _emit(config.provider, current_step, "FAIL", "provider_transport")
        return 1
    finally:
        provider_token = ""
    _emit(config.provider, "close", "PASS", "expected_idle_teardown")
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("openai", "gemini"))
    parser.add_argument("backend_base_url")
    parser.add_argument("--bearer-token-file", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 60:
        parser.error("--timeout-seconds must be between 1 and 60")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    return run_probe(config_from_args(parse_args(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
