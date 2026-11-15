"""Context deadlines bound the entire operation and discard late evidence."""

from contextvars import ContextVar
import threading
import time
from unittest.mock import Mock

import pytest

from utils.episodes import composer_context_budget as budget
from utils import executors


@pytest.fixture(autouse=True)
def fallbacks(monkeypatch):
    executors.get_context_executor()
    recorder = Mock()
    monkeypatch.setattr(budget, '_fallback', recorder)
    return recorder


def test_one_deadline_discards_all_partial_context_and_late_memories(monkeypatch, fallbacks):
    monkeypatch.setattr(budget, 'COMPOSER_CONTEXT_TIMEOUT_SECONDS', 0.1)
    release, ended = threading.Event(), threading.Event()
    identity = ContextVar('synthetic_owner', default='missing')
    token = identity.set('owner-context')

    def load(deadline):
        try:
            assert identity.get() == 'owner-context'
            assert deadline - time.monotonic() <= 0.1
            release.wait(1)
            return 'late profile', 'late private memories'
        finally:
            ended.set()

    try:
        started = time.monotonic()
        result = budget.bounded_gather(load, 'fallback')
        assert time.monotonic() - started < 0.5
        assert result == ('fallback', '')
    finally:
        release.set()
        assert ended.wait(1)
        identity.reset(token)
    assert result == ('fallback', '')
    fallbacks.assert_called_once_with('timeout')


def test_saturated_context_workers_fail_empty_without_queuing(monkeypatch):
    monkeypatch.setattr(budget, '_submit', Mock(side_effect=RuntimeError('saturated')))
    calls = []
    assert budget.bounded_gather(lambda *_args: calls.append(True), 'owner') == ('owner', '')
    assert not calls


def test_retrieval_error_omits_all_loaded_context_and_counts_once(fallbacks):

    def load(_deadline):
        raise RuntimeError('private provider detail never logged')

    assert budget.bounded_gather(load, 'default') == ('default', '')
    fallbacks.assert_called_once_with('transport_error')
