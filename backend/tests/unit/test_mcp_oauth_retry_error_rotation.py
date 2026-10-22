"""A drained SDK retry budget no longer skips the MCP rotation's three-attempt budget.

Failure-Class: FC-drained-sdk-retry-budget-escapes-transient-class (declared
with the recording-session boundaries in
``test_firestore_retry_error_envelope_transient.py``; this file pins the same
class at the MCP OAuth refresh-rotation boundary). ``rotate_refresh_token``
owns a three-attempt budget over exactly the shapes a redial can answer
(``Aborted``, 503, 504, the expired-id ``InvalidArgument``; Firestore wraps
exhausted commit aborts in ``ValueError``). The Firestore transport, however,
retries every RPC itself on its availability set for ~60s and raises
``google.api_core.exceptions.RetryError`` — with the last fault chained as its
cause — when that budget drains. ``RetryError`` extends ``GoogleAPIError``,
not ``GoogleAPICallError``, so it matched none of the caught shapes: a
sustained-but-recovering data-plane fault skipped the boundary's own budget
entirely and propagated raw into the router, whose ``except`` maps only
``RefreshRotationUnavailable`` to the connector-facing 503 — every other
exception surfaces as a 500 on the token endpoint. The boundary now reads one
level through the envelope: an enveloped 503/504 consumes the budget
(attempt warnings, the inter-attempt sleeps, and the terminal
``RefreshRotationUnavailable`` — the honest 503), while an envelope around a
permanent refusal or with no transient evidence still raises; bare permanent
failures, quota envelopes, and every pre-existing verdict are unchanged.

Guards:
- the real SDK's own ``retry_target``, drained on the Firestore transport's
  predicate, produces exactly the envelope the boundary now consumes;
- an enveloped 503 uses the full budget: two retry warnings, both sleeps, and
  ``RefreshRotationUnavailable`` chained from the last envelope — the router's
  ``except`` then yields the honest 503 instead of a 500;
- a single enveloped 503 that clears on the second attempt rotates and never
  reaches the terminal raise;
- an envelope around ``PermissionDenied``, a quota
  (``ResourceExhausted``) envelope, and a cause-less envelope still propagate
  (permanent or evidence-free is not transient), as do bare
  ``PermissionDenied`` and bare ``ValueError`` wrapping a real error;
- the expired-id and aborted-commit shapes still replay exactly as before
  (the envelope read-through must not shadow them), including the
  ``ValueError``-wraps-abort form the boundary already decoded;
- a clean rotation commits untouched.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from google.api_core import retry as api_retry
from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    InternalServerError,
    InvalidArgument,
    PermissionDenied,
    ResourceExhausted,
    RetryError,
    ServiceUnavailable,
)

from database import mcp_oauth

_ROTATE = "rotate_refresh_token"


def _drain_real_retry(leaf: Callable[[], Any], timeout: float = 0.1) -> Any:
    """Drain a retry budget mirroring the Firestore transport's predicate."""
    predicate = api_retry.if_exception_type(
        DeadlineExceeded, InternalServerError, ResourceExhausted, ServiceUnavailable
    )
    return api_retry.retry_target(leaf, predicate, iter([0.03] * 10), timeout=timeout, on_error=None)


