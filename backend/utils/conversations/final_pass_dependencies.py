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
import requests

from utils.batch_pipeline.artifact_reads import ArtifactReadLimit


def transient_cause(error):
    """Inspect explicit causes only; never parse provider/user error messages."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ArtifactReadLimit):
            # Structural limits cannot be repaired by another dependency call.
            if error.args != ('artifact read deadline',):
                return None
            if error.__cause__ is None:
                return error
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
                requests.exceptions.Timeout,
            ),
        ):
            return error
        elif isinstance(error, requests.exceptions.ConnectionError) and not isinstance(
            error, requests.exceptions.SSLError
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
