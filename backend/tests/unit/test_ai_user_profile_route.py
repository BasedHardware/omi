"""Return-only AI user profile synthesis route uses the managed memories feature."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import users as users_router
from utils.llm.ai_user_profile import ProfileSynthesis

UID = 'uid-ai-profile-synthesis'


def test_synthesize_ai_profile_returns_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_synthesize(uid, sources, **kwargs):
        calls['uid'] = uid
        calls['sources'] = sources
        calls['kwargs'] = kwargs
        return ProfileSynthesis(
            profile_text='- User is an engineer',
            data_sources_used=['memories', 'goals'],
            item_count=2,
        )

    import utils.llm.ai_user_profile as ai_user_profile_llm

    monkeypatch.setattr(ai_user_profile_llm, 'synthesize_ai_user_profile', fake_synthesize)

    response = users_router.synthesize_ai_profile(
        users_router.SynthesizeAIUserProfileRequest(
            memories=['[work] engineer'],
            goals=['ship the desktop app'],
            past_profiles=['- old fact'],
        ),
        uid=UID,
    )

    assert response.profile_text == '- User is an engineer'
    assert response.data_sources_used == ['memories', 'goals']
    assert response.item_count == 2
    assert calls['uid'] == UID
    assert calls['sources'].memories == ['[work] engineer']
    assert calls['sources'].goals == ['ship the desktop app']
    assert calls['kwargs']['past_profiles'] == ['- old fact']


def test_synthesize_ai_profile_fails_closed_when_synthesis_returns_none(monkeypatch):
    import utils.llm.ai_user_profile as ai_user_profile_llm

    monkeypatch.setattr(ai_user_profile_llm, 'synthesize_ai_user_profile', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        users_router.synthesize_ai_profile(
            users_router.SynthesizeAIUserProfileRequest(memories=['[work] engineer']),
            uid=UID,
        )
    assert exc.value.status_code == 502
