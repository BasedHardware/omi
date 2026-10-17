from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from database import conversations as conversations_db, users as users_db
from models.users import PlanType, Subscription, SubscriptionStatus
from routers import conversations as routes
from routers import users as users_routes

UID = "test-user-unlock-recovery"
CONV_LOCKED_1 = "conv-locked-1"
CONV_LOCKED_2 = "conv-locked-2"
CONV_UNLOCKED = "conv-unlocked-3"


@contextmanager
def fake_context_manager(*args, **kwargs):
    yield


def _setup_mock_db(
    monkeypatch,
    *,
    allowance_reason: str = "plan_within_allowance",
    managed: bool = True,
    byok_active: bool = False,
):
    mock_conversations = {
        CONV_LOCKED_1: {
            "id": CONV_LOCKED_1,
            "is_locked": True,
            "deleted": False,
            "structured": {"title": "Historical Meeting", "overview": "Overview 1"},
            "speakers": ["self"],
        },
        CONV_LOCKED_2: {
            "id": CONV_LOCKED_2,
            "is_locked": True,
            "deleted": False,
            "structured": {"title": "Older Strategy", "overview": "Overview 2"},
            "speakers": ["self"],
        },
        CONV_UNLOCKED: {
            "id": CONV_UNLOCKED,
            "is_locked": False,
            "deleted": False,
            "structured": {"title": "Active Call", "overview": "Overview 3"},
            "speakers": ["self"],
        },
    }

    def mock_get_conversation(uid, conversation_id, **kwargs):
        return mock_conversations.get(conversation_id)

    updated_conversations = {}

    def mock_update_conversation(uid, conversation_id, patch):
        if conversation_id in mock_conversations:
            mock_conversations[conversation_id].update(patch)
            updated_conversations[conversation_id] = patch

    def mock_get_conversations_by_id_without_photos(uid, conversation_ids, **kwargs):
        return [dict(mock_conversations[cid]) for cid in conversation_ids if cid in mock_conversations]

    fake_allowance = SimpleNamespace(
        managed=managed,
        reason=allowance_reason,
        byok_active=byok_active,
        limit_seconds=18000,
        remaining_seconds=10000,
        as_dict=lambda: {"limit_seconds": 18000, "remaining_seconds": 10000},
    )

    import utils.subscription

    monkeypatch.setattr(utils.subscription, "resolve_transcription_allowance", lambda uid, **kwargs: fake_allowance)

    monkeypatch.setattr(routes.conversations_db, "get_conversation", mock_get_conversation)
    monkeypatch.setattr(routes.conversations_db, "update_conversation", mock_update_conversation)
    monkeypatch.setattr(
        routes.conversations_db,
        "get_conversations_by_id_without_photos",
        mock_get_conversations_by_id_without_photos,
    )
    monkeypatch.setattr(routes.conversations_db, "is_soft_deleted", lambda c: False)
    monkeypatch.setattr(routes.conversations_db, "is_visible_conversation", lambda c, **k: True)

    monkeypatch.setattr(conversations_db, "get_conversation", mock_get_conversation)
    monkeypatch.setattr(conversations_db, "update_conversation", mock_update_conversation)
    monkeypatch.setattr(
        conversations_db,
        "get_conversations_by_id_without_photos",
        mock_get_conversations_by_id_without_photos,
    )

    return mock_conversations, updated_conversations, fake_allowance


# 1. Detail route tests
def test_free_user_accessing_locked_conversation_raises_402(monkeypatch):
    _setup_mock_db(monkeypatch, allowance_reason="subscription_inactive", managed=False)

    with pytest.raises(HTTPException) as exc_info:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "A paid plan is required to access this conversation."


def test_paid_user_within_allowance_heals_and_returns_conversation(monkeypatch):
    mock_conversations, updated, _ = _setup_mock_db(monkeypatch, allowance_reason="plan_within_allowance", managed=True)

    result = routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert result["id"] == CONV_LOCKED_1
    assert result["is_locked"] is False
    assert updated.get(CONV_LOCKED_1) == {"is_locked": False}
    assert mock_conversations[CONV_LOCKED_1]["is_locked"] is False


def test_exhausted_paid_user_accessing_locked_conversation_raises_402(monkeypatch):
    _setup_mock_db(monkeypatch, allowance_reason="plan_allowance_exhausted", managed=True)

    with pytest.raises(HTTPException) as exc_info:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc_info.value.status_code == 402


def test_synthetic_byok_accessing_locked_conversation_raises_402(monkeypatch):
    _setup_mock_db(monkeypatch, allowance_reason="byok", managed=False, byok_active=True)

    with pytest.raises(HTTPException) as exc_info:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc_info.value.status_code == 402


