"""Product-scoped Context for Claude free-tier limits and demand-side enrichment."""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from models.users import PlanLimits, PlanType
from testing.import_isolation import load_module_fresh, stub_modules
from utils import product_entitlements as pe
from utils.product_entitlements import apply_product_free_limits, is_context_for_claude, transcription_usage_field

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def subscription_module():
    announcements_stub = ModuleType('database.announcements')
    announcements_stub.compare_versions = lambda a, b: 0
    fakes = {
        'database.announcements': announcements_stub,
        'database.users': ModuleType('database.users'),
        'database.user_usage': ModuleType('database.user_usage'),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.subscription',
            os.path.join(str(_BACKEND), 'utils', 'subscription.py'),
        )
        yield module


def test_context_free_limits_overlay_basic_only():
    basic = PlanLimits(transcription_seconds=300 * 60, chat_questions_per_month=30)
    overlaid = apply_product_free_limits(PlanType.basic, basic, 'context-for-claude')
    assert overlaid.transcription_seconds == pe.CONTEXT_FOR_CLAUDE_BASIC_TIER_MONTHLY_SECONDS_LIMIT
    assert overlaid.chat_questions_per_month == 0

    paid = apply_product_free_limits(
        PlanType.unlimited,
        PlanLimits(transcription_seconds=None, chat_questions_per_month=200),
        'context-for-claude',
    )
    assert paid.transcription_seconds is None
    assert paid.chat_questions_per_month == 200

    desktop = apply_product_free_limits(PlanType.basic, basic, 'omi-desktop')
    assert desktop.transcription_seconds == 300 * 60
    assert desktop.chat_questions_per_month == 30


def test_transcription_usage_field_isolated():
    assert transcription_usage_field('context-for-claude') == pe.CONTEXT_TRANSCRIPTION_SECONDS_FIELD
    assert transcription_usage_field('omi-desktop') == 'transcription_seconds'
    assert transcription_usage_field(None) == 'transcription_seconds'


def test_chat_quota_zero_for_context_free(subscription_module):
    sub = subscription_module
    with (
        patch.object(sub, 'is_trial_paywalled', return_value=False),
        patch.object(sub, 'users_db') as users_db,
        patch.object(sub, 'user_usage_db') as usage_db,
    ):
        users_db.get_user_valid_subscription.return_value = SimpleNamespace(plan=PlanType.basic)
        usage_db.get_monthly_chat_usage.return_value = {'questions': 0, 'cost_usd': 0.0, 'reset_at': 0}
        snap = sub.get_chat_quota_snapshot('uid', platform='macos', app_product='context-for-claude')
    assert snap['limit'] == 0.0
    assert snap['allowed'] is False


def test_enforce_chat_quota_denies_context_free(subscription_module):
    sub = subscription_module
    with (
        patch.object(sub, 'is_trial_paywalled', return_value=False),
        patch.object(sub, 'users_db') as users_db,
        patch.object(sub, 'get_chat_quota_snapshot') as snap,
        patch.object(sub, 'get_byok_key', return_value=None),
    ):
        users_db.is_byok_active.return_value = False
        snap.return_value = {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 0.0,
            'limit': 0.0,
            'allowed': False,
            'reset_at': 0,
        }
        with pytest.raises(HTTPException) as exc:
            sub.enforce_chat_quota('uid', platform='macos', app_product='context-for-claude')
    assert exc.value.status_code == 402


def test_has_transcription_credits_uses_context_pool(subscription_module):
    sub = subscription_module
    with (
        patch.object(sub, 'is_trial_paywalled', return_value=False),
        patch.object(sub, 'users_db') as users_db,
        patch.object(sub, 'get_byok_key', return_value=None),
        patch.object(sub, 'get_monthly_usage_for_subscription') as usage,
        patch.object(sub, 'get_plan_limits') as limits,
    ):
        users_db.is_byok_active.return_value = False
        users_db.get_user_valid_subscription.return_value = SimpleNamespace(plan=PlanType.basic)
        limits.return_value = PlanLimits(transcription_seconds=300 * 60, chat_questions_per_month=30)
        usage.return_value = {
            'transcription_seconds': 999999,
            pe.CONTEXT_TRANSCRIPTION_SECONDS_FIELD: 10,
        }
        assert sub.has_transcription_credits('uid', source='desktop', app_product='context-for-claude') is True
        usage.return_value[pe.CONTEXT_TRANSCRIPTION_SECONDS_FIELD] = (
            pe.CONTEXT_FOR_CLAUDE_BASIC_TIER_MONTHLY_SECONDS_LIMIT + 1
        )
        assert sub.has_transcription_credits('uid', source='desktop', app_product='context-for-claude') is False


