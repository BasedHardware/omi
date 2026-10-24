from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as conversations_db, users as users_db
from models.users import PlanType, Subscription, SubscriptionStatus
from routers import conversations as routes
from utils.conversations import paid_lock_recovery as recovery
from utils.conversations import search as search_module

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

    for row in mock_conversations.values():
        row.update(created_at=datetime(2026, 8, 18, tzinfo=timezone.utc), started_at=None, finished_at=None)
        row['structured'].update(emoji='📝', category='other')
        row['transcript_segments'] = [
            {'text': 'Preserved speech', 'start': 0, 'end': 1, 'is_user': True, 'speaker_id': 0}
        ]

    def mock_get_conversation(uid, conversation_id, **kwargs):
        row = mock_conversations.get(conversation_id)
        return dict(row) if row else None

    updated_conversations = {}

    def mock_update_conversation(uid, conversation_id, patch):
        if conversation_id in mock_conversations:
            mock_conversations[conversation_id].update(patch)
            updated_conversations[conversation_id] = patch
            return True
        return False

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

    monkeypatch.setattr(recovery, "resolve_transcription_allowance", lambda uid, **kwargs: fake_allowance)
    monkeypatch.setattr(
        users_db,
        "get_user_valid_subscription",
        lambda *a, **k: Subscription(plan=PlanType.unlimited, status=SubscriptionStatus.active),
    )
    monkeypatch.setattr(recovery, "fresh_cache_reads", fake_context_manager)
    monkeypatch.setattr(recovery, "external_write_fence", fake_context_manager)
    monkeypatch.setattr(recovery.redis_db, "set_credits_invalidation_signal", lambda uid: None)

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


@pytest.mark.parametrize(
    'plan,status', [(PlanType.basic, SubscriptionStatus.active), (PlanType.unlimited, SubscriptionStatus.inactive)]
)
def test_real_free_or_inactive_subscription_cannot_use_an_unlimited_allowance_override(monkeypatch, plan, status):
    rows, updated, _ = _setup_mock_db(monkeypatch, allowance_reason='plan_unlimited')
    monkeypatch.setattr(users_db, 'get_user_valid_subscription', lambda *a, **k: Subscription(plan=plan, status=status))
    with pytest.raises(HTTPException) as exc:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc.value.status_code == 402
    assert not updated and rows[CONV_LOCKED_1]['is_locked']


@pytest.mark.parametrize('reason', ['allowance_unavailable', 'usage_invalid'])
def test_unknown_allowance_returns_retry_without_a_purchase_denial_or_unlock(monkeypatch, reason):
    rows, updated, _ = _setup_mock_db(monkeypatch, allowance_reason=reason, managed=False)
    with pytest.raises(HTTPException) as exc:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc.value.status_code == 503
    assert not updated and rows[CONV_LOCKED_1]['is_locked']


@pytest.mark.parametrize('failure', [False, 'raise'])
def test_failed_write_never_claims_recovery_and_a_later_retry_preserves_content(monkeypatch, failure):
    rows, updated, _ = _setup_mock_db(monkeypatch)
    before = deepcopy(rows[CONV_LOCKED_1])
    real_write = conversations_db.update_conversation

    def fail(*args, **kwargs):
        if failure == 'raise':
            raise RuntimeError('storage unavailable')
        return False

    monkeypatch.setattr(conversations_db, 'update_conversation', fail)
    with pytest.raises(HTTPException) as exc:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc.value.status_code == 503
    assert rows[CONV_LOCKED_1] == before and not updated
    monkeypatch.setattr(conversations_db, 'update_conversation', real_write)
    restored = routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert restored['is_locked'] is False
    assert rows[CONV_LOCKED_1] == {**before, 'is_locked': False}


def test_redirect_repairs_the_survivor_not_the_deleted_url_record(monkeypatch):
    rows, updated, _ = _setup_mock_db(monkeypatch)
    rows['old'] = {'id': 'old', 'deleted': True, 'sync_merged_into': CONV_LOCKED_1}
    monkeypatch.setattr(conversations_db, 'is_soft_deleted', lambda row: row.get('deleted', False))
    monkeypatch.setattr(
        conversations_db,
        'get_sync_redirected_conversation',
        lambda *args, **kwargs: conversations_db.get_conversation(UID, CONV_LOCKED_1),
    )
    restored = routes._get_valid_conversation_by_id(UID, 'old', follow_sync_bridge=True)
    assert restored['id'] == CONV_LOCKED_1
    assert set(updated) == {CONV_LOCKED_1}
    assert rows['old']['deleted']


