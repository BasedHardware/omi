"""Bounded Firestore reads for the MCP request-gating authentication path.

Bearer-token lookups gate every MCP request and run synchronously on a shared
thread pool, so they must fail fast rather than wait out a Firestore outage: the
client's default retry deadline for a document read is 300 seconds, and an MCP
client that keeps retrying (connectors do) would pin one pool worker per
in-flight request for five minutes each until the pool is exhausted and every
other Firestore caller in the process stalls behind it.

A few seconds is far beyond a healthy auth read (tens of milliseconds) and far
below that failure mode. Exhausting the bounded retry raises a
``google.api_core`` error, which the MCP router turns into a 503 with
``Retry-After`` — a retryable "come back shortly", never a 401 that would make a
connector discard a perfectly good token over a transient backend problem.
"""

import os
from typing import Any

MCP_AUTH_DB_TIMEOUT_SECONDS = float(os.getenv("MCP_AUTH_DB_TIMEOUT_SECONDS", "5"))

_retry_policy: Any = None


def mcp_auth_db_retry() -> Any:
    """Return the bounded retry policy, built once on first use.

    Built lazily rather than at import time: ``google.api_core.retry`` drags in
    ``google.auth`` and its credential machinery, and this module sits on the
    import path of every MCP router. Keeping production imports cheap is the
    Tier-1 rule in ``docs/test_isolation.md``.
    """
    global _retry_policy
    if _retry_policy is None:
        from google.api_core import exceptions as google_api_exceptions
        from google.api_core import retry as google_api_retry

        _retry_policy = google_api_retry.Retry(
            # Bounding the deadline must not stop transient failures from being
            # retried at all — only cap how long that retrying may take.
            predicate=google_api_retry.if_exception_type(
                google_api_exceptions.ServiceUnavailable,
                google_api_exceptions.InternalServerError,
                google_api_exceptions.DeadlineExceeded,
                google_api_exceptions.ResourceExhausted,
                google_api_exceptions.Aborted,
            ),
            initial=0.2,
            maximum=1.0,
            multiplier=2.0,
            timeout=MCP_AUTH_DB_TIMEOUT_SECONDS,
        )
    return _retry_policy


def mcp_auth_read(reference: Any) -> Any:
    """Read a document on the auth path with the bounded deadline."""
    return reference.get(retry=mcp_auth_db_retry(), timeout=MCP_AUTH_DB_TIMEOUT_SECONDS)


def mcp_auth_stream(query: Any) -> Any:
    """Stream a query on the auth path with the bounded deadline."""
    return query.stream(retry=mcp_auth_db_retry(), timeout=MCP_AUTH_DB_TIMEOUT_SECONDS)
