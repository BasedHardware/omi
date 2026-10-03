"""Hermetic unit tests for Firestore transaction contention retry logic."""

import math
from typing import Any
import pytest

from database.firestore_transaction_retry import (
    DEFAULT_MAX_ATTEMPTS,
    FirestoreAborted,
    FirestoreContentionExhausted,
    is_transaction_contention,
    run_with_transaction_contention_retry,
)


class DummyCustomConflict(Exception):
    """Custom exception simulating contention."""
    pass


class DummyStatusError(Exception):
    def __init__(self, code=None, status_code=None, grpc_status_code=None):
        super().__init__(f"code={code}, status_code={status_code}, grpc={grpc_status_code}")
        self.code = code
        self.status_code = status_code
        self.grpc_status_code = grpc_status_code


class DummyExceptionGroup(Exception):
    def __init__(self, message: str, exceptions: list[BaseException]):
        super().__init__(message)
        self.exceptions = exceptions


class DummyTransaction:
    """Mock transaction passed to operation."""
    pass


def test_is_transaction_contention_non_exception():
    assert not is_transaction_contention(None)  # type: ignore
    assert not is_transaction_contention("error")  # type: ignore
    assert not is_transaction_contention(409)  # type: ignore
    assert not is_transaction_contention({})  # type: ignore


def test_is_transaction_contention_direct_types():
    assert is_transaction_contention(FirestoreAborted("aborted"))
    
    class Aborted(Exception):
        pass
    assert is_transaction_contention(Aborted("contention"))

    class Conflict(Exception):
        pass
    assert is_transaction_contention(Conflict("conflict"))


def test_is_transaction_contention_status_codes():
    # code attribute matches
    assert is_transaction_contention(DummyStatusError(code=409))
    assert is_transaction_contention(DummyStatusError(code="409"))
    assert is_transaction_contention(DummyStatusError(code="ABORTED"))
    assert is_transaction_contention(DummyStatusError(code=10))

    # status_code attribute matches
    assert is_transaction_contention(DummyStatusError(status_code=409))
    assert is_transaction_contention(DummyStatusError(status_code="409"))
    assert is_transaction_contention(DummyStatusError(status_code=10))

    # grpc_status_code attribute matches
    assert is_transaction_contention(DummyStatusError(grpc_status_code=10))
    assert is_transaction_contention(DummyStatusError(grpc_status_code="10"))
    assert is_transaction_contention(DummyStatusError(grpc_status_code=409))

    # non-contention codes
    assert not is_transaction_contention(DummyStatusError(code=500))
    assert not is_transaction_contention(DummyStatusError(status_code=404))
    assert not is_transaction_contention(DummyStatusError(grpc_status_code=14))


def test_is_transaction_contention_cause_traversal():
    root = FirestoreAborted("contention")
    wrapper1 = RuntimeError("wrapper 1")
    wrapper1.__cause__ = root
    wrapper2 = ValueError("wrapper 2")
    wrapper2.__cause__ = wrapper1

    assert is_transaction_contention(wrapper2)


def test_is_transaction_contention_context_does_not_retry():
    # Implicit __context__ from an except block should NOT make replacement errors retryable
    root = DummyStatusError(code=409)
    try:
        try:
            raise root
        except Exception:
            raise RuntimeError("replacement failure")
    except Exception as wrapped:
        assert not is_transaction_contention(wrapped)


def test_is_transaction_contention_circular_references():
    err1 = RuntimeError("error 1")
    err2 = RuntimeError("error 2")
    err1.__cause__ = err2
    err2.__cause__ = err1

    # Should safely terminate and return False without recursion error
    assert not is_transaction_contention(err1)

    # Now link one in cycle to a contention cause
    err3 = DummyStatusError(code=409)
    err2.__cause__ = err3
    assert is_transaction_contention(err1)


def test_is_transaction_contention_exception_group():
    err1 = ValueError("irrelevant")
    err2 = DummyStatusError(status_code=409)
    group = DummyExceptionGroup("group", [err1, err2])

    assert is_transaction_contention(group)


def test_is_transaction_contention_unrelated_errors():
    assert not is_transaction_contention(ValueError("generic error"))
    assert not is_transaction_contention(KeyError("missing key"))
    assert not is_transaction_contention(RuntimeError("something else"))


def test_retry_successful_first_attempt():
    tx = DummyTransaction()
    tx_calls = 0
    op_calls = 0

    def factory():
        nonlocal tx_calls
        tx_calls += 1
        return tx

    def op(t):
        nonlocal op_calls
        op_calls += 1
        assert t is tx
        return "success"

    slept = []
    res = run_with_transaction_contention_retry(
        transaction_factory=factory,
        operation=op,
        operation_name="test_op",
        sleep=slept.append,
    )
    assert res == "success"
    assert tx_calls == 1
    assert op_calls == 1
    assert slept == []


