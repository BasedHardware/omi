"""Tests for utils/executors.py run_blocking and submit_with_context."""

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from utils.executors import run_blocking, submit_with_context

_test_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test")
_test_ctxvar = contextvars.ContextVar("test_key", default=None)


@pytest.mark.asyncio
async def test_run_blocking_uses_provided_executor():
    """run_blocking must execute fn on the given executor, not the default pool."""
    captured = {}

    def capture_thread():
        captured["thread"] = threading.current_thread().name

    await run_blocking(_test_executor, capture_thread)
    assert captured["thread"].startswith("test"), f"Expected 'test' prefix, got {captured['thread']}"


@pytest.mark.asyncio
async def test_run_blocking_passes_args_and_kwargs():
    """Positional and keyword arguments must reach the target function."""

    def adder(a, b, multiplier=1):
        return (a + b) * multiplier

    result = await run_blocking(_test_executor, adder, 3, 4, multiplier=2)
    assert result == 14


@pytest.mark.asyncio
async def test_run_blocking_propagates_exceptions():
    """Exceptions raised inside the executor must propagate to the caller."""

    def boom():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        await run_blocking(_test_executor, boom)


@pytest.mark.asyncio
async def test_run_blocking_propagates_contextvars():
    """ContextVars set before run_blocking must be visible inside the executor."""
    token = _test_ctxvar.set("hello-from-caller")
    captured = {}

    def read_ctxvar():
        captured["value"] = _test_ctxvar.get()

    try:
        await run_blocking(_test_executor, read_ctxvar)
    finally:
        _test_ctxvar.reset(token)

    assert captured["value"] == "hello-from-caller"


def test_submit_with_context_propagates_contextvars():
    """submit_with_context must propagate ContextVars to the submitted function."""
    token = _test_ctxvar.set("submit-test")
    captured = {}

    def read_ctxvar():
        captured["value"] = _test_ctxvar.get()

    try:
        future = submit_with_context(_test_executor, read_ctxvar)
        future.result(timeout=5)
    finally:
        _test_ctxvar.reset(token)

    assert captured["value"] == "submit-test"


def test_submit_with_context_returns_future_with_result():
    """submit_with_context must return a Future whose result matches fn's return."""

    def double(x):
        return x * 2

    future = submit_with_context(_test_executor, double, 21)
    assert future.result(timeout=5) == 42
