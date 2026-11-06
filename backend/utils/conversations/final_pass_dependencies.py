"""Typed dependency failures eligible for the capped speaker-only retry path."""

import errno

from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    InternalServerError,
    ServiceUnavailable,
    TooManyRequests,
)
import httpx

from database.storage_transport_errors import TLS_ERRORS, TRANSIENT_ERRORS
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit
from utils.stt.http_errors import has_tls_cause, retryable_http_error


def transient_cause(error):
    """Inspect explicit causes; nested TLS vetoes retry without message parsing."""
    if has_tls_cause(error, TLS_ERRORS):
        return None
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ArtifactReadLimit):
            # Structural limits cannot be repaired by another dependency call.
            if error.args != ('artifact read deadline',):
                return None
            if error.__cause__ is None:
                return error
        elif isinstance(error, httpx.HTTPStatusError):
            return error if retryable_http_error(error) else None
        elif isinstance(
            error,
            (
                Aborted,
                DeadlineExceeded,
                InternalServerError,
                ServiceUnavailable,
                TooManyRequests,  # Includes ResourceExhausted.
                ConnectionError,
                TimeoutError,
                httpx.TimeoutException,
                httpx.NetworkError,
                *TRANSIENT_ERRORS,
            ),
        ):
            return error
        elif isinstance(error, OSError) and error.errno in {
            errno.ECONNRESET,
            errno.ECONNABORTED,
            errno.ECONNREFUSED,
            errno.ETIMEDOUT,
            errno.EPIPE,
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
        }:
            return error
        error = error.__cause__
    return None
