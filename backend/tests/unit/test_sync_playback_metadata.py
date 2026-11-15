"""Demand metadata work has bounded admission, single-flight and retry debt."""

from concurrent.futures import Future, TimeoutError
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from utils.sync import playback_metadata as module


@pytest.fixture
def coordinator(monkeypatch):
    owner = module.DemandCoordinator()
    monkeypatch.setattr(module, '_coordinator', owner)
    monkeypatch.setattr(module.time, 'monotonic', lambda: 100.0)
    return owner


def test_single_flight_and_user_process_bounds_keep_running_timeout_reserved(coordinator, monkeypatch):
    first, second = Future(), Future()
    first.set_running_or_notify_cancel()
    second.set_running_or_notify_cancel()
    submit = Mock(side_effect=[first, second])
    monkeypatch.setattr(module, 'submit_with_context', submit)
    assert coordinator.get('one', 'a') is first
    assert coordinator.get('one', 'a') is first  # Same owner/conversation joins.
    with pytest.raises(module.MetadataPending):
        coordinator.get('one', 'b')  # One active request per user.
    assert coordinator.get('two', 'b') is second
    with pytest.raises(module.MetadataPending):
        coordinator.get('three', 'c')
    # Expire only this caller's wait; the running work keeps its real Future
    # callbacks and admission slots until completion below.
    expired_wait = Mock(side_effect=TimeoutError)
    with monkeypatch.context() as wait_patch:
        wait_patch.setattr(first, 'result', expired_wait)
        with pytest.raises(module.MetadataPending) as timeout:
            module.refresh_on_open('one', 'a')
        expired_wait.assert_called_once_with(timeout=module.OPEN_TIMEOUT_SECONDS)
    assert timeout.value.reason == 'timeout'
    assert len(coordinator.active) == 2 and not first.cancelled()
    assert first.running() and second.running() and not second.cancelled()
    assert submit.call_count == 2  # Repeated open cannot launch another listing.
    first.set_result({'audio_files': [{'id': 'first'}]})
    second.set_result({'audio_files': [{'id': 'second'}]})
    assert not coordinator.active
    assert not coordinator.cooldown  # Both real completion callbacks read successful results.


@pytest.mark.parametrize('result', [{}, HTTPException(503, 'unavailable'), HTTPException(404, 'refused')])
def test_failure_or_empty_has_cooldown_without_new_io(coordinator, monkeypatch, result):
    future = Future()
    submit = Mock(return_value=future)
    monkeypatch.setattr(module, 'submit_with_context', submit)
    assert coordinator.get('u', 'c') is future
    if isinstance(result, Exception):
        future.set_exception(result)
    else:
        future.set_result(result)
    for _ in range(3):
        with pytest.raises((module.MetadataPending, HTTPException)):
            coordinator.get('u', 'c')
    assert submit.call_count == 1
    monkeypatch.setattr(module.time, 'monotonic', lambda: 131.0)
    assert coordinator.get('u', 'c') is future
    assert submit.call_count == 2


def test_successful_fast_requests_still_obey_user_and_total_attempt_budgets(coordinator, monkeypatch):
    def done(*args):
        future = Future()
        future.set_result({'audio_files': [{'id': 'ready'}]})
        return future

    submit = Mock(side_effect=done)
    monkeypatch.setattr(module, 'submit_with_context', submit)
    for i in range(module.MAX_USER_ATTEMPTS):
        coordinator.get('same', str(i))
    with pytest.raises(module.MetadataPending):
        coordinator.get('same', 'excess')
    for i in range(module.MAX_PROCESS_ATTEMPTS - module.MAX_USER_ATTEMPTS):
        coordinator.get(str(i), 'c')
    with pytest.raises(module.MetadataPending):
        coordinator.get('new-owner', 'c')
    assert submit.call_count == module.MAX_PROCESS_ATTEMPTS
    monkeypatch.setattr(module.time, 'monotonic', lambda: 161.0)
    coordinator.get('same', 'after-window')
    assert len(coordinator.attempts) == 1


def test_history_capacity_refuses_without_evicting_unexpired_cooldown(coordinator, monkeypatch):
    monkeypatch.setattr(module, 'MAX_HISTORY', 2)
    submit = Mock()
    monkeypatch.setattr(module, 'submit_with_context', submit)
    coordinator.cooldown['a', 'c'] = (130, None)
    coordinator.cooldown['b', 'c'] = (130, None)
    with pytest.raises(module.MetadataPending):
        coordinator.get('third', 'c')
    assert len(coordinator.cooldown) == 2
    submit.assert_not_called()