# 2. List route tests
def test_free_user_listing_conversations_leaves_locked_rows_intact(monkeypatch):
    mock_conversations, updated, _ = _setup_mock_db(
        monkeypatch, allowance_reason="subscription_inactive", managed=False
    )
    rows = [dict(mock_conversations[CONV_LOCKED_1])]

    routes._heal_locked_conversations_if_eligible(UID, rows)
    assert rows[0]["is_locked"] is True
    assert CONV_LOCKED_1 not in updated


def test_paid_user_listing_conversations_heals_locked_rows(monkeypatch):
    mock_conversations, updated, _ = _setup_mock_db(monkeypatch, allowance_reason="plan_within_allowance", managed=True)
    rows = [dict(mock_conversations[CONV_LOCKED_1]), dict(mock_conversations[CONV_UNLOCKED])]

    routes._heal_locked_conversations_if_eligible(UID, rows)
    assert rows[0]["is_locked"] is False
    assert rows[1]["is_locked"] is False
    assert updated.get(CONV_LOCKED_1) == {"is_locked": False}


# 3. Exact reference search tests
@pytest.mark.asyncio
async def test_exact_reference_search_recovers_locked_record_for_eligible_paid_user(monkeypatch):
    mock_conversations, updated, _ = _setup_mock_db(monkeypatch, allowance_reason="plan_within_allowance", managed=True)

    search_req = SimpleNamespace(
        page=1,
        per_page=10,
        include_discarded=False,
        speaker_id=None,
    )

    monkeypatch.setattr(routes, "conversation_matches_speaker", lambda c, s: True)
    monkeypatch.setattr(routes, "conversation_matches_date_range", lambda c, s, e: True)
    monkeypatch.setattr(routes, "redact_conversations_for_list", lambda convs: None)

    res = await routes._search_exact_conversation_reference(
        CONV_LOCKED_1,
        search_req,
        UID,
        None,
        None,
    )

    assert len(res["items"]) == 1
    assert res["items"][0]["id"] == CONV_LOCKED_1
    assert res["items"][0]["is_locked"] is False
    assert updated.get(CONV_LOCKED_1) == {"is_locked": False}


@pytest.mark.asyncio
async def test_exact_reference_search_discards_locked_record_for_exhausted_paid_user(monkeypatch):
    mock_conversations, updated, _ = _setup_mock_db(
        monkeypatch, allowance_reason="plan_allowance_exhausted", managed=True
    )

    search_req = SimpleNamespace(
        page=1,
        per_page=10,
        include_discarded=False,
        speaker_id=None,
    )

    monkeypatch.setattr(routes, "conversation_matches_speaker", lambda c, s: True)
    monkeypatch.setattr(routes, "conversation_matches_date_range", lambda c, s, e: True)
    monkeypatch.setattr(routes, "redact_conversations_for_list", lambda convs: None)

    res = await routes._search_exact_conversation_reference(
        CONV_LOCKED_1,
        search_req,
        UID,
        None,
        None,
    )

    assert len(res["items"]) == 0
    assert CONV_LOCKED_1 not in updated


# 4. Subscription endpoint scheduling tests
def test_subscription_endpoint_schedules_recovery_for_eligible_paid_user(monkeypatch):
    submitted_tasks = []
    fake_executor = SimpleNamespace(submit=lambda fn, *args: submitted_tasks.append((fn, args)))
    monkeypatch.setattr(users_routes, "db_executor", fake_executor)

    redis_set_calls = []

    class FakeRedis:
        def set(self, key, val, nx=False, ex=None):
            redis_set_calls.append((key, val, nx, ex))
            return True

    from database import redis_db

    monkeypatch.setattr(redis_db, "r", FakeRedis())

    fake_allowance = SimpleNamespace(
        managed=True,
        reason="plan_within_allowance",
        byok_active=False,
        limit_seconds=18000,
        remaining_seconds=10000,
        as_dict=lambda: {
            "mode": "managed",
            "limit_seconds": 18000,
            "remaining_seconds": 10000,
            "reason": "plan_within_allowance",
        },
    )

    import utils.subscription

    monkeypatch.setattr(utils.subscription, "resolve_transcription_allowance", lambda uid, **k: fake_allowance)
    monkeypatch.setattr(users_routes, "resolve_transcription_allowance", lambda uid, **k: fake_allowance)

    fake_response = SimpleNamespace(
        transcription_allowance=None,
        transcription_seconds_limit=None,
        subscription=SimpleNamespace(limits=SimpleNamespace(transcription_seconds=None)),
    )
    monkeypatch.setattr(users_routes, "_user_subscription_response", lambda *a, **k: fake_response)
    monkeypatch.setattr(users_routes, "fresh_cache_reads", fake_context_manager)

    req = SimpleNamespace(headers={})
    res = users_routes.get_user_subscription_endpoint(req, UID)

    assert len(submitted_tasks) == 1
    assert submitted_tasks[0][1] == (UID,)
    assert any(c[0] == f"users:{UID}:locked_content_recovery:refresh_lease" for c in redis_set_calls)


