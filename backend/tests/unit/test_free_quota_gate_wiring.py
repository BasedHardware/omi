"""Wiring tests: free-tier monthly chat quota gate on user-initiated LLM endpoints.

Regression for the enforcement-coverage gap where a free user past
FREE_CHAT_QUESTIONS_PER_MONTH could still trigger managed LLM spend through
daily-summary regeneration, goal progress extraction, app description
generation, and the omni realtime relay. Each test proves the endpoint calls
the shared gate BEFORE doing LLM work and lets the 402 propagate.

`enforce_chat_quota`'s own decision logic is covered in test_chat_quota.py;
these tests only pin the call-site wiring, so the gate is patched at each
router module (the sanctioned monkeypatch-on-module seam).
"""

import asyncio
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('DEEPGRAM_API_KEY', 'dg-test-fake-for-unit-tests')
os.environ.setdefault('GOOGLE_API_KEY', 'goog-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from fastapi import HTTPException
from testing.import_isolation import AutoMockModule, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _make_fakes() -> dict:
    fakes: dict = {
        "database._client": AutoMockModule("database._client"),
        "database.redis_db": AutoMockModule("database.redis_db"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.memories": AutoMockModule("database.memories"),
        "database.chat": AutoMockModule("database.chat"),
        "database.users": AutoMockModule("database.users"),
        "database.user_usage": AutoMockModule("database.user_usage"),
        "database.llm_usage": AutoMockModule("database.llm_usage"),
        "database.announcements": AutoMockModule("database.announcements"),
        "database.notifications": AutoMockModule("database.notifications"),
        "database.daily_summaries": AutoMockModule("database.daily_summaries"),
        "database.app_review_config": AutoMockModule("database.app_review_config"),
        "database.webhook_health": AutoMockModule("database.webhook_health"),
        "database.action_items": AutoMockModule("database.action_items"),
        "database.goals": AutoMockModule("database.goals"),
        "database.workstreams": AutoMockModule("database.workstreams"),
        "database.apps": AutoMockModule("database.apps"),
        "utils.other.storage": AutoMockModule("utils.other.storage"),
        "utils.apps": AutoMockModule("utils.apps"),
        "utils.stripe": AutoMockModule("utils.stripe"),
        "utils.twilio_service": AutoMockModule("utils.twilio_service"),
        "utils.notifications": AutoMockModule("utils.notifications"),
        "utils.llm.external_integrations": AutoMockModule("utils.llm.external_integrations"),
        "utils.llm.goals": AutoMockModule("utils.llm.goals"),
        "utils.llm.persona": AutoMockModule("utils.llm.persona"),
        "utils.llm.app_generator": AutoMockModule("utils.llm.app_generator"),
        "utils.llm.app_generation_prompts": AutoMockModule("utils.llm.app_generation_prompts"),
        "utils.llm.usage_tracker": AutoMockModule("utils.llm.usage_tracker"),
        "utils.llm.clients": AutoMockModule("utils.llm.clients"),
        "utils.llm.gateway_client": AutoMockModule("utils.llm.gateway_client"),
    }

    streaming = ModuleType("utils.stt.streaming")
    streaming.deepgram_nova3_multi_languages = ['en']
    fakes["utils.stt.streaming"] = streaming

    return fakes


@pytest.fixture(scope="module", autouse=True)
def _quota_gate_isolation():
    with stub_modules(_make_fakes()):
        # Warm the heavy router import graphs during fixture setup so the
        # first test's call phase doesn't pay them (fast-unit CPU guard).
        import routers.apps  # noqa: F401
        import routers.goals  # noqa: F401
        import routers.omni_relay  # noqa: F401
        import routers.users  # noqa: F401

        yield


def _quota_402() -> HTTPException:
    return HTTPException(status_code=402, detail={'error': 'quota_exceeded'})


# ---------------------------------------------------------------------------
# routers/users.py — daily summary test + regenerate
# ---------------------------------------------------------------------------


class TestDailySummaryGates:
    def test_test_daily_summary_blocked_past_cap(self):
        import routers.users as users_router

        with patch.object(users_router, 'enforce_chat_quota', side_effect=_quota_402()) as gate, patch.object(
            users_router, 'notification_db'
        ) as notif_db:
            with pytest.raises(HTTPException) as exc_info:
                users_router.test_daily_summary(request=None, uid='u1', x_app_platform='macos')
            assert exc_info.value.status_code == 402
            gate.assert_called_once_with('u1', platform='macos')
            notif_db.get_user_time_zone.assert_not_called()

    def test_regenerate_daily_summary_blocked_past_cap(self):
        import routers.users as users_router

        with patch.object(users_router, 'enforce_chat_quota', side_effect=_quota_402()) as gate, patch.object(
            users_router, 'daily_summaries_db'
        ) as summaries_db:
            with pytest.raises(HTTPException) as exc_info:
                users_router.regenerate_daily_summary('summary-1', uid='u1', x_app_platform='macos')
            assert exc_info.value.status_code == 402
            gate.assert_called_once_with('u1', platform='macos')
            summaries_db.get_daily_summary.assert_not_called()

    def test_regenerate_daily_summary_allowed_proceeds(self):
        import routers.users as users_router

        with patch.object(users_router, 'enforce_chat_quota') as gate, patch.object(
            users_router, 'daily_summaries_db'
        ) as summaries_db:
            summaries_db.get_daily_summary.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                users_router.regenerate_daily_summary('summary-1', uid='u1', x_app_platform='macos')
            # Gate passed; endpoint proceeded to the summary lookup (404, not 402).
            assert exc_info.value.status_code == 404
            gate.assert_called_once()
            summaries_db.get_daily_summary.assert_called_once_with('u1', 'summary-1')


# ---------------------------------------------------------------------------
# routers/goals.py — progress extraction
# ---------------------------------------------------------------------------


class TestGoalsGate:
    def test_extract_progress_blocked_past_cap(self):
        import routers.goals as goals_router

        with patch.object(goals_router, 'enforce_chat_quota', side_effect=_quota_402()) as gate, patch.object(
            goals_router, 'extract_and_update_goal_progress'
        ) as llm:
            request = goals_router.ProgressExtractRequest(text='ran 5k today')
            with pytest.raises(HTTPException) as exc_info:
                goals_router.extract_and_update_progress(request, uid='u1', x_app_platform='macos')
            assert exc_info.value.status_code == 402
            gate.assert_called_once_with('u1', platform='macos')
            llm.assert_not_called()

    def test_extract_progress_allowed_proceeds(self):
        import routers.goals as goals_router

        with patch.object(goals_router, 'enforce_chat_quota') as gate, patch.object(
            goals_router, 'extract_and_update_goal_progress', return_value=None
        ) as llm:
            request = goals_router.ProgressExtractRequest(text='ran 5k today')
            result = goals_router.extract_and_update_progress(request, uid='u1', x_app_platform='macos')
            assert result == {'updated': False, 'reason': 'No active goal'}
            gate.assert_called_once()
            llm.assert_called_once_with('u1', 'ran 5k today')


# ---------------------------------------------------------------------------
# routers/apps.py — app description generators
# ---------------------------------------------------------------------------


class TestAppGeneratorGates:
    def test_generate_description_blocked_past_cap(self):
        import routers.apps as apps_router

        with patch.object(apps_router, 'enforce_chat_quota', side_effect=_quota_402()) as gate, patch.object(
            apps_router, 'generate_description'
        ) as llm:
            data = apps_router.GenerateDescriptionRequest(name='My App', description='does things')
            with pytest.raises(HTTPException) as exc_info:
                apps_router.generate_description_endpoint(data, uid='u1', x_app_platform='macos')
            assert exc_info.value.status_code == 402
            gate.assert_called_once_with('u1', platform='macos')
            llm.assert_not_called()

    def test_generate_description_emoji_blocked_past_cap(self):
        import routers.apps as apps_router

        with patch.object(apps_router, 'enforce_chat_quota', side_effect=_quota_402()) as gate:
            data = apps_router.GenerateDescriptionEmojiRequest(name='My App', prompt='be helpful')
            with pytest.raises(HTTPException) as exc_info:
                apps_router.generate_description_and_emoji_endpoint(data, uid='u1', x_app_platform='macos')
            assert exc_info.value.status_code == 402
            gate.assert_called_once_with('u1', platform='macos')


# ---------------------------------------------------------------------------
# routers/omni_relay.py — realtime relay WebSocket
# ---------------------------------------------------------------------------


def _fake_websocket(provider: str = 'gemini') -> MagicMock:
    ws = MagicMock()
    ws.headers = {'authorization': 'Bearer token'}
    ws.query_params = {'provider': provider}
    ws.close = AsyncMock()
    ws.accept = AsyncMock()
    return ws


async def _passthrough_run_blocking(_executor, fn, *args):
    return fn(*args)


class TestOmniRelayGate:
    def test_relay_closes_for_free_user_past_cap(self):
        import routers.omni_relay as relay
        from models.users import PlanType

        ws = _fake_websocket()
        with patch.object(relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface'), patch.object(
            relay, 'run_blocking', _passthrough_run_blocking
        ), patch.object(relay, '_verify_ws_auth', return_value='u1'), patch.object(
            relay, 'extract_byok_from_websocket', return_value={}
        ), patch.object(
            relay, 'is_trial_paywalled', return_value=False
        ), patch.object(
            relay, 'get_chat_quota_snapshot', return_value={'plan': PlanType.basic, 'allowed': False}
        ) as snapshot:
            asyncio.run(relay.omni_relay(ws))
            snapshot.assert_called_once_with('u1', 'desktop')
            ws.close.assert_awaited_once_with(code=1008, reason='quota_exceeded')
            ws.accept.assert_not_awaited()

    def test_relay_skips_quota_for_byok_session(self):
        import routers.omni_relay as relay

        # Unsupported provider makes the handler exit right AFTER the gates,
        # so the test stays deterministic without faking the upstream socket.
        ws = _fake_websocket(provider='unsupported-provider')
        with patch.object(relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface'), patch.object(
            relay, 'run_blocking', _passthrough_run_blocking
        ), patch.object(relay, '_verify_ws_auth', return_value='u1'), patch.object(
            relay, 'extract_byok_from_websocket', return_value={'openai': 'sk-user'}
        ), patch.object(
            relay, 'set_byok_keys'
        ), patch.object(
            relay, 'validate_byok_websocket', return_value=None
        ), patch.object(
            relay, 'is_trial_paywalled', return_value=False
        ), patch.object(
            relay, 'get_chat_quota_snapshot'
        ) as snapshot:
            asyncio.run(relay.omni_relay(ws))
            snapshot.assert_not_called()
            ws.close.assert_awaited_once()
            assert ws.close.await_args.kwargs.get('code') == 1011

    def test_relay_allows_free_user_under_cap(self):
        import routers.omni_relay as relay
        from models.users import PlanType

        ws = _fake_websocket(provider='unsupported-provider')
        with patch.object(relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface'), patch.object(
            relay, 'run_blocking', _passthrough_run_blocking
        ), patch.object(relay, '_verify_ws_auth', return_value='u1'), patch.object(
            relay, 'extract_byok_from_websocket', return_value={}
        ), patch.object(
            relay, 'is_trial_paywalled', return_value=False
        ), patch.object(
            relay, 'get_chat_quota_snapshot', return_value={'plan': PlanType.basic, 'allowed': True}
        ):
            asyncio.run(relay.omni_relay(ws))
            # Past the quota gate; exits at provider validation (1011), not 1008.
            ws.close.assert_awaited_once()
            assert ws.close.await_args.kwargs.get('code') == 1011
