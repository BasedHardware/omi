"""Local LLM record/replay proxy (DESIGN L6). Point the backend's ``OMI_LLM_GATEWAY_URL`` at it.

Per POST request:

1. Key the canonical request (``wire.request_key``).
2. Cache hit (modes ``record`` and ``replay``): serve the recorded response byte
   for byte, streaming or not, at no spend.
3. Miss in ``replay`` mode: HTTP 409 ``pipeline_lab_cache_miss`` (non-retryable).
4. Otherwise (``record`` miss, or ``refresh``): reserve the worst case on the run
   ledger, forward to the configured upstream, relay the response (SSE chunks
   are relayed as they arrive), settle the measured cost, cache 2xx responses.
5. Ledger refusal: HTTP 402 ``spend_cap_reached`` with ``x-should-retry: false``
   (the OpenAI and Anthropic SDKs honour it; 4xx is outside their retry set), and
   ``cap_reached`` is set for the orchestrator to stop the run.
6. Append one ``llm_calls.jsonl`` row per request, tagged with stage and
   conversation id (see ``tagging.py``).

Binds 127.0.0.1 only. Upstream gets the client's headers minus hop-by-hop,
lab tag and encoding headers (``Accept-Encoding: identity`` so recorded bodies are
plain). Settlement: 2xx with usage -> priced cost; 2xx without usage -> the
reservation is kept as the cost; an HTTP error answer -> 0 (not billed); a
transport failure after sending -> the reservation is kept (unknown fate).
"""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import os
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

from testing.pipeline_lab.contracts import LlmCall, utc_iso
from testing.pipeline_lab.ledger import SpendCapReached, SpendLedger
from testing.pipeline_lab.llm_proxy import tagging, wire
from testing.pipeline_lab.store import Store

MODES = ('record', 'replay', 'refresh')
CACHE_NAMESPACE = 'llm'
RETRYABLE_UPSTREAM_STATUS = frozenset({429, 502, 503, 504})
UPSTREAM_ATTEMPTS = 4
UPSTREAM_BACKOFF_SECONDS = 2.0
# A refused or reset connection before the request went out is always safe to retry; the dev gateway
# is reached through a reconnecting port-forward that can be down for tens of seconds (a 2026-11-18
# replay lost its daily summary to one such gap after 12 s of retries). Wait up to this long for it.
UPSTREAM_CONNECT_WAIT_SECONDS = float(os.environ.get('OMI_PIPELINE_LAB_UPSTREAM_CONNECT_WAIT', '120') or 120)
_HOP = {
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade',
    'host',
    'content-length',
    'accept-encoding',
}


def _header_value(value: object) -> str:
    """A response header value with no CR, LF or other control characters (upstream values are relayed)."""
    return ''.join(ch for ch in str(value) if ch == '\t' or ' ' <= ch != '\x7f')


def _is_loopback(host: str) -> bool:
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class ProxyConfig:
    upstream: str
    mode: str = 'record'
    run_id: Optional[str] = None
    prices: wire.PriceTable = field(default_factory=wire.PriceTable)
    upstream_token: Optional[str] = None  # replaces the client's Authorization when set
    ignored_fields: tuple[str, ...] = wire.DEFAULT_IGNORED_FIELDS
    timeout: float = 180.0
    max_body_bytes: int = 8_000_000

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f'mode must be one of {MODES}')
        parsed = urllib.parse.urlsplit(self.upstream)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('upstream must be an http(s) URL')
        if parsed.scheme == 'http' and not _is_loopback(parsed.hostname):
            # Prompts are private and the proxy may add a bearer token: plain HTTP only to this host.
            raise ValueError('a non-loopback upstream must use https')


def _error_body(kind: str, code: str, message: str) -> bytes:
    # Readable by both SDK families: OpenAI reads error.message/type/code, Anthropic reads type=error.
    return json.dumps({'type': 'error', 'error': {'type': kind, 'code': code, 'message': message}}).encode()