def test_retry_recovers_after_contention():
    tx = DummyTransaction()
    attempts = 0

    def factory():
        return tx

    def op(t):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise DummyStatusError(code=409)
        return "recovered"

    slept = []
    res = run_with_transaction_contention_retry(
        transaction_factory=factory,
        operation=op,
        operation_name="recover_op",
        max_attempts=5,
        sleep=slept.append,
        random_value=lambda: 0.5,
    )
    assert res == "recovered"
    assert attempts == 3
    assert len(slept) == 2


def test_retry_exhausted_raises_exception():
    tx = DummyTransaction()
    attempts = 0

    def factory():
        return tx

    def op(t):
        nonlocal attempts
        attempts += 1
        raise FirestoreAborted("contention forever")

    slept = []
    with pytest.raises(FirestoreContentionExhausted) as exc_info:
        run_with_transaction_contention_retry(
            transaction_factory=factory,
            operation=op,
            operation_name="exhausted_op",
            max_attempts=3,
            sleep=slept.append,
        )

    assert "Firestore transaction contention exhausted for exhausted_op" in str(exc_info.value)
    assert attempts == 3
    assert len(slept) == 2
    assert isinstance(exc_info.value.__cause__, FirestoreAborted)


def test_retry_unrelated_exception_raised_immediately():
    attempts = 0

    def factory():
        return DummyTransaction()

    def op(t):
        nonlocal attempts
        attempts += 1
        raise ValueError("fatal logic error")

    slept = []
    with pytest.raises(ValueError, match="fatal logic error"):
        run_with_transaction_contention_retry(
            transaction_factory=factory,
            operation=op,
            operation_name="fail_fast_op",
            max_attempts=5,
            sleep=slept.append,
        )

    assert attempts == 1
    assert slept == []


@pytest.mark.parametrize("invalid_max_attempts", [0, -1, True, False, 1.5, "3", None])
def test_retry_invalid_max_attempts(invalid_max_attempts):
    with pytest.raises(ValueError, match="max_attempts must be positive"):
        run_with_transaction_contention_retry(
            transaction_factory=lambda: None,
            operation=lambda _: None,
            operation_name="valid_name",
            max_attempts=invalid_max_attempts,  # type: ignore
        )


@pytest.mark.parametrize("invalid_op_name", ["", "   ", None, 123])
def test_retry_invalid_operation_name(invalid_op_name):
    with pytest.raises(ValueError, match="operation_name must be a non-empty string"):
        run_with_transaction_contention_retry(
            transaction_factory=lambda: None,
            operation=lambda _: None,
            operation_name=invalid_op_name,  # type: ignore
        )


def test_retry_non_callable_arguments():
    with pytest.raises(TypeError, match="transaction_factory must be callable"):
        run_with_transaction_contention_retry(
            transaction_factory="not_callable",  # type: ignore
            operation=lambda _: None,
            operation_name="valid",
        )

    with pytest.raises(TypeError, match="operation must be callable"):
        run_with_transaction_contention_retry(
            transaction_factory=lambda: None,
            operation="not_callable",  # type: ignore
            operation_name="valid",
        )

    with pytest.raises(TypeError, match="sleep must be callable"):
        run_with_transaction_contention_retry(
            transaction_factory=lambda: None,
            operation=lambda _: None,
            operation_name="valid",
            sleep="not_callable",  # type: ignore
        )

    with pytest.raises(TypeError, match="random_value must be callable"):
        run_with_transaction_contention_retry(
            transaction_factory=lambda: None,
            operation=lambda _: None,
            operation_name="valid",
            random_value="not_callable",  # type: ignore
        )

    with pytest.raises(TypeError, match="on_retry must be callable"):
        run_with_transaction_contention_retry(
            transaction_factory=lambda: None,
            operation=lambda _: None,
            operation_name="valid",
            on_retry="not_callable",  # type: ignore
        )


def test_retry_nan_inf_jitter_safety():
    attempts = 0

    def op(t):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FirestoreAborted("retry")
        return "done"

    slept = []
    # Test NaN returned by random_value
    res = run_with_transaction_contention_retry(
        transaction_factory=lambda: None,
        operation=op,
        operation_name="jitter_nan",
        sleep=slept.append,
        random_value=lambda: float("nan"),
    )
    assert res == "done"
    assert len(slept) == 1
    assert not math.isnan(slept[0])
    assert not math.isinf(slept[0])
    assert slept[0] > 0


def test_retry_on_retry_callback_invoked_and_isolated():
    on_retry_calls = []

    def handle_retry(attempt: int, error: BaseException, delay: float):
        on_retry_calls.append((attempt, error, delay))
        raise RuntimeError("callback crashed intentionally")

    attempts = 0

    def op(t):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise FirestoreAborted("contention")
        return "success"

    slept = []
    res = run_with_transaction_contention_retry(
        transaction_factory=lambda: None,
        operation=op,
        operation_name="callback_test",
        sleep=slept.append,
        on_retry=handle_retry,
    )
    assert res == "success"
    assert len(on_retry_calls) == 2
    assert on_retry_calls[0][0] == 1
    assert isinstance(on_retry_calls[0][1], FirestoreAborted)
    assert on_retry_calls[1][0] == 2