class _FakeDocumentRef:
    def __init__(self, harness: "_RotationHarness") -> None:
        self.harness = harness

    def get(self, transaction: Any = None) -> Any:
        del transaction
        return self.harness.snapshot()

    def set(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


class _FakeCollectionRef:
    def __init__(self, harness: "_RotationHarness") -> None:
        self.harness = harness

    def document(self, document_id: str) -> _FakeDocumentRef:
        del document_id
        return _FakeDocumentRef(self.harness)


class _FakeStore:
    """Stands in for the data-plane Firestore client at the rotation boundary.

    ``rotate_refresh_token`` resolves ``db.collection(...).document(...)`` at
    entry, so the store — not just the transaction — must be substituted to
    keep the suite hermetic.
    """

    def __init__(self, harness: "_RotationHarness") -> None:
        self.harness = harness

    def collection(self, name: str) -> _FakeCollectionRef:
        del name
        return _FakeCollectionRef(self.harness)

    def transaction(self, **kwargs: Any) -> Any:
        del kwargs
        return object()


class _RotationHarness:
    """Substitutes ``rotate_refresh_token``'s transactional body.

    The bodies, budgets and classification of the real boundary stay
    production code; only the Firestore round-trip is replaced: the queue
    raises one exception per ``_rotate`` call (transaction start), then
    returns the queued result.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> None:
        self.sleeps: list[float] = []
        self.calls = 0
        self._outcomes = iter(outcomes)

        def fake_body(transaction: Any, *args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            self.calls += 1
            outcome = next(self._outcomes)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(mcp_oauth.firestore, "transactional", lambda func: fake_body)
        monkeypatch.setattr(mcp_oauth, "db", _FakeStore(self))
        monkeypatch.setattr(mcp_oauth.time, "sleep", self.sleeps.append)

    def snapshot(self) -> Any:
        raise AssertionError("a queued outcome must raise before the body reads")

    def rotate(self) -> Any:
        return mcp_oauth.rotate_refresh_token("token", "client", None)


def test_drained_transport_budget_produces_the_envelope():
    """SDK truth: the exact shape this boundary receives, from the SDK itself."""
    calls = {"n": 0}

    def leaf() -> None:
        calls["n"] += 1
        raise ServiceUnavailable("503: backend unavailable")

    with pytest.raises(RetryError) as excinfo:
        _drain_real_retry(leaf)

    assert calls["n"] >= 2
    assert isinstance(excinfo.value.cause, ServiceUnavailable)


def test_enveloped_503_consumes_the_full_budget_and_fails_honestly(monkeypatch):
    harness = _RotationHarness(monkeypatch, [RetryError("Timeout of 60.0s exceeded", ServiceUnavailable("503"))] * 3)

    with pytest.raises(mcp_oauth.RefreshRotationUnavailable) as excinfo:
        harness.rotate()

    assert harness.calls == 3
    assert harness.sleeps == [0.1, 0.3]
    assert isinstance(excinfo.value.__cause__, RetryError)


def test_single_enveloped_503_that_clears_rotates(monkeypatch):
    envelope = RetryError("Timeout of 60.0s exceeded", ServiceUnavailable("503"))
    harness = _RotationHarness(monkeypatch, [envelope, {"access_token": "at", "refresh_token": "rt"}])

    result = harness.rotate()

    assert result == {"access_token": "at", "refresh_token": "rt"}
    assert harness.calls == 2
    assert harness.sleeps == [0.1]


def test_envelope_around_permission_denied_still_raises(monkeypatch):
    """The envelope re-raises as itself; its cause still names the refusal."""
    envelope = RetryError("Timeout of 60.0s exceeded", PermissionDenied("permission denied on row"))
    harness = _RotationHarness(monkeypatch, [envelope] * 3)

    with pytest.raises(RetryError) as excinfo:
        harness.rotate()

    assert isinstance(excinfo.value.cause, PermissionDenied)
    assert harness.calls == 1
    assert harness.sleeps == []


def test_quota_envelope_still_raises(monkeypatch):
    envelope = RetryError("Timeout of 60.0s exceeded", ResourceExhausted("429: quota"))
    harness = _RotationHarness(monkeypatch, [envelope] * 3)

    with pytest.raises(RetryError) as excinfo:
        harness.rotate()

    assert isinstance(excinfo.value.cause, ResourceExhausted)
    assert harness.calls == 1


def test_causeless_envelope_still_raises(monkeypatch):
    harness = _RotationHarness(monkeypatch, [RetryError("Unknown error", None)] * 3)

    with pytest.raises(RetryError):
        harness.rotate()

    assert harness.calls == 1


def test_bare_permission_denied_still_raises(monkeypatch):
    harness = _RotationHarness(monkeypatch, [PermissionDenied("permission denied on row")] * 3)

    with pytest.raises(PermissionDenied):
        harness.rotate()

    assert harness.calls == 1


def test_value_error_wrapping_a_real_error_still_propagates(monkeypatch):
    real = RuntimeError("not a firestore shape")
    wrapped = ValueError("attempt retries exhausted")
    wrapped.__cause__ = real
    harness = _RotationHarness(monkeypatch, [wrapped] * 3)

    with pytest.raises(ValueError):
        harness.rotate()

    assert harness.calls == 1


@pytest.mark.parametrize(
    ("shape", "enveloped"),
    [
        (InvalidArgument("The referenced transaction has expired or is no longer valid"), False),
        (Aborted("contention"), False),
        (RetryError("Timeout of 60.0s exceeded", Aborted("contention")), True),
        (RetryError("Timeout of 60.0s exceeded", InvalidArgument("The referenced transaction has expired")), True),
    ],
    ids=["expired-id", "aborted", "enveloped-aborted", "enveloped-expired-id"],
)
def test_contention_and_expired_id_shapes_replay_unchanged(monkeypatch, shape, enveloped):
    """The envelope read-through must not shadow the shapes already budgeted;
    enveloped contention/expired-id now ride the same budget."""
    harness = _RotationHarness(monkeypatch, [shape, {"rotated": True}])

    assert harness.rotate() == {"rotated": True}
    assert harness.calls == 2
    assert harness.sleeps == [0.1]


def test_enveloped_expired_id_exhaustion_raises_refresh_unavailable(monkeypatch):
    envelope = RetryError(
        "Timeout of 60.0s exceeded",
        InvalidArgument("The referenced transaction has expired or is no longer valid"),
    )
    harness = _RotationHarness(monkeypatch, [envelope] * 3)

    with pytest.raises(mcp_oauth.RefreshRotationUnavailable):
        harness.rotate()

    assert harness.calls == 3
    assert harness.sleeps == [0.1, 0.3]


def test_clean_rotation_commits_untouched(monkeypatch):
    harness = _RotationHarness(monkeypatch, [{"access_token": "at", "refresh_token": "rt"}])

    assert harness.rotate() == {"access_token": "at", "refresh_token": "rt"}
    assert harness.calls == 1
    assert harness.sleeps == []
