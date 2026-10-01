"""Unit tests for bounded Firestore transaction contention retry."""

from __future__ import annotations

import logging
import math
from typing import Any
from unittest.mock import MagicMock

import pytest

from database.firestore_transaction_retry import (
    DEFAULT_MAX_ATTEMPTS,
    FirestoreAborted,
    FirestoreContentionExhausted,
    _is_transaction_contention,
    is_transaction_contention,
    run_with_transaction_contention_retry,
)


class MockTransaction:
    """Mock Firestore transaction object."""

    def __init__(self, tx_id: int):
        self.tx_id = tx_id


def test_success_first_attempt() -> None:
    tx_factory = MagicMock(return_value=MockTransaction(1))
    operation = MagicMock(return_value="commit_ok")
    sleep = MagicMock()

    result = run_with_transaction_contention_retry(
        tx_factory,
        operation,
        operation_name="test_op",
        sleep=sleep,
    )

    assert result == "commit_ok"
    assert tx_factory.call_count == 1
    assert operation.call_count == 1
    assert sleep.call_count == 0


def test_recover_after_contention_retry(caplog: pytest.LogCaptureFixture) -> None:
    tx_factory = MagicMock(side_effect=[MockTransaction(1), MockTransaction(2), MockTransaction(3)])
    delays: list[float] = []

    def record_sleep(d: float) -> None:
        delays.append(d)

    attempts = [0]

    def op(tx: Any) -> str:
        attempts[0] += 1
        if attempts[0] < 3:
            raise FirestoreAborted(f"Abort attempt {attempts[0]}")
        return "success_recovered"

    with caplog.at_level(logging.INFO):
        result = run_with_transaction_contention_retry(
            tx_factory,
            op,
            operation_name="recover_op",
            max_attempts=5,
            sleep=record_sleep,
            random_value=lambda: 0.5,
        )

    assert result == "success_recovered"
    assert attempts[0] == 3
    assert len(delays) == 2
    assert all(d > 0 for d in delays)
    assert "outcome=retry" in caplog.text
    assert "outcome=recovered" in caplog.text


def test_exhaust_max_attempts(caplog: pytest.LogCaptureFixture) -> None:
    delays: list[float] = []

    def op(tx: Any) -> None:
        raise FirestoreAborted("Always abort")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FirestoreContentionExhausted) as exc_info:
            run_with_transaction_contention_retry(
                lambda: MockTransaction(1),
                op,
                operation_name="exhaust_op",
                max_attempts=4,
                sleep=lambda d: delays.append(d),
                random_value=lambda: 0.0,
            )

    assert "Firestore transaction contention exhausted for exhaust_op" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, FirestoreAborted)
    assert len(delays) == 3
    assert "outcome=exhausted" in caplog.text


def test_unrelated_exception_raises_immediately() -> None:
    sleep = MagicMock()
    tx_factory = MagicMock(return_value=MockTransaction(1))

    def op(tx: Any) -> None:
        raise ValueError("Invalid business logic data")

    with pytest.raises(ValueError, match="Invalid business logic data"):
        run_with_transaction_contention_retry(
            tx_factory,
            op,
            operation_name="fail_fast_op",
            sleep=sleep,
        )

    assert tx_factory.call_count == 1
    assert sleep.call_count == 0


def test_chained_explicit_cause_contention() -> None:
    attempts = [0]

    def op(tx: Any) -> str:
        attempts[0] += 1
        if attempts[0] == 1:
            try:
                raise FirestoreAborted("Low-level gRPC abort")
            except FirestoreAborted as err:
                raise RuntimeError("Service-layer wrapper error") from err
        return "chain_resolved"

    result = run_with_transaction_contention_retry(
        lambda: MockTransaction(1),
        op,
        operation_name="cause_chain_op",
        sleep=lambda d: None,
    )

    assert result == "chain_resolved"
    assert attempts[0] == 2