def test_subscription_endpoint_does_not_schedule_for_exhausted_or_byok(monkeypatch):
    submitted_tasks = []
    fake_executor = SimpleNamespace(submit=lambda fn, *args: submitted_tasks.append((fn, args)))
    monkeypatch.setattr(users_routes, "db_executor", fake_executor)

    from database import redis_db

    monkeypatch.setattr(redis_db, "r", SimpleNamespace(set=lambda *a, **k: True))

    import utils.subscription

    # Test exhausted
    exhausted_allowance = SimpleNamespace(
        managed=True,
        reason="plan_allowance_exhausted",
        byok_active=False,
        limit_seconds=18000,
        remaining_seconds=0,
        as_dict=lambda: {
            "mode": "on_device",
            "limit_seconds": 18000,
            "remaining_seconds": 0,
            "reason": "plan_allowance_exhausted",
        },
    )
    monkeypatch.setattr(utils.subscription, "resolve_transcription_allowance", lambda uid, **k: exhausted_allowance)
    monkeypatch.setattr(users_routes, "resolve_transcription_allowance", lambda uid, **k: exhausted_allowance)
    fake_response = SimpleNamespace(
        transcription_allowance=None,
        transcription_seconds_limit=None,
        subscription=SimpleNamespace(limits=SimpleNamespace(transcription_seconds=None)),
    )
    monkeypatch.setattr(users_routes, "_user_subscription_response", lambda *a, **k: fake_response)
    monkeypatch.setattr(users_routes, "fresh_cache_reads", fake_context_manager)

    req = SimpleNamespace(headers={})
    users_routes.get_user_subscription_endpoint(req, UID)
    assert len(submitted_tasks) == 0

    # Test BYOK
    byok_allowance = SimpleNamespace(
        managed=False,
        reason="byok",
        byok_active=True,
        limit_seconds=None,
        remaining_seconds=None,
        as_dict=lambda: {"mode": "on_device", "limit_seconds": None, "remaining_seconds": None, "reason": "byok"},
    )
    monkeypatch.setattr(utils.subscription, "resolve_transcription_allowance", lambda uid, **k: byok_allowance)
    monkeypatch.setattr(users_routes, "resolve_transcription_allowance", lambda uid, **k: byok_allowance)
    users_routes.get_user_subscription_endpoint(req, UID)
    assert len(submitted_tasks) == 0


def test_subscription_endpoint_handles_redis_or_executor_failure_gracefully(monkeypatch):
    def failing_submit(*a, **k):
        raise RuntimeError("executor pool saturated")

    fake_executor = SimpleNamespace(submit=failing_submit)
    monkeypatch.setattr(users_routes, "db_executor", fake_executor)

    from database import redis_db

    monkeypatch.setattr(redis_db, "r", SimpleNamespace(set=lambda *a, **k: True))

    fake_allowance = SimpleNamespace(
        managed=True,
        reason="plan_within_allowance",
        byok_active=False,
        limit_seconds=18000,
        remaining_seconds=10000,
        as_dict=lambda: {
            "mode": "managed",
            "limit_seconds": 18000,
            "remaining_seconds": 10000,
            "reason": "plan_within_allowance",
        },
    )

    import utils.subscription

    monkeypatch.setattr(utils.subscription, "resolve_transcription_allowance", lambda uid, **k: fake_allowance)
    monkeypatch.setattr(users_routes, "resolve_transcription_allowance", lambda uid, **k: fake_allowance)

    fake_response = SimpleNamespace(
        transcription_allowance=None,
        transcription_seconds_limit=None,
        subscription=SimpleNamespace(limits=SimpleNamespace(transcription_seconds=None)),
    )
    monkeypatch.setattr(users_routes, "_user_subscription_response", lambda *a, **k: fake_response)
    monkeypatch.setattr(users_routes, "fresh_cache_reads", fake_context_manager)

    req = SimpleNamespace(headers={})
    # Must not raise exception
    res = users_routes.get_user_subscription_endpoint(req, UID)
    assert res is not None
