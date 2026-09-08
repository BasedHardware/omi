"""Mid-stream retry decisions for Firestore query streams.

Regression: google-cloud-firestore resolves the RunQuery retry policy from
``transport.run_query``, which is the raw gRPC stub and carries no ``_retry``.
Every retryable error raised while a stream was being consumed therefore died
with ``AttributeError: '_UnaryStreamMultiCallable' object has no attribute
'_retry'`` instead of resuming the stream, and any read that streams a
collection (staged tasks, action items) answered the user with a 500.
"""

import builtins
from typing import Any

import pytest
from google.api_core import gapic_v1
from google.api_core.exceptions import InvalidArgument, ServiceUnavailable
from google.cloud.firestore_v1.query import Query

import database._client  # importing installs the retry-resolution fix


class _RawStub:
    """The generated transport's ``run_query``: a bare callable with no ``_retry``."""


class _WrappedMethod:
    def __init__(self, retry: Any) -> None:
        self._retry = retry


class _Retry:
    def __init__(self, predicate: Any) -> None:
        self._predicate = predicate


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, ServiceUnavailable)


def _query(*, wrapped: bool = True) -> Any:
    """A stand-in for a Query bound to the transport shape the SDK actually builds."""
    stub = _RawStub()

    class _Transport:
        run_query = stub
        _wrapped_methods = {stub: _WrappedMethod(_Retry(_transient))} if wrapped else {}

    class _Api:
        _transport = _Transport()

    class _Client:
        _firestore_api = _Api()

    class _Query:
        _client = _Client()

    return _Query()


def test_raw_stub_carries_no_retry_policy():
    """The shape that broke the SDK lookup — the raw stub has no ``_retry``."""
    with pytest.raises(AttributeError):
        _query()._client._firestore_api._transport.run_query._retry


def test_transient_error_resumes_the_stream():
    assert (
        Query._retry_query_after_exception(
            _query(), ServiceUnavailable('backend unavailable'), gapic_v1.method.DEFAULT, None
        )
        is True
    )


def test_permanent_error_is_raised_to_the_caller():
    assert (
        Query._retry_query_after_exception(_query(), InvalidArgument('bad query'), gapic_v1.method.DEFAULT, None)
        is False
    )


def test_unresolvable_policy_surfaces_the_original_error():
    """No policy anywhere: still a decision, never an AttributeError over the real fault."""
    assert (
        Query._retry_query_after_exception(
            _query(wrapped=False), ServiceUnavailable('backend unavailable'), gapic_v1.method.DEFAULT, None
        )
        is False
    )


def test_caller_supplied_retry_is_honoured():
    caller_retry = _Retry(lambda exc: isinstance(exc, InvalidArgument))
    assert Query._retry_query_after_exception(_query(), InvalidArgument('bad query'), caller_retry, None) is True


def test_transaction_never_snapshot_retries():
    assert (
        Query._retry_query_after_exception(
            _query(), ServiceUnavailable('backend unavailable'), gapic_v1.method.DEFAULT, object()
        )
        is False
    )


def test_install_is_a_noop_when_the_sdk_is_unreachable(monkeypatch):
    """Importing ``database._client`` must survive a stubbed ``google`` namespace.

    Unit harnesses (``testing.import_isolation.stub_modules``) replace ``google`` with a
    package whose ``__path__`` is empty, so ``firestore_v1``/``gapic_v1`` — and the
    ``google.auth`` they pull in — cannot resolve. Resolving them at module scope broke
    the import of five unrelated unit files; the install has to skip instead.
    """
    real_import = builtins.__import__

    def _no_firestore_sdk(name, *args, **kwargs):
        if name.startswith('google.cloud.firestore_v1'):
            raise ModuleNotFoundError("No module named 'google.auth'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', _no_firestore_sdk)
    assert database._client._install_query_stream_retry_compat() is None
