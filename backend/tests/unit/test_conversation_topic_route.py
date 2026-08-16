"""Return-only conversation topic uses the managed conv_structure feature."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import conversations as conversations_router
from utils.llm.conversation_topic import ConversationTopic

UID = 'uid-conversation-topic'


@pytest.fixture(autouse=True)
def _entitled(monkeypatch):
    """Default to an entitled account; the paywall gate has its own test."""
    import utils.subscription as subscription

    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda uid, platform: False)


async def test_generate_topic_returns_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_generate(uid, transcript):
        calls['uid'] = uid
        calls['transcript'] = transcript
        return ConversationTopic(emoji='🎧', title='Weekly standup')

    import utils.llm.conversation_topic as conversation_topic_llm

    monkeypatch.setattr(conversation_topic_llm, 'generate_conversation_topic', fake_generate)

    response = await conversations_router.generate_conversation_topic_endpoint(
        conversations_router.ConversationTopicRequest(transcript='we discussed the sprint'),
        uid=UID,
    )

    assert response.emoji == '🎧'
    assert response.title == 'Weekly standup'
    assert calls['uid'] == UID
    assert calls['transcript'] == 'we discussed the sprint'


async def test_generate_topic_fails_closed_when_generation_returns_none(monkeypatch):
    import utils.llm.conversation_topic as conversation_topic_llm

    monkeypatch.setattr(conversation_topic_llm, 'generate_conversation_topic', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        await conversations_router.generate_conversation_topic_endpoint(
            conversations_router.ConversationTopicRequest(transcript='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 502


async def test_generate_conversation_topic_endpoint_blocks_a_trial_expired_account(monkeypatch):
    import utils.subscription as subscription

    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda uid, platform: True)

    with pytest.raises(HTTPException) as exc:
        await conversations_router.generate_conversation_topic_endpoint(
            conversations_router.ConversationTopicRequest(transcript='anything'),
            uid=UID,
        )
    assert exc.value.status_code == 402
