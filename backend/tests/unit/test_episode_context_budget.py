"""Context deadlines bound the entire operation and discard late evidence."""

from contextvars import ContextVar
import threading
from types import SimpleNamespace
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
    """The caller's budget elapses on an injected clock while the provider call is still running."""
    now = [1000.0]
    release, ended, entered = threading.Event(), threading.Event(), threading.Event()

    class ExpiringEvent(threading.Event):
        def wait(self, timeout=None):
            # The whole remaining budget passes with the worker inside its provider call.
            assert entered.wait(5)
            now[0] += timeout
            return self.is_set()

    monkeypatch.setattr(budget, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(budget, 'threading', SimpleNamespace(Event=ExpiringEvent, Lock=threading.Lock))
    identity = ContextVar('synthetic_owner', default='missing')
    token = identity.set('owner-context')

    def load(deadline):
        try:
            assert identity.get() == 'owner-context'
            assert 0 < deadline - now[0] <= budget.COMPOSER_CONTEXT_TIMEOUT_SECONDS
            entered.set()
            release.wait(5)
            return 'late profile', 'late private memories'
        finally:
            ended.set()

    try:
        result = budget.bounded_gather(load, 'fallback')
        # Returned at the deadline, not when the non-cooperative provider finished.
        assert not ended.is_set()
        assert result == ('fallback', '')
    finally:
        release.set()
        assert ended.wait(5)
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