def test_processing_backlog_still_requires_its_explicit_choice(monkeypatch):
    rows, updated, _ = _setup_mock_db(monkeypatch)
    rows[CONV_LOCKED_1]['processing_deferred'] = True
    with pytest.raises(HTTPException) as exc:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc.value.status_code == 402
    assert not updated and rows[CONV_LOCKED_1]['processing_deferred']


def test_partial_page_write_failure_is_retryable_without_rewriting_restored_content(monkeypatch):
    rows, updated, _ = _setup_mock_db(monkeypatch)
    before = deepcopy(rows)
    write = conversations_db.update_conversation

    def fail_second(uid, cid, patch):
        return False if cid == CONV_LOCKED_2 else write(uid, cid, patch)

    monkeypatch.setattr(conversations_db, 'update_conversation', fail_second)
    monkeypatch.setattr(
        conversations_db, 'get_conversations_without_photos', lambda *a, **k: deepcopy(list(rows.values()))
    )
    with _http_client() as client:
        assert client.get('/v1/conversations').status_code == 503
        assert rows[CONV_LOCKED_1] == {**before[CONV_LOCKED_1], 'is_locked': False}
        assert rows[CONV_LOCKED_2] == before[CONV_LOCKED_2]
        monkeypatch.setattr(conversations_db, 'update_conversation', write)
        response = client.get('/v1/conversations')
        assert response.status_code == 200, response.text
        assert all(not row['is_locked'] for row in response.json())
    for cid, row in rows.items():
        assert row == {**before[cid], 'is_locked': False}
    assert set(updated) == {CONV_LOCKED_1, CONV_LOCKED_2}


def _http_client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_android_list_refresh_then_detail_and_restart_keep_paid_content_readable(monkeypatch):
    rows, updated, _ = _setup_mock_db(monkeypatch, allowance_reason='plan_unlimited')
    before = deepcopy(rows)

    def list_rows(*args, **kwargs):
        assert kwargs['list_fields_only'] is True
        return deepcopy(list(rows.values()))

    monkeypatch.setattr(conversations_db, 'get_conversations_without_photos', list_rows)
    with _http_client() as client:
        listed = client.get('/v1/conversations')
        assert listed.status_code == 200, listed.text
        assert all(not row['is_locked'] for row in listed.json())
        detail = client.get(f'/v1/conversations/{CONV_LOCKED_1}')
        assert detail.status_code == 200, detail.text
        assert detail.json()['transcript_segments'][0]['text'] == 'Preserved speech'
    # A new HTTP/client lifetime reads the durable patch, not an in-memory unlock.
    with _http_client() as client:
        assert client.get('/v1/conversations').json() == listed.json()
    assert len(updated) == 2
    for cid, row in rows.items():
        assert row == {**before[cid], 'is_locked': False}


@pytest.mark.parametrize('paid', [True, False])
def test_http_keyword_search_retains_paid_locked_hits_before_hydration_but_hides_free_hits(monkeypatch, paid):
    rows, updated, _ = _setup_mock_db(monkeypatch, allowance_reason='plan_unlimited')
    if not paid:
        monkeypatch.setattr(users_db, 'get_user_valid_subscription', lambda *a, **k: Subscription(plan=PlanType.basic))
    fake_client = MagicMock()
    fake_client.collections['conversations'].documents.search.return_value = {
        'hits': [
            {
                'document': {
                    'id': CONV_LOCKED_1,
                    'is_locked': True,
                    'created_at': 1,
                    'started_at': 1,
                    'finished_at': 2,
                    'structured': {'title': 'Historical Meeting', 'overview': 'Overview 1'},
                }
            }
        ]
    }
    monkeypatch.setattr(search_module, 'client', fake_client)
    monkeypatch.setattr(routes.vector_db, 'index', None)
    with _http_client() as client:
        response = client.post(
            '/v1/conversations/search', json={'query': 'Historical', 'include_discarded': True, 'per_page': 1}
        )
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()['items']] == ([CONV_LOCKED_1] if paid else [])
    assert response.json()['total_pages'] == (2 if paid else 1)
    assert bool(updated) is paid
    assert rows[CONV_LOCKED_1]['is_locked'] is not paid


# 1. Detail route tests
def test_free_user_accessing_locked_conversation_raises_402(monkeypatch):
    _setup_mock_db(monkeypatch, allowance_reason="subscription_inactive", managed=False)

    with pytest.raises(HTTPException) as exc_info:
        routes._get_valid_conversation_by_id(UID, CONV_LOCKED_1)
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "A paid plan is required to access this conversation."


@pytest.mark.parametrize('reason', ['plan_within_allowance', 'plan_unlimited', 'usage_budget_available'])
def test_paid_user_within_allowance_heals_and_returns_conversation(monkeypatch, reason):
    mock_conversations, updated, _ = _setup_mock_db(monkeypatch, allowance_reason=reason, managed=True)

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
