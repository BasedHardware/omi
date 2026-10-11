"""Regression tests: MCP bearer-token auth must fail fast, and fail honestly.

Both halves matter, and both were live failures on 2026-08-23.

*Fail fast.* ``authenticate_mcp_request`` runs synchronously on the shared
``db_executor`` pool and gates every MCP request. The Firestore client retries a
document read for 300 seconds by default, so while the project's daily read
quota was exhausted each request parked one of the pool's 24 workers for five
minutes. An MCP connector retrying its handshake (claude.ai sent ~100 requests)
is therefore enough to exhaust the pool that the rest of the backend shares for
all of its Firestore work. The bounded retry in ``database.mcp_auth_read`` caps
that hold at a few seconds.

*Fail honestly.* Once the read gives up, the request must not be reported as
401: a connector told "unauthorized" throws its token away and restarts the
OAuth flow, which is a permanent, user-visible response to a transient backend
problem. 503 with ``Retry-After`` says the true thing.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from google.api_core import exceptions as google_api_exceptions
from google.api_core.exceptions import RetryError

from database import mcp_auth_read

_BACKEND = Path(__file__).resolve().parents[2]

# The default the bound exists to escape (google-cloud-firestore's retry
# deadline for batch_get_documents), asserted against rather than assumed.
FIRESTORE_DEFAULT_RETRY_DEADLINE_SECONDS = 300.0


class _SpyReference:
    """Records the read kwargs the auth path asks Firestore for."""

    def __init__(self):
        self.get_kwargs = None
        self.stream_kwargs = None

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return "snapshot"

    def stream(self, **kwargs):
        self.stream_kwargs = kwargs
        return iter(())


def test_auth_read_is_bounded():
    ref = _SpyReference()
    assert mcp_auth_read.mcp_auth_read(ref) == "snapshot"
    assert ref.get_kwargs == {
        "retry": mcp_auth_read.mcp_auth_db_retry(),
        "timeout": mcp_auth_read.MCP_AUTH_DB_TIMEOUT_SECONDS,
    }


def test_auth_stream_is_bounded():
    ref = _SpyReference()
    list(mcp_auth_read.mcp_auth_stream(ref))
    assert ref.stream_kwargs == {
        "retry": mcp_auth_read.mcp_auth_db_retry(),
        "timeout": mcp_auth_read.MCP_AUTH_DB_TIMEOUT_SECONDS,
    }


def test_auth_deadline_stays_far_below_the_firestore_default():
    """A worker must be released in seconds, not in the default five minutes."""
    assert 0 < mcp_auth_read.MCP_AUTH_DB_TIMEOUT_SECONDS <= 15
    assert mcp_auth_read.mcp_auth_db_retry()._timeout == mcp_auth_read.MCP_AUTH_DB_TIMEOUT_SECONDS
    assert mcp_auth_read.mcp_auth_db_retry()._timeout < FIRESTORE_DEFAULT_RETRY_DEADLINE_SECONDS / 10


@pytest.mark.parametrize(
    "error",
    [
        # The one that actually happened: Firestore daily quota exhausted.
        google_api_exceptions.ResourceExhausted("429 Quota exceeded."),
        google_api_exceptions.ServiceUnavailable("503"),
        google_api_exceptions.InternalServerError("500"),
    ],
)
def test_auth_retry_still_retries_transient_errors(error):
    """Bounding the deadline must not turn off retrying — only cap how long."""
    assert mcp_auth_read.mcp_auth_db_retry()._predicate(error) is True


def test_auth_retry_does_not_retry_permanent_errors():
    assert mcp_auth_read.mcp_auth_db_retry()._predicate(google_api_exceptions.NotFound("404")) is False


@pytest.fixture()
def mcp_sse():
    from routers import mcp_sse as module

    return module


def _quota_retry_error():
    return RetryError(
        "Timeout of 300.0s exceeded, last exception: 429 Quota exceeded.",
        cause=google_api_exceptions.ResourceExhausted("429 Quota exceeded."),
    )


def test_oauth_token_store_outage_is_503_not_401(mcp_sse, monkeypatch):
    def boom(*_args, **_kwargs):
        raise _quota_retry_error()

    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "validate_access_token", boom)

    with pytest.raises(HTTPException) as excinfo:
        mcp_sse.authenticate_mcp_request("Bearer some-oauth-access-token")

    assert excinfo.value.status_code == 503
    assert excinfo.value.headers["Retry-After"] == str(mcp_sse.MCP_AUTH_UNAVAILABLE_RETRY_AFTER_SECONDS)


def test_legacy_key_store_outage_is_503_not_401(mcp_sse, monkeypatch):
    def boom(*_args, **_kwargs):
        raise google_api_exceptions.ResourceExhausted("429 Quota exceeded.")

    monkeypatch.setattr(mcp_sse.mcp_api_key_db, "get_api_key_auth_result", boom)

    with pytest.raises(HTTPException) as excinfo:
        mcp_sse.authenticate_mcp_request("Bearer omi_mcp_deadbeef")

    assert excinfo.value.status_code == 503


def test_reachable_store_still_rejects_an_unknown_token(mcp_sse, monkeypatch):
    """The 401 path is unchanged: only an unreachable store becomes a 503."""
    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "validate_access_token", lambda *a, **k: None)

    assert mcp_sse.authenticate_mcp_request("Bearer unknown-token") is None


def test_missing_authorization_header_still_returns_none(mcp_sse):
    assert mcp_sse.authenticate_mcp_request(None) is None


def test_importing_the_helper_stays_cheap():
    """The retry policy is built on first use, not at import.

    ``google.api_core.retry`` pulls in ``google.auth`` and its credential
    machinery. This module sits on the import path of every MCP router, and
    tests exercise those routers against a stubbed ``google`` namespace, so an
    import-time dependency here would be paid — and would break — everywhere.
    """
    probe = (
        "import sys, database.mcp_auth_read;"
        "print('google.api_core.retry' in sys.modules, 'google.auth' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False False", result.stdout
