"""Return-only AgentPill title/ack uses the managed session_titles feature."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import chat_sessions as chat_sessions_router
from utils.llm.agent_pill_title import AgentPillTitleAck

UID = 'uid-agent-pill-title'


@pytest.fixture(autouse=True)
def _entitled(monkeypatch):
    import utils.subscription as subscription

    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda uid, platform: False)


async def test_generate_agent_pill_title_returns_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_generate(uid, query):
        calls['uid'] = uid
        calls['query'] = query
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


async def test_generate_agent_pill_title_fails_closed_when_generation_returns_none(monkeypatch):
    import utils.llm.agent_pill_title as agent_pill_title_llm

    monkeypatch.setattr(agent_pill_title_llm, 'generate_agent_pill_title_ack', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        await chat_sessions_router.generate_agent_pill_title(
            chat_sessions_router.AgentPillTitleRequest(query='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 502


async def test_generate_agent_pill_title_blocks_a_trial_expired_account(monkeypatch):
    import utils.subscription as subscription

    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda uid, platform: True)

    with pytest.raises(HTTPException) as exc:
        await chat_sessions_router.generate_agent_pill_title(
            chat_sessions_router.AgentPillTitleRequest(query='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 402
