"""Unit tests for the bounded tokenizer-cache prewarm helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'prewarm_tiktoken_cache.py'


def _load_script():
    spec = importlib.util.spec_from_file_location('prewarm_tiktoken_cache', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_prewarm_retries_transient_http_failure_with_a_bounded_attempt_count():
    prewarm = _load_script()
    calls: list[str] = []
    delays: list[float] = []

    # Match the requests HTTPError shape used by tiktoken without importing requests.
    failure = RuntimeError('service unavailable')
    failure.response = SimpleNamespace(status_code=503)  # type: ignore[attr-defined]
    outcomes = iter((failure, failure, None))

    def load_with_transient_failures(model: str) -> None:
        calls.append(model)
        outcome = next(outcomes)
        if outcome is not None:
            raise outcome

    prewarm.prewarm(load_with_transient_failures, sleep=delays.append)

    assert calls == ['gpt-4', 'gpt-4', 'gpt-4']
    assert delays == [1.0, 2.0]


def test_prewarm_does_not_retry_non_transient_failure():
    prewarm = _load_script()
    calls: list[str] = []

    def load_encoding(model: str) -> None:
        calls.append(model)
        raise ValueError('unknown model')

    try:
        prewarm.prewarm(load_encoding, sleep=lambda _: None)
    except RuntimeError as error:
        assert 'attempt 1/3' in str(error)
    else:
        raise AssertionError('expected prewarm to fail')

    assert calls == ['gpt-4']
