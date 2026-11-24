"""Return-only AI user profile synthesis route uses the managed memories feature."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import users as users_router
from utils.llm.ai_user_profile import ProfileSynthesis

UID = 'uid-ai-profile-synthesis'


async def test_synthesize_ai_profile_returns_without_persisting(monkeypatch):
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

    response = await users_router.synthesize_ai_profile(
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


async def test_synthesize_ai_profile_fails_closed_when_synthesis_returns_none(monkeypatch):
    import utils.llm.ai_user_profile as ai_user_profile_llm

    monkeypatch.setattr(ai_user_profile_llm, 'synthesize_ai_user_profile', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        await users_router.synthesize_ai_profile(
            users_router.SynthesizeAIUserProfileRequest(memories=['[work] engineer']),
            uid=UID,
        )
    assert exc.value.status_code == 502


def test_get_ai_profile_hands_its_read_to_the_scheduler(monkeypatch):
    scheduled: list[tuple] = []
    monkeypatch.setattr(
        users_router.ai_profile_refresh,
        'schedule_refresh',
        lambda uid, profile, known=False: scheduled.append((uid, profile, known)),
    )
    stale = {'profile_text': '- fact', 'source': 'client'}
    monkeypatch.setattr(users_router.users_db, 'get_ai_user_profile', lambda uid: stale)

    assert users_router.get_ai_profile(uid=UID) is stale
    assert scheduled == [(UID, stale, True)]


def test_patch_ai_profile_records_source(monkeypatch):
    seen: dict = {}

    def fake_update(uid, **kwargs):
        seen.update(kwargs)
        return {'profile_text': kwargs['profile_text'], 'source': kwargs['source']}

    monkeypatch.setattr(users_router.users_db, 'update_ai_user_profile', fake_update)
    response = users_router.update_ai_profile(
        users_router.UpdateAIUserProfileRequest(profile_text='- edited', source='user_edit'), uid=UID
    )
    assert response['source'] == 'user_edit'
    assert seen['source'] == 'user_edit'


def test_delete_ai_profile(monkeypatch):
    deleted: list[str] = []
    monkeypatch.setattr(users_router.users_db, 'delete_ai_user_profile', deleted.append)
    assert users_router.delete_ai_profile(uid=UID).status_code == 204
    assert deleted == [UID]


def test_forget_profile_also_clears_the_retired_v2_profile(monkeypatch):
    from unittest.mock import MagicMock

    from database import users as users_db

    store = MagicMock()
    invalidated = []
    monkeypatch.setattr(users_db, 'db', store)
    monkeypatch.setattr(users_db, 'invalidate', lambda cache, uid: invalidated.append(uid))
    users_db.delete_ai_user_profile(UID)
    store.collection.assert_called_once_with('users')
    store.collection.return_value.document.assert_called_once_with(UID)
    (update,), _ = store.collection.return_value.document.return_value.update.call_args
    assert update == {
        'ai_user_profile': users_db.firestore.DELETE_FIELD,
        'ai_user_profile_v2': users_db.firestore.DELETE_FIELD,
    }
    assert invalidated == [UID]


@pytest.mark.parametrize(
    'code, status',
    [
        ('ai_profile_refresh_unavailable', 503),
        ('ai_profile_refresh_in_progress', 409),
        ('ai_profile_insufficient_data', 422),
        ('ai_profile_synthesis_failed', 502),
    ],
)
async def test_refresh_ai_profile_maps_errors(monkeypatch, code, status):
    def fail(uid):
        raise users_router.ai_profile_refresh.RefreshError(code)

    monkeypatch.setattr(users_router, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(users_router.ai_profile_refresh, 'refresh_now', fail)
    with pytest.raises(HTTPException) as exc:
        await users_router.refresh_ai_profile(uid=UID)
    assert exc.value.status_code == status
    assert exc.value.detail == code


async def test_refresh_ai_profile_returns_new_profile(monkeypatch):
    monkeypatch.setattr(users_router, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(
        users_router.ai_profile_refresh, 'refresh_now', lambda uid: {'profile_text': '- new', 'source': 'backend'}
    )
    assert (await users_router.refresh_ai_profile(uid=UID))['profile_text'] == '- new'
