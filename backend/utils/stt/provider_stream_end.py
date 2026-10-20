"""Who ended a live provider STT stream, with which close code, and how fast it served.

Vendor escalations (Modulate 2026-10-20) need three things listen did not record:
the vendor's own request id for a failed stream, the close code and closer on
*every* stream end (not only when the vendor sent an error frame), and
per-provider connect / first-text latency.

Each provider socket owns one ``ProviderStreamEnd`` latch. The first end it
observes is recorded once: a vendor error frame, close frame, clean EOF or
transport loss (``vendor``), our keepalive or done-wait timeout
(``us_timeout``), or our own teardown, whose cause the session sets as an
intent before closing (``us_client_gone``, ``us_drain`` for a pod restart,
``us_failover``). Our teardown with no recorded intent counts as
``us_client_gone``.

Labels are closed vocabularies only. Log lines carry bounded tokens, the
vendor's request id when it matches a strict id shape, and sanitized close
diagnostics; never user ids, audio, transcript or raw vendor text.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from typing import Any, Callable, Mapping, Optional

from prometheus_client import Counter, Histogram

from utils.log_sanitizer import sanitize_provider_error
from utils.stt.failure_diagnostics import frame_close_code, session_age_bucket
from utils.stt.pod_drain import is_draining
from utils.stt.stream_close import bounded_stream_close_provider

logger = logging.getLogger(__name__)

VENDOR = 'vendor'
US_CLIENT_GONE = 'us_client_gone'
US_DRAIN = 'us_drain'
US_FAILOVER = 'us_failover'
US_TIMEOUT = 'us_timeout'
CLOSERS = (VENDOR, US_CLIENT_GONE, US_DRAIN, US_FAILOVER, US_TIMEOUT)

# ``none``: the stream ended before any close frame was seen in either direction.
CODE_CLASSES = ('1000', '1001', '1006', '1011', '4xxx', 'other', 'none')
PROVIDERS = ('modulate', 'soniox')

# Uvicorn closes every open websocket with 1012 when the pod shuts down.
POD_RESTART_CLOSE_CODE = 1012
# Callers abort a cancelled drain within their cleanup budget (seconds); this backstop runs after it.
CANCELLED_DRAIN_RECORD_DELAY_SECONDS = 5.0

OMI_STT_PROVIDER_STREAM_END_TOTAL = Counter(
    'omi_stt_provider_stream_end_total',
    'Live-STT provider stream ends by bounded provider, closer and close-code class',
    ['provider', 'closer', 'code_class'],
)
OMI_STT_PROVIDER_CONNECT_SECONDS = Histogram(
    'omi_stt_provider_connect_seconds',
    'Seconds from the first live-STT provider connect attempt until the stream accepts audio',
    ['provider'],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0),
)
OMI_STT_PROVIDER_FIRST_TEXT_SECONDS = Histogram(
    'omi_stt_provider_first_text_seconds',
    'Seconds from the first audio written to a live-STT provider stream until its first text',
    ['provider'],
    buckets=(0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
)

for _provider in PROVIDERS:
    OMI_STT_PROVIDER_CONNECT_SECONDS.labels(provider=_provider)
    OMI_STT_PROVIDER_FIRST_TEXT_SECONDS.labels(provider=_provider)
    for _closer in CLOSERS:
        for _code_class in CODE_CLASSES:
            OMI_STT_PROVIDER_STREAM_END_TOTAL.labels(provider=_provider, closer=_closer, code_class=_code_class)

# Handshake headers that commonly carry a vendor trace id, in preference order.
REQUEST_ID_HEADERS = (
    'x-request-id',
    'request-id',
    'x-amzn-requestid',
    'x-amz-request-id',
    'x-correlation-id',
    'x-trace-id',
    'x-amzn-trace-id',
    'x-cloud-trace-context',
    'traceparent',
    'cf-ray',
)
# Vendor-generated ids an error or status frame may carry.
REQUEST_ID_FRAME_KEYS = ('request_id', 'requestId', 'trace_id', 'traceId', 'session_id', 'sessionId')
_REQUEST_ID_RE = re.compile(r'[A-Za-z0-9._:/=+;-]{1,128}')
_HEADER_NAME_RE = re.compile(r'[a-z0-9-]{1,64}')
_MAX_LOGGED_HEADER_NAMES = 32
_header_names_logged: set[str] = set()
_header_names_lock = threading.Lock()


def bounded_closer(closer: Optional[str]) -> str:
    return closer if closer in CLOSERS else US_CLIENT_GONE


def close_code_class(code: Any) -> str:
    if code is None or isinstance(code, bool) or not isinstance(code, int) or code < 0:
        return 'none'
    label = str(code)
    if label in CODE_CLASSES:
        return label
    return '4xxx' if 4000 <= code <= 4999 else 'other'


def bounded_request_id(value: Any) -> Optional[str]:
    """A vendor id only when it has a strict id shape; anything else is dropped, never logged."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text if _REQUEST_ID_RE.fullmatch(text) else None