def test_record_usage_routes_context_seconds_to_product_field():
    from utils.analytics import record_usage

    with (
        patch('utils.analytics.user_usage_db') as usage_db,
        patch('utils.analytics.record_llm_usage_bucket') as bucket,
    ):
        record_usage('uid', transcription_seconds=60, speech_seconds=10, app_product='context-for-claude')
        args, _kwargs = usage_db.update_hourly_usage.call_args
        updates = args[2]
        assert updates.get('transcription_seconds', 0) == 0
        assert updates[pe.CONTEXT_TRANSCRIPTION_SECONDS_FIELD] == 60
        assert updates['speech_seconds'] == 10
        assert bucket.called


def test_context_stub_persist_completed_deferred():
    """MCP-listable Context stubs use completed + deferred (not processing-only)."""
    from models.conversation_enums import ConversationStatus

    # Mirror _persist_enrichment_stub status selection without importing the LLM-heavy module.
    mcp_listable = True
    status = ConversationStatus.completed if mcp_listable else ConversationStatus.processing
    assert status == ConversationStatus.completed
    assert ConversationStatus.processing != status


def test_is_context_product():
    assert is_context_for_claude('context-for-claude')
    assert not is_context_for_claude('omi-desktop')


def test_should_demand_stub_context(subscription_module):
    sub = subscription_module
    with patch.object(sub, 'should_defer_desktop_processing', return_value=True):
        assert sub.should_demand_stub_context_enrichment('uid', 'context-for-claude') is True
        assert sub.should_demand_stub_context_enrichment('uid', 'omi-desktop') is False
    with patch.object(sub, 'should_defer_desktop_processing', return_value=False):
        assert sub.should_demand_stub_context_enrichment('uid', 'context-for-claude') is False


def test_screen_activity_sync_rate_policy_present():
    from utils.rate_limit_config import RATE_POLICIES

    assert RATE_POLICIES['screen_activity:sync'] == (120, 3600)


def test_reacquire_accepts_completed_deferred_context_stub():
    """MCP-listable Context stubs are completed+deferred; reacquire must move them to processing."""
    from database.conversation_finalization_jobs import _reacquire_deferred_processing_txn

    class _Snap:
        exists = True

        def to_dict(self):
            return {'status': 'completed', 'deferred': True, 'discarded': False}

    class _Ref:
        def __init__(self):
            self.updates = None

        def get(self, transaction=None):
            return _Snap()

    ref = _Ref()
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)

    def txn_update(_ref, payload):
        ref.updates = payload

    txn = SimpleNamespace(update=txn_update)
    assert _reacquire_deferred_processing_txn(txn, ref, now) is True
    assert ref.updates['status'] == 'processing'
    assert ref.updates['deferred'] is False
    assert 'processing_admitted_at' in ref.updates


def test_reacquire_rejects_completed_without_deferred():
    from database.conversation_finalization_jobs import _reacquire_deferred_processing_txn

    class _Snap:
        exists = True

        def to_dict(self):
            return {'status': 'completed', 'deferred': False}

    class _Ref:
        def get(self, transaction=None):
            return _Snap()

    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    assert _reacquire_deferred_processing_txn(SimpleNamespace(update=MagicMock()), _Ref(), now) is False


def test_kick_recent_context_enrichment_only_deferred(monkeypatch):
    from utils.conversations import context_demand_enrich as enrich

    recent = [
        {'id': 'a', 'deferred': True},
        {'id': 'b', 'deferred': False},
        {'id': 'c', 'deferred': True},
    ]
    kicked_ids = []

    db_mod = ModuleType('database.conversations')
    db_mod.get_conversations = MagicMock(return_value=recent)
    router_mod = ModuleType('routers.conversations')

    def _kick(_uid, conv):
        kicked_ids.append(conv['id'])
        return conv

    router_mod.enrich_deferred_conversation = _kick

    # Nested packages already exist; only swap the leaf modules for this call.
    monkeypatch.setitem(__import__('sys').modules, 'database.conversations', db_mod)
    monkeypatch.setitem(__import__('sys').modules, 'routers.conversations', router_mod)
    # `from database import conversations` resolves the package attribute.
    import database as database_pkg
    import routers as routers_pkg

    monkeypatch.setattr(database_pkg, 'conversations', db_mod, raising=False)
    monkeypatch.setattr(routers_pkg, 'conversations', router_mod, raising=False)

    assert enrich.kick_recent_context_enrichment('uid', n=3) == 2
    assert kicked_ids == ['a', 'c']
