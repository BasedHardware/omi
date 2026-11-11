"""Regression test: the OAuth callback ``error`` param must not become an
unbounded Prometheus label value.

``routers/auth.py``'s Google/Apple callback handlers echo the provider's
``error`` query/form parameter straight into ``AUTH_FLOW_EVENTS.labels(...)``
via ``failure_class``. That endpoint requires no prior authentication (it is
the public OAuth redirect target), so an attacker fully controls the raw
string. ``prometheus_client`` never evicts a label-value combination once
seen — ``Counter._metrics`` is a plain dict that only grows for the life of
the process — so every distinct ``error=`` value an attacker sends creates a
brand-new, permanent time series on ``auth_flow_events_total``. That is
exactly the "Prometheus labels: static low-cardinality only ... never
uid/session_id"-style violation backend/AGENTS.md calls out, just carried by
a free-form provider error string instead of a uid.

The fix bounds the echoed value to the closed RFC 6749 §4.1.2.1 OAuth error
vocabulary (``_bounded_provider_error``), defaulting anything else to a
single ``"provider_error_other"`` bucket.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "omi_test_secret_for_ci_only_0123456789")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake")

# Sanctioned pattern (backend/docs/test_isolation.md): import the router module
# normally at module scope. No sys.modules mutation, no import-hook stubbing —
# routers.auth is import-pure and its real deps (firebase_admin, jwt,
# cryptography) are already installed.
import routers.auth as auth_mod  # noqa: E402
from utils.metrics import AUTH_FLOW_EVENTS  # noqa: E402

_ATTACKER_VALUE_COUNT = 40


def _series_count() -> int:
    """Number of distinct label-value combinations Counter has ever recorded.

    ``prometheus_client`` caches one child metric per unique label tuple in
    ``Counter._metrics`` and never evicts it — this is the process-lifetime
    structure whose growth we are bounding.
    """
    return len(AUTH_FLOW_EVENTS._metrics)


async def _drive_google_callback(request, error_values):
    """Fire the real (unauthenticated) callback handler for every value on one
    event loop, the way concurrent attacker requests would actually arrive."""

    async def _one(error_value):
        try:
            await auth_mod.auth_callback_google(request=request, code=None, state=None, error=error_value)
        except HTTPException:
            pass

    await asyncio.gather(*(_one(value) for value in error_values))


def _run(coro):
    # Match this test suite's established idiom (see test_auth_redirect_uri.py):
    # reuse/extend the current event loop rather than asyncio.run(), which closes
    # its loop and clears the thread's "current loop" — that would break sibling
    # test files that still call asyncio.get_event_loop().run_until_complete(...)
    # after this module runs in the same pytest session.
    return asyncio.get_event_loop().run_until_complete(coro)


class TestGoogleCallbackFailureClassCardinality:
    def test_distinct_attacker_error_values_do_not_grow_cardinality_unboundedly(self):
        """Bug path: N distinct, attacker-chosen ``error=`` values must collapse
        into a small bounded set of label values, not N new series."""
        request = MagicMock()
        before = _series_count()

        values = [f"unique-payload-{i}" for i in range(_ATTACKER_VALUE_COUNT)]
        _run(_drive_google_callback(request, values))

        growth = _series_count() - before
        assert growth <= 5, (
            f"AUTH_FLOW_EVENTS grew by {growth} distinct series for {_ATTACKER_VALUE_COUNT} distinct "
            f"attacker-controlled error values (expected a small bounded bucket, "
            f"not one series per request)"
        )

    def test_repeated_known_error_value_does_not_grow_cardinality(self):
        """Sibling normal-path case: a real provider sending the same standard
        OAuth error code repeatedly must not grow cardinality either — this
        passes on both the fixed and unfixed code, since a Counter never grows
        cardinality for a *repeated* label tuple."""
        request = MagicMock()
        before = _series_count()

        values = ["access_denied"] * _ATTACKER_VALUE_COUNT
        _run(_drive_google_callback(request, values))

        growth = _series_count() - before
        assert growth <= 1, f"AUTH_FLOW_EVENTS grew by {growth} for {_ATTACKER_VALUE_COUNT} calls with the same value"


class TestBoundedProviderErrorHelper:
    """Direct check that the bounding helper itself has a closed output range."""

    def test_arbitrary_input_maps_into_closed_set(self):
        outputs = {auth_mod._bounded_provider_error(f"garbage-{i}") for i in range(_ATTACKER_VALUE_COUNT)}
        allowed = auth_mod._OAUTH_ERROR_CODES | {"provider_error_other"}
        assert outputs <= allowed
        # Many distinct garbage inputs must not produce many distinct outputs.
        assert len(outputs) <= 1

    def test_known_oauth_codes_pass_through_unchanged(self):
        for code in auth_mod._OAUTH_ERROR_CODES:
            assert auth_mod._bounded_provider_error(code) == code

    def test_case_and_whitespace_normalized(self):
        assert auth_mod._bounded_provider_error("  Access_Denied  ") == "access_denied"
