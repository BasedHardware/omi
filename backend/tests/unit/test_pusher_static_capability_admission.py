"""Pusher startup rejects a revision that cannot mutate canonical memory."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import pusher.main as pusher_main


@pytest.mark.parametrize(
    'env',
    [
        {'MEMORY_ENABLED': 'on'},
        {'MEMORY_MODE': 'write'},
        # The production parser keeps this legacy mode mutation-capable.
        {'MEMORY_MODE': 'read'},
    ],
)
def test_pusher_static_capability_admission_accepts_runtime_writable_modes(env: dict[str, str]) -> None:
    pusher_main._validate_static_capabilities(env)


@pytest.mark.parametrize(
    'env',
    [
        {},
        {'MEMORY_ENABLED': 'off'},
        {'MEMORY_ENABLED': 'invalid'},
        {'MEMORY_MODE': 'shadow'},
    ],
)
def test_pusher_static_capability_admission_rejects_non_writable_modes(env: dict[str, str]) -> None:
    with pytest.raises(RuntimeError, match='conversation.finalize.persisted requires memory.canonical.mutate'):
        pusher_main._validate_static_capabilities(env)


async def test_pusher_startup_checks_static_capability_before_starting_background_work(monkeypatch) -> None:
    monkeypatch.setenv('MEMORY_ENABLED', 'off')
    monkeypatch.delenv('MEMORY_MODE', raising=False)
    start_background_task = MagicMock()
    monkeypatch.setattr(pusher_main, 'start_background_task', start_background_task)

    with pytest.raises(RuntimeError, match='static capability admission failed'):
        await pusher_main.startup_event()

    start_background_task.assert_not_called()
