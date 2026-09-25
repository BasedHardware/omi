"""Closed vocabularies shared by sync telemetry emitters.

Kept under ``config`` so ``database`` and ``utils.sync`` bound diagnostic
fields against one source: anything outside these sets collapses to a bounded
token and can never carry caller-controlled text into structured logs.
"""

from __future__ import annotations

import uuid

SYNC_PHASE_TOKENS = frozenset(
    {
        'download',
        'decode',
        'vad',
        'provider_select',
        'provider_call',
        'parse',
        'assignment',
        'persistence',
        'postprocess',
        'usage',
        'finalize',
        'unknown',
    }
)

SYNC_EXCEPTION_CLASSES = frozenset(
    {
        'AssertionError',
        'AttributeError',
        'BrokenPipeError',
        'CancelledError',
        'ConnectionError',
        'EOFError',
        'IndexError',
        'JSONDecodeError',
        'KeyError',
        'OSError',
        'RuntimeError',
        'StopAsyncIteration',
        'StopIteration',
        'TimeoutError',
        'TypeError',
        'UnicodeDecodeError',
        'ValueError',
        'ConnectError',
        'ConnectTimeout',
        'DecodingError',
        'HTTPError',
        'HTTPStatusError',
        'InvalidURL',
        'LocalProtocolError',
        'NetworkError',
        'PoolTimeout',
        'ProtocolError',
        'ProxyError',
        'ReadError',
        'ReadTimeout',
        'RemoteProtocolError',
        'RequestError',
        'StreamError',
        'TimeoutException',
        'TooManyRedirects',
        'TransportError',
        'WriteError',
        'WriteTimeout',
        'HTTPException',
        'WebSocketException',
        'ValidationError',
        'CouldntDecodeError',
        'OpusError',
        'Aborted',
        'AlreadyExists',
        'DeadlineExceeded',
        'FailedPrecondition',
        'GoogleAPICallError',
        'InvalidArgument',
        'NotFound',
        'PermissionDenied',
        'ResourceExhausted',
        'RetryError',
        'ServiceUnavailable',
        'Unauthenticated',
        'RedisError',
        'DestructiveOperationInProgress',
        'PrerecordedSTTConfigurationError',
        'SyncAssignmentSuperseded',
        'SyncConversationPersistenceFenced',
        'SyncJobRunLeaseLost',
        'TranscriptionFailure',
        'OtherException',
    }
)


def bounded_sync_phase(phase: object) -> str:
    """A closed phase token, ``none`` when no failure context exists."""
    if phase is None or phase == 'none':
        return 'none'
    return phase if isinstance(phase, str) and phase in SYNC_PHASE_TOKENS else 'unknown'


def bounded_exception_class(error: object) -> str:
    """Map an exception (or a pre-bounded token) to the closed class set."""
    if error is None or error == 'none':
        return 'none'
    name = type(error).__name__ if isinstance(error, BaseException) else str(error)
    return name if name in SYNC_EXCEPTION_CLASSES else 'OtherException'


def bounded_correlation_ref(value: object) -> str:
    """Opaque correlation is allowed only for UUIDv4 identifiers (hex form)."""
    if not isinstance(value, str):
        return 'none'
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return 'none'
    return parsed.hex if parsed.version == 4 else 'none'


def new_attempt_ref() -> str:
    """Random attempt correlation for one coordinator invocation."""
    return uuid.uuid4().hex