def test_implicit_context_does_not_trigger_retry() -> None:
    attempts = [0]

    def op(tx: Any) -> str:
        attempts[0] += 1
        try:
            raise FirestoreAborted("Raw contention")
        except FirestoreAborted:
            # Implicit context: raised without 'from err' must NOT be retried per repo contract
            raise RuntimeError("Replacement error")

    with pytest.raises(RuntimeError, match="Replacement error"):
        run_with_transaction_contention_retry(
            lambda: MockTransaction(1),
            op,
            operation_name="implicit_context_op",
            sleep=lambda d: None,
        )

    assert attempts[0] == 1


def test_operation_name_non_string_sanitization() -> None:
    result = run_with_transaction_contention_retry(
        lambda: MockTransaction(1),
        lambda tx: "ok",
        operation_name=None,  # type: ignore[arg-type]
    )
    assert result == "ok"


def test_grpc_status_code_callable_and_attribute() -> None:
    class GrpcCallableCodeError(Exception):
        def code(self) -> Any:
            class Status:
                name = "ABORTED"

            return Status()

    class GrpcStatusCodeError(Exception):
        def __init__(self) -> None:
            self.grpc_status_code = 10

    class NonAbortedConflictError(Exception):
        def __init__(self) -> None:
            self.code = 409  # Generic HTTP 409 Conflict must NOT be treated as contention

    assert is_transaction_contention(GrpcCallableCodeError()) is True
    assert is_transaction_contention(GrpcStatusCodeError()) is True
    # In chat.py, AlreadyExists/Conflict must escape and not be replayed as transaction contention
    assert is_transaction_contention(NonAbortedConflictError()) is False


def test_cyclic_exception_reference_protection() -> None:
    e1 = Exception("first")
    e2 = Exception("second")
    e1.__cause__ = e2
    e2.__cause__ = e1

    assert is_transaction_contention(e1) is False

    # Now inject FirestoreAborted in chain via __cause__
    e3 = FirestoreAborted("inner abort")
    e2.__cause__ = e3
    assert is_transaction_contention(e1) is True


def test_nested_exception_group_unrolling() -> None:
    class MockExceptionGroup(Exception):
        def __init__(self, message: str, exceptions: list[BaseException]):
            super().__init__(message)
            self.exceptions = exceptions

    eg = MockExceptionGroup("TaskGroup failure", [ValueError("not this"), FirestoreAborted("abort inside")])
    assert is_transaction_contention(eg) is True

    eg_benign = MockExceptionGroup("TaskGroup benign", [ValueError("nope"), KeyError("not here")])
    assert is_transaction_contention(eg_benign) is False


@pytest.mark.parametrize("invalid_attempts", [0, -1, -5, True, False, "5", 3.14, None])
def test_invalid_max_attempts(invalid_attempts: Any) -> None:
    with pytest.raises(ValueError, match="max_attempts must be positive"):
        run_with_transaction_contention_retry(
            lambda: None,
            lambda tx: None,
            operation_name="invalid_attempts_op",
            max_attempts=invalid_attempts,
        )