class LlmProxy:
    """One proxy per run. ``start()`` binds and serves on a daemon thread; ``stop()`` shuts it down."""

    def __init__(
        self,
        config: ProxyConfig,
        *,
        store: Optional[Store] = None,
        ledger: Optional[SpendLedger] = None,
        host: str = '127.0.0.1',
        port: int = 0,
    ):
        if host not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('the lab proxy binds loopback only')
        if config.mode != 'replay' and ledger is None:
            raise ValueError('a spend ledger is required unless mode is replay')
        self.config = config
        self.store = store
        self.ledger = ledger
        self.host = host
        self.port = port
        self.cap_reached = False
        self.session_tag: tuple[Optional[str], Optional[str]] = (None, None)
        self.counters = {'requests': 0, 'hits': 0, 'misses': 0, 'errors': 0, 'refused': 0}
        self._key_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._active = 0  # handlers can still be settling streamed calls
        self._idle = threading.Condition()

    # ---- lifecycle ---------------------------------------------------------------

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError('proxy not started')
        return f'http://{self.host}:{self._server.server_address[1]}'

    def start(self) -> 'LlmProxy':
        proxy = self

        class Handler(_Handler):
            owner = proxy

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name='pipeline-lab-llm-proxy', daemon=True)
        self._thread.start()
        return self

    def serve_forever(self, on_ready: Optional[Callable[[str], None]] = None) -> None:
        """Foreground serving for the CLI (Ctrl-C to stop); ``on_ready`` gets the bound URL."""
        proxy = self

        class Handler(_Handler):
            owner = proxy

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        if on_ready is not None:
            on_ready(self.url)
        try:
            self._server.serve_forever()
        finally:
            self._server.server_close()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            # Wait for in-flight handlers, so the ledger and call log hold every answered call.
            deadline = time.monotonic() + self.config.timeout + 5
            with self._idle:
                while self._active and time.monotonic() < deadline:
                    self._idle.wait(timeout=0.1)
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def __enter__(self) -> 'LlmProxy':
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    # ---- internals ---------------------------------------------------------------

    def key_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def cache_get(self, key: str) -> Optional[dict[str, Any]]:
        return self.store.cache_get(CACHE_NAMESPACE, key) if self.store is not None else None

    def cache_put(self, key: str, entry: dict[str, Any]) -> None:
        if self.store is not None:
            self.store.cache_put(CACHE_NAMESPACE, key, entry)

    def log(self, call: LlmCall) -> None:
        if self.store is not None and self.config.run_id:
            self.store.append_llm_calls(self.config.run_id, [call])

    def tag_for(self, headers: Any) -> tuple[Optional[str], Optional[str]]:
        stage = headers.get(tagging.STAGE_HEADER)
        conversation = headers.get(tagging.CONVERSATION_HEADER)
        if stage or conversation:
            return stage, conversation
        return self.session_tag