def teardown_closer(close_code: Any) -> str:
    """Our-side closer for a listen session ending with the client websocket's close code."""
    return US_DRAIN if close_code == POD_RESTART_CLOSE_CODE or is_draining() else US_CLIENT_GONE


def session_teardown_closer(host: Any) -> str:
    """``teardown_closer`` for a listen session host; a host without state is an ordinary teardown."""
    return teardown_closer(getattr(getattr(host, 'state', None), 'close_code', None))


def _headers(source: Any) -> Optional[Mapping[str, Any]]:
    # websockets 12 legacy client: ``response_headers``; asyncio client: ``response.headers``;
    # handshake rejections: ``headers`` or ``response.headers``.
    for candidate in (
        getattr(source, 'response_headers', None),
        getattr(getattr(source, 'response', None), 'headers', None),
        getattr(source, 'headers', None),
    ):
        if candidate is not None and hasattr(candidate, 'get'):
            return candidate
    return None


def handshake_request_id(source: Any) -> tuple[Optional[str], Optional[str]]:
    """(header name, id) from a handshake response or rejection, or (None, None). Never raises."""
    try:
        headers = _headers(source)
        if headers is None:
            return None, None
        for name in REQUEST_ID_HEADERS:
            request_id = bounded_request_id(headers.get(name))
            if request_id is not None:
                return name, request_id
    except Exception:
        pass
    return None, None


def frame_request_id(msg: Mapping[str, Any]) -> Optional[str]:
    for key in REQUEST_ID_FRAME_KEYS:
        request_id = bounded_request_id(msg.get(key))
        if request_id is not None:
            return request_id
    return None


def _log_handshake_header_names(provider: str, source: Any) -> None:
    """Once per provider per process: which headers the vendor returns (names only, never values)."""
    with _header_names_lock:
        if provider in _header_names_logged:
            return
        _header_names_logged.add(provider)
    try:
        headers = _headers(source)
        keys = headers.keys() if headers is not None and hasattr(headers, 'keys') else ()
        names = sorted({str(key).lower() for key in keys if _HEADER_NAME_RE.fullmatch(str(key).lower())})
        logger.info(
            'STT provider handshake header names provider=%s names=%s',
            provider,
            ','.join(names[:_MAX_LOGGED_HEADER_NAMES]) or 'none',
        )
    except Exception:
        pass


def observe_connect_seconds(provider: str, seconds: float) -> None:
    """Never raises."""
    try:
        OMI_STT_PROVIDER_CONNECT_SECONDS.labels(provider=bounded_stream_close_provider(provider)).observe(
            max(0.0, seconds)
        )
    except Exception:
        pass


def log_connect_rejection(provider: str, error: BaseException) -> None:
    """Log the vendor's request id and HTTP status for a refused handshake. Never raises."""
    try:
        header, request_id = handshake_request_id(error)
        status = getattr(error, 'status_code', None) or getattr(getattr(error, 'response', None), 'status_code', None)
        status = status or getattr(getattr(error, 'response', None), 'status', None)
        if request_id is None and status is None:
            return
        logger.warning(
            'STT provider connect rejected provider=%s status=%s request_id=%s request_id_header=%s',
            bounded_stream_close_provider(provider),
            status if isinstance(status, int) and not isinstance(status, bool) else 'unknown',
            request_id or 'none',
            header or 'none',
        )
    except Exception:
        pass


def transport_closer(error: BaseException, sent: Any = None) -> Optional[str]:
    """Closer implied by a transport failure, or None when ``error`` is not one.

    A dropped connection or reset counts as ``vendor``: we did not end it, and
    the provider side or the network path to it did. The code class (1006 for
    no close frame) keeps a network drop separable from a vendor close frame.
    """
    sent = sent if sent is not None else getattr(error, 'sent', None)
    if getattr(sent, 'reason', None) == 'keepalive ping timeout':
        return US_TIMEOUT  # Our keepalive ping went unanswered; websockets closed it for us with 1011.
    if isinstance(error, TimeoutError):
        return US_TIMEOUT  # Our own write/connect bound expired.
    if type(error).__name__.startswith('ConnectionClosed') or isinstance(error, OSError):
        return VENDOR
    return None