def test_invalid_callables() -> None:
    with pytest.raises(TypeError, match="transaction_factory must be callable"):
        run_with_transaction_contention_retry(
            "not_callable",  # type: ignore[arg-type]
            lambda tx: None,
            operation_name="test",
        )

    with pytest.raises(TypeError, match="operation must be callable"):
        run_with_transaction_contention_retry(
            lambda: None,
            "not_callable",  # type: ignore[arg-type]
            operation_name="test",
        )

    with pytest.raises(TypeError, match="sleep must be callable"):
        run_with_transaction_contention_retry(
            lambda: None,
            lambda tx: None,
            operation_name="test",
            sleep="not_callable",  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="random_value must be callable"):
        run_with_transaction_contention_retry(
            lambda: None,
            lambda tx: None,
            operation_name="test",
            random_value="not_callable",  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="on_retry must be callable"):
        run_with_transaction_contention_retry(
            lambda: None,
            lambda tx: None,
            operation_name="test",
            on_retry="not_callable",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("op_name, expected_name", [("  custom_name  ", "custom_name"), ("", "unnamed_operation")])
def test_operation_name_sanitization(op_name: Any, expected_name: str) -> None:
    with pytest.raises(FirestoreContentionExhausted) as exc_info:
        run_with_transaction_contention_retry(
            lambda: None,
            lambda tx: (_ for _ in ()).throw(FirestoreAborted("abort")),
            operation_name=op_name,
            max_attempts=1,
            sleep=lambda d: None,
        )
    assert f"Firestore transaction contention exhausted for {expected_name}" in str(exc_info.value)


@pytest.mark.parametrize(
    "corrupted_random",
    [
        lambda: float("nan"),
        lambda: float("inf"),
        lambda: -1.0,
        lambda: 2.5,
        lambda: "invalid",
        lambda: 10**1000,  # Triggers OverflowError during float()
    ],
)
def test_jitter_sanitization_boundary(corrupted_random: Any) -> None:
    delays: list[float] = []
    attempts = [0]

    def op(tx: Any) -> str:
        attempts[0] += 1
        if attempts[0] == 1:
            raise FirestoreAborted("Jitter test")
        return "ok"

    result = run_with_transaction_contention_retry(
        lambda: None,
        op,
        operation_name="jitter_test",
        sleep=lambda d: delays.append(d),
        random_value=corrupted_random,
    )

    assert result == "ok"
    assert len(delays) == 1
    assert not math.isnan(delays[0])
    assert not math.isinf(delays[0])
    assert delays[0] >= 0.0


def test_backoff_delay_clamped_at_max_delay_and_exponent() -> None:
    """Exercise late retry attempts (attempt >= 5) to verify clamping at _MAX_DELAY_SECONDS."""
    delays: list[float] = []
    attempts = [0]

    def op(tx: Any) -> str:
        attempts[0] += 1
        if attempts[0] <= 5:
            raise FirestoreAborted(f"Contention attempt {attempts[0]}")
        return "finally_recovered"

    result = run_with_transaction_contention_retry(
        lambda: None,
        op,
        operation_name="deep_retry_op",
        max_attempts=7,
        sleep=lambda d: delays.append(d),
        random_value=lambda: 1.0,  # High jitter gives maximum bound
    )

    assert result == "finally_recovered"
    assert attempts[0] == 6
    assert len(delays) == 5

    # Attempts 1 to 5 delay progression:
    # attempt 1: 0.2
    # attempt 2: 0.4
    # attempt 3: 0.8
    # attempt 4: 1.0 (capped at _MAX_DELAY_SECONDS)
    # attempt 5: 1.0 (capped at _MAX_DELAY_SECONDS)
    assert delays[0] <= 0.2 + 1e-6
    assert delays[1] <= 0.4 + 1e-6
    assert delays[2] <= 0.8 + 1e-6
    assert delays[3] <= 1.0 + 1e-6
    assert delays[4] <= 1.0 + 1e-6


def test_on_retry_observer_and_fault_isolation() -> None:
    callback_events: list[tuple[str, int, int, float]] = []

    def observer(op: str, attempt: int, max_att: int, delay: float, err: BaseException) -> None:
        callback_events.append((op, attempt, max_att, delay))
        if attempt == 2:
            raise RuntimeError("Observer internal crash")

    attempts = [0]

    def op(tx: Any) -> str:
        attempts[0] += 1
        if attempts[0] < 3:
            raise FirestoreAborted("Retry")
        return "done"

    result = run_with_transaction_contention_retry(
        lambda: None,
        op,
        operation_name="telemetry_op",
        max_attempts=4,
        sleep=lambda d: None,
        on_retry=observer,
    )

    assert result == "done"
    assert attempts[0] == 3
    assert len(callback_events) == 2
    assert callback_events[0][0] == "telemetry_op"
    assert callback_events[0][1] == 1
    assert callback_events[1][1] == 2


def test_exports_and_aliases() -> None:
    assert _is_transaction_contention is is_transaction_contention
    assert DEFAULT_MAX_ATTEMPTS == 5
