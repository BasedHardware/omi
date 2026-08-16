"""Behavioral contract for replaying content fenced by empty-session cleanup."""

from __future__ import annotations

import pytest

from utils.conversations.live_content import retry_fenced_live_content_once


@pytest.mark.anyio
async def test_fenced_content_rolls_once_then_replays_into_fresh_generation() -> None:
    calls: list[str] = []

    def write_current() -> None:
        calls.append('write-current')
        return None

    async def rollover() -> None:
        calls.append('rollover')

    def write_fresh() -> tuple[str, str]:
        calls.append('write-fresh')
        return ('fresh-conversation', 'persisted-content')

    result, rolled_over = await retry_fenced_live_content_once(
        write_current=write_current,
        rollover=rollover,
        write_fresh=write_fresh,
    )

    assert result == ('fresh-conversation', 'persisted-content')
    assert rolled_over is True
    assert calls == ['write-current', 'rollover', 'write-fresh']


@pytest.mark.anyio
async def test_successful_content_write_never_opens_an_extra_generation() -> None:
    calls: list[str] = []

    def write_current() -> str:
        calls.append('write-current')
        return 'persisted-content'

    async def rollover() -> None:
        calls.append('rollover')

    def write_fresh() -> str:
        calls.append('write-fresh')
        return 'unexpected'

    result, rolled_over = await retry_fenced_live_content_once(
        write_current=write_current,
        rollover=rollover,
        write_fresh=write_fresh,
    )

    assert result == 'persisted-content'
    assert rolled_over is False
    assert calls == ['write-current']
