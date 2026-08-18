"""Return-only AgentPill title/ack uses the managed session_titles feature."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from routers import chat_sessions as chat_sessions_router
from utils.llm.agent_pill_title import AgentPillTitleAck

UID = 'uid-agent-pill-title'


@pytest.fixture(autouse=True)
def _entitled(monkeypatch):
    monkeypatch.setattr(chat_sessions_router, 'is_trial_paywalled', lambda uid, platform: False)


async def test_generate_agent_pill_title_returns_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_generate(uid, query, deadline=None):
        calls['uid'] = uid
        calls['query'] = query
        calls['deadline'] = deadline
        return AgentPillTitleAck(title='Build Mario Level', ack='Got it, on it.')

    import utils.llm.agent_pill_title as agent_pill_title_llm

    monkeypatch.setattr(agent_pill_title_llm, 'generate_agent_pill_title_ack', fake_generate)

    response = await chat_sessions_router.generate_agent_pill_title(
        chat_sessions_router.AgentPillTitleRequest(query='build a mario level'),
        uid=UID,
    )

    assert response.title == 'Build Mario Level'
    assert response.ack == 'Got it, on it.'
    assert calls['uid'] == UID
    assert calls['query'] == 'build a mario level'
    assert isinstance(calls['deadline'], float)


async def test_generate_agent_pill_title_fails_closed_when_generation_returns_none(monkeypatch):
    import utils.llm.agent_pill_title as agent_pill_title_llm

    monkeypatch.setattr(agent_pill_title_llm, 'generate_agent_pill_title_ack', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        await chat_sessions_router.generate_agent_pill_title(
            chat_sessions_router.AgentPillTitleRequest(query='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 502


async def test_generate_agent_pill_title_fails_closed_when_executor_exceeds_deadline(monkeypatch):
    """A queued title job that exceeds the route's outer deadline returns 502."""
    monkeypatch.setattr(chat_sessions_router, 'AGENT_PILL_TITLE_ROUTE_TIMEOUT_SECONDS', 0.1)

    call_count = [0]

    async def slow_run_blocking(executor, fn, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # The first call is the trial-paywall check; return quickly.
            return False
        await asyncio.sleep(10)

    monkeypatch.setattr(chat_sessions_router, 'run_blocking', slow_run_blocking)

    with pytest.raises(HTTPException) as exc:
        await chat_sessions_router.generate_agent_pill_title(
            chat_sessions_router.AgentPillTitleRequest(query='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 502
    assert exc.value.detail == 'agent_pill_title_timeout'


async def test_generate_agent_pill_title_blocks_a_trial_expired_account(monkeypatch):
    monkeypatch.setattr(chat_sessions_router, 'is_trial_paywalled', lambda uid, platform: True)

    with pytest.raises(HTTPException) as exc:
        await chat_sessions_router.generate_agent_pill_title(
            chat_sessions_router.AgentPillTitleRequest(query='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 402