def _close_frames(ws: Any, error: Optional[BaseException]) -> tuple[Any, Any]:
    received = getattr(error, 'rcvd', None) if error is not None else None
    sent = getattr(error, 'sent', None) if error is not None else None
    protocol = getattr(ws, 'protocol', None)  # asyncio client keeps frames on its protocol
    for owner in (ws, protocol):
        if owner is None:
            continue
        received = received or getattr(owner, 'close_rcvd', None)
        sent = sent or getattr(owner, 'close_sent', None)
    return received, sent


class ProviderStreamEnd:
    """One provider stream's end-of-life record. Every method is thread-safe and never raises."""

    def __init__(self, provider: str, ws: Any, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.provider = bounded_stream_close_provider(provider)
        self._ws = ws
        self._clock = clock
        self._opened_at = clock()
        self._lock = threading.Lock()
        self._recorded = False
        self._closing = False
        self._intent: Optional[str] = None
        self._vendor_reason: Optional[str] = None
        self._first_audio_at: Optional[float] = None
        self._first_text_seen = False
        self.request_id_header, self.request_id = handshake_request_id(ws)
        _log_handshake_header_names(self.provider, ws)

    @property
    def recorded(self) -> bool:
        return self._recorded

    @property
    def closing(self) -> bool:
        return self._closing

    def begin_close(self) -> None:
        """An owner is closing the transport and records after ``ws.close()``, once the close frames exist.

        From here ``finish()`` and transport errors defer to that owner, so our
        own close can neither latch early with no close code nor read as a vendor drop.
        """
        with self._lock:
            self._closing = True

    def record_after_drain(self, *, cancelled: bool, closer: Optional[str] = None) -> None:
        """An owner's drain ended. A cancelled one usually left ``ws.close()`` to the abort that follows.

        That abort records after its own close; this only backstops a cancel
        nobody aborts, after ``CANCELLED_DRAIN_RECORD_DELAY_SECONDS``.
        """
        if not cancelled:
            self.record(closer=closer)
            return
        try:
            asyncio.get_running_loop().call_later(
                CANCELLED_DRAIN_RECORD_DELAY_SECONDS, lambda: self.record(closer=closer)
            )
        except RuntimeError:
            self.record(closer=closer)

    def note_intent(self, closer: str) -> None:
        """The session's reason for closing this stream. The first intent wins."""
        if closer in CLOSERS and closer != VENDOR and self._intent is None:
            self._intent = closer

    def note_frame(self, msg: Mapping[str, Any]) -> None:
        if self.request_id is None:
            try:
                self.request_id = frame_request_id(msg)
            except Exception:
                pass

    def note_vendor_error(self, reason: Optional[str]) -> None:
        """A vendor error frame ended the stream. Recorded at close, once its close frame is visible."""
        if self._vendor_reason is None:
            self._vendor_reason = reason or 'untyped'

    def note_audio_sent(self) -> None:
        if self._first_audio_at is None:
            self._first_audio_at = self._clock()

    def note_text(self) -> None:
        if self._first_text_seen:
            return
        self._first_text_seen = True
        try:
            started = self._first_audio_at if self._first_audio_at is not None else self._opened_at
            OMI_STT_PROVIDER_FIRST_TEXT_SECONDS.labels(provider=self.provider).observe(
                max(0.0, self._clock() - started)
            )
        except Exception:
            pass

    def _closer(self, closer: Optional[str], sent: Any, error: Optional[BaseException]) -> Optional[str]:
        if closer in CLOSERS and closer != VENDOR:
            return closer
        if self._vendor_reason is not None:
            return VENDOR  # The vendor said why; that holds even while we drain.
        if closer == VENDOR:
            label: Optional[str] = VENDOR
        elif error is not None:
            label = transport_closer(error, sent)
        else:
            return self._intent or US_CLIENT_GONE
        # After SIGTERM a dropped leg died of our restart (FC-listen-cancellation-counted-as-provider-failure).
        return US_DRAIN if label == VENDOR and is_draining() else label

    def record(
        self,
        ws: Any = None,
        *,
        error: Optional[BaseException] = None,
        closer: Optional[str] = None,
        reason: Optional[str] = None,
        unless_closing: bool = False,
    ) -> bool:
        """Count and log this stream's end once. Returns whether this call recorded it.

        ``ws`` defaults to the transport the latch was opened with. An ``error``
        that is not a transport failure attributes nothing, and a transport
        error raised while an owner is closing defers to that owner's record:
        either way the latch stays open for the teardown. So does a clean EOF
        seen while an owner closes (that EOF is our own close), and an
        ``unless_closing`` record (``finish()`` with no owner) once an owner
        has begun closing; that check and ``begin_close()`` share the lock.
        """
        if ws is None:
            ws = self._ws
        try:
            received, sent = _close_frames(ws, error)
            label = self._closer(closer, sent, error)
        except Exception:
            received, sent, label = None, None, self._intent or US_CLIENT_GONE
        if label is None:
            return False
        with self._lock:
            if self._recorded:
                return False
            if self._closing and (unless_closing or error is not None or closer == VENDOR):
                return False
            self._recorded = True
        try:
            received_code, sent_code = frame_close_code(received), frame_close_code(sent)
            if received_code >= 0:
                code: Optional[int] = received_code
            elif sent_code >= 0:
                code = sent_code
            elif error is not None and type(error).__name__.startswith('ConnectionClosed'):
                code = 1006  # The transport dropped with no close frame either way.
            else:
                code = None
            code_class = close_code_class(code)
            OMI_STT_PROVIDER_STREAM_END_TOTAL.labels(provider=self.provider, closer=label, code_class=code_class).inc()
            close_reason = getattr(received, 'reason', None) or getattr(sent, 'reason', None)
            logger.log(
                logging.WARNING if label == VENDOR else logging.INFO,
                'STT provider stream end provider=%s closer=%s code_class=%s received_code=%s sent_code=%s '
                'reason=%s request_id=%s request_id_header=%s session_age_bucket=%s close_%s',
                self.provider,
                label,
                code_class,
                received_code,
                sent_code,
                reason or self._vendor_reason or 'none',
                self.request_id or 'none',
                self.request_id_header or 'none',
                session_age_bucket(self._clock() - self._opened_at),
                sanitize_provider_error(close_reason or '', code=code),
            )
        except Exception:
            pass
        return True


class _DetachedStreamEnd(ProviderStreamEnd):
    """Class-level stand-in for a socket built without ``__init__``: observes and records nothing."""

    def __init__(self) -> None:
        self.provider = 'unknown'
        self.request_id_header = self.request_id = None

    @property
    def recorded(self) -> bool:
        return True

    @property
    def closing(self) -> bool:
        return False

    def begin_close(self) -> None:
        pass

    def record_after_drain(self, *, cancelled: bool, closer: Optional[str] = None) -> None:
        pass

    def note_intent(self, closer: str) -> None:
        pass

    def note_frame(self, msg: Mapping[str, Any]) -> None:
        pass

    def note_vendor_error(self, reason: Optional[str]) -> None:
        pass

    def note_audio_sent(self) -> None:
        pass

    def note_text(self) -> None:
        pass

    def record(self, ws: Any = None, **_kwargs: Any) -> bool:
        return False


DETACHED_STREAM_END: ProviderStreamEnd = _DetachedStreamEnd()


def stream_end_of(socket: Any) -> Optional[ProviderStreamEnd]:
    """The innermost provider latch under listen's socket wrappers, if any."""
    current = socket
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            return None
        seen.add(id(current))
        stream_end = getattr(current, 'stream_end', None)
        if isinstance(stream_end, ProviderStreamEnd):
            return stream_end
        current = next(
            (
                inner
                for name in ('raw', '_conn', 'connection', '_transport')
                if (inner := getattr(current, name, None)) is not None and inner is not current
            ),
            None,
        )
    return None


def begin_stream_close(socket: Any) -> None:
    """An owner is about to close the provider transport under ``socket``. Never raises."""
    try:
        stream_end = stream_end_of(socket)
        if stream_end is not None:
            stream_end.begin_close()
    except Exception:
        pass


def record_stream_end(socket: Any) -> None:
    """Record the end of the provider stream under ``socket`` after its owner closed the transport. Never raises."""
    try:
        stream_end = stream_end_of(socket)
        if stream_end is not None:
            stream_end.record()
    except Exception:
        pass


def note_stream_close_intent(socket: Any, closer: str) -> None:
    """Tell the provider stream under ``socket`` why the session is about to close it. Never raises."""
    try:
        stream_end = stream_end_of(socket)
        if stream_end is not None:
            stream_end.note_intent(closer)
    except Exception:
        pass