class _Handler(BaseHTTPRequestHandler):
    owner: LlmProxy
    protocol_version = 'HTTP/1.1'
    server_version = 'pipeline-lab-llm-proxy'
    sys_version = ''

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        return  # request lines may carry private data; the call log is the record

    # ---- small writers -----------------------------------------------------------

    def _send(
        self, status: int, body: bytes, content_type: str = 'application/json', extra: dict | None = None
    ) -> None:
        self.send_response(status)
        self.send_header('Content-Type', _header_value(content_type))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for name, value in (extra or {}).items():
            self.send_header(_header_value(name), _header_value(value))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Optional[bytes]:
        length = self.headers.get('Content-Length')
        if length is None:
            self._send(411, _error_body('invalid_request_error', 'length_required', 'Content-Length required'))
            return None
        try:
            size = int(length)
        except ValueError:
            size = -1
        if size < 0:
            self._send(400, _error_body('invalid_request_error', 'bad_length', 'Content-Length is not a length'))
            return None
        if size > self.owner.config.max_body_bytes:
            self._send(413, _error_body('invalid_request_error', 'too_large', 'request body over the lab cap'))
            return None
        return self.rfile.read(size)

    # ---- routes --------------------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == '/_lab/health':
            owner = self.owner
            body = {
                'ok': True,
                'mode': owner.config.mode,
                'run_id': owner.config.run_id,
                'cap_reached': owner.cap_reached,
                'counters': owner.counters,
                'ledger': owner.ledger.snapshot() if owner.ledger else None,
            }
            self._send(200, json.dumps(body).encode())
            return
        self._send(405, _error_body('invalid_request_error', 'method_not_allowed', 'lab proxy serves POST only'))

    def do_POST(self) -> None:
        owner = self.owner
        with owner._idle:
            owner._active += 1
        try:
            self._do_post()
        finally:
            with owner._idle:
                owner._active -= 1
                owner._idle.notify_all()

    def _do_post(self) -> None:
        body = self._read_body()
        if body is None:
            return
        if self.path == '/_lab/tag':
            data = wire.parse_json(body) or {}
            self.owner.session_tag = (data.get('stage'), data.get('conversation_id'))
            self._send(200, b'{"ok":true}')
            return
        self._proxy(body)

    def do_PUT(self) -> None:
        self._send(405, _error_body('invalid_request_error', 'method_not_allowed', 'lab proxy serves POST only'))

    do_DELETE = do_PATCH = do_PUT

    # ---- the proxy -------------------------------------------------------------------

    def _proxy(self, body: bytes) -> None:
        owner = self.owner
        config = owner.config
        started = time.monotonic()
        owner.counters['requests'] += 1
        parsed = wire.parse_json(body)
        stream = wire.is_stream_request(parsed)
        stage, conversation = owner.tag_for(self.headers)
        key = wire.request_key('POST', self.path, body, dict(self.headers.items()), config.ignored_fields)
        call = LlmCall(
            id='llm-' + secrets.token_hex(8),
            at=utc_iso(),
            stage=stage,
            conversation_id=conversation,
            feature=self.headers.get('X-Omi-LLM-Feature'),
            model=parsed.get('model') if isinstance(parsed, dict) else None,
            prompt=wire.prompt_view(parsed),
            extra={'request_key': key, 'path': self.path, 'stream': stream},
        )
        try:
            with owner.key_lock(key):
                entry = owner.cache_get(key) if config.mode != 'refresh' else None
                if entry is not None:
                    owner.counters['hits'] += 1
                    send_response = self._cached_response(entry, call)
                elif config.mode == 'replay':
                    owner.counters['misses'] += 1
                    call.extra.update(status=409, error='cache_miss')
                    send_response = partial(
                        self._send,
                        409,
                        _error_body(
                            'pipeline_lab_cache_miss', 'cache_miss', 'replay mode: request not in the lab cache'
                        ),
                        extra={'x-should-retry': 'false', 'X-Pipeline-Lab-Call-Id': call.id},
                    )
                else:
                    owner.counters['misses'] += 1
                    send_response = self._forward(body, parsed, stream, key, call)
        finally:
            call.ms = round((time.monotonic() - started) * 1000.0, 1)
            owner.log(call)
        # Buffered callers can export conversation artifacts as soon as they receive
        # the response. Publish the attributed call before those callers resume.
        if send_response is not None:
            try:
                send_response()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

    def _cached_response(self, entry: dict[str, Any], call: LlmCall) -> Callable[[], None]:
        payload = base64.b64decode(entry['body_b64']) if 'body_b64' in entry else entry.get('body', '').encode('utf-8')
        call.cache_hit = True
        call.model = entry.get('model') or call.model
        call.tokens_in = int(entry.get('tokens_in') or 0)
        call.tokens_out = int(entry.get('tokens_out') or 0)
        call.output = entry.get('output')
        call.usd = 0.0
        call.extra.update(status=int(entry.get('status') or 200), recorded_usd=entry.get('usd'))
        return partial(
            self._send,
            int(entry.get('status') or 200),
            payload,
            entry.get('content_type') or 'application/json',
            extra={'X-Pipeline-Lab-Cache': 'hit', 'X-Pipeline-Lab-Call-Id': call.id},
        )

    def _upstream_headers(self) -> dict[str, str]:
        headers = {}
        for name, value in self.headers.items():
            lowered = name.lower()
            if lowered in _HOP or lowered.startswith(tagging.LAB_HEADER_PREFIX):
                continue
            headers[name] = value
        headers['Accept-Encoding'] = 'identity'
        if self.owner.config.upstream_token:
            headers = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'x-api-key')}
            headers['Authorization'] = 'Bearer ' + self.owner.config.upstream_token
        return headers

    def _forward(self, body: bytes, parsed: Any, stream: bool, key: str, call: LlmCall) -> Callable[[], None] | None:
        owner = self.owner
        config = owner.config
        assert owner.ledger is not None
        estimate = config.prices.reservation(self.path, parsed, len(body))
        try:
            reservation = owner.ledger.reserve(estimate, purpose=f'llm:{call.stage or "untagged"}')
        except SpendCapReached as stop:
            owner.cap_reached = True
            owner.counters['refused'] += 1
            call.extra.update(status=402, error='spend_cap_reached')
            return partial(
                self._send,
                402,
                _error_body('pipeline_lab_spend_cap', 'spend_cap_reached', str(stop)),
                extra={'x-should-retry': 'false', 'X-Pipeline-Lab-Call-Id': call.id},
            )

        upstream = urllib.parse.urlsplit(config.upstream)
        connection_cls = http.client.HTTPSConnection if upstream.scheme == 'https' else http.client.HTTPConnection
        target = upstream.path.rstrip('/') + self.path
        connection = None
        sent = False
        try:
            # A transient gateway answer (429/502/503/504) is retried before anything reaches the
            # client, so one blip does not fail a whole replay. Those answers are not billed upstream.
            # A transport error after the body was sent is never retried: its fate is unknown.
            connect_deadline = time.monotonic() + UPSTREAM_CONNECT_WAIT_SECONDS
            attempt = 0
            while True:
                attempt += 1
                connection = connection_cls(upstream.hostname, upstream.port, timeout=config.timeout)
                sent = False
                try:
                    connection.putrequest('POST', target, skip_accept_encoding=True)
                    for name, value in self._upstream_headers().items():
                        connection.putheader(name, value)
                    connection.putheader('Content-Length', str(len(body)))
                    connection.endheaders(body)
                    sent = True
                    response = connection.getresponse()
                except (OSError, http.client.HTTPException):
                    connection.close()
                    left = connect_deadline - time.monotonic()
                    if sent or (attempt >= UPSTREAM_ATTEMPTS and left <= 0):
                        raise
                    call.extra.setdefault('retries', []).append('transport')
                    delay = UPSTREAM_BACKOFF_SECONDS * min(attempt, 5)
                    time.sleep(delay if attempt < UPSTREAM_ATTEMPTS else max(0.0, min(delay, left)))
                    continue
                if response.status in RETRYABLE_UPSTREAM_STATUS and attempt < UPSTREAM_ATTEMPTS:
                    response.read()
                    connection.close()
                    call.extra.setdefault('retries', []).append(response.status)
                    time.sleep(UPSTREAM_BACKOFF_SECONDS * attempt)
                    continue
                break
            content_type = response.getheader('Content-Type') or 'application/json'
            event_stream = 'text/event-stream' in content_type
            send_response = None
            if event_stream or stream:
                payload = self._relay_stream(response, content_type, call.id)
            else:
                payload = response.read()
                send_response = partial(
                    self._send,
                    response.status,
                    payload,
                    content_type,
                    extra={'X-Pipeline-Lab-Cache': 'miss', 'X-Pipeline-Lab-Call-Id': call.id},
                )
        except (OSError, http.client.HTTPException) as error:
            owner.counters['errors'] += 1
            if sent:
                owner.ledger.settle(reservation, reservation.usd)  # fate unknown: keep the worst case
                call.usd = round(reservation.usd, 9)
            else:
                owner.ledger.release(reservation)
            call.extra.update(status=502, error=f'upstream_transport:{type(error).__name__}')
            return partial(
                self._send, 502, _error_body('pipeline_lab_upstream', 'upstream_transport', type(error).__name__)
            )
        finally:
            if connection is not None:
                connection.close()

        status = response.status
        call.extra['status'] = status
        if not 200 <= status < 300:
            owner.counters['errors'] += 1
            owner.ledger.settle(reservation, 0.0)
            call.extra['error'] = f'upstream_http_{status}'
            return send_response
        usage = wire.parse_usage(payload, event_stream or stream)
        cost = config.prices.cost(usage) if usage.known else reservation.usd
        owner.ledger.settle(reservation, cost)
        call.model = usage.model or call.model
        call.tokens_in = usage.tokens_in
        call.tokens_out = usage.tokens_out
        call.output = usage.output
        call.usd = round(cost, 9)
        if not usage.known:
            call.extra['warning'] = 'usage missing; reservation kept as cost'
        owner.cache_put(
            key,
            {
                'request': {'path': self.path, 'feature': call.feature, 'stream': stream},
                'status': status,
                'content_type': content_type,
                'body': payload.decode('utf-8') if _is_utf8(payload) else None,
                **({} if _is_utf8(payload) else {'body_b64': base64.b64encode(payload).decode('ascii')}),
                'model': call.model,
                'tokens_in': call.tokens_in,
                'tokens_out': call.tokens_out,
                'usd': call.usd,
                'output': call.output,
                'recorded_run': config.run_id,
            },
        )
        return send_response

    def _relay_stream(self, response: http.client.HTTPResponse, content_type: str, call_id: str) -> bytes:
        """Relay upstream chunks to the client as they arrive; return the full body."""
        self.send_response(response.status)
        self.send_header('Content-Type', _header_value(content_type))
        self.send_header('Transfer-Encoding', 'chunked')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Pipeline-Lab-Cache', 'miss')
        self.send_header('X-Pipeline-Lab-Call-Id', call_id)
        self.end_headers()
        buffered = bytearray()
        client_alive = True
        while True:
            chunk = response.read1(65536)
            if not chunk:
                break
            buffered.extend(chunk)
            if client_alive:
                try:
                    self.wfile.write(b'%x\r\n%s\r\n' % (len(chunk), chunk))
                    self.wfile.flush()
                except OSError:
                    client_alive = False  # keep draining upstream so the recording is complete
        if client_alive:
            try:
                self.wfile.write(b'0\r\n\r\n')
                self.wfile.flush()
            except OSError:
                pass
        return bytes(buffered)


def _is_utf8(payload: bytes) -> bool:
    try:
        payload.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False
