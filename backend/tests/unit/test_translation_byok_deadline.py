"""Viewed-lane BYOK transport bounds (Luna R1 regression).

The viewed translation policy enforces a hard per-request deadline. When the
backend resolves the Gemini client through the direct BYOK branch of
``get_llm`` — which bypasses the gateway options that carry the deadline — the
transport must still be constructed with that deadline, or a slow provider can
occupy a translation worker for the chat-default 120 seconds.
"""

from unittest.mock import patch

import utils.llm.clients as clients
from config.translation import resolve_translation_profile, viewed_translation_profile


def test_viewed_profile_deadline_reaches_direct_byok_client():
    profile = viewed_translation_profile(resolve_translation_profile({}), _ondemand_config())
    assert profile.policy_version == 'viewed_v1'
    assert profile.deadline_seconds < 120

    captured: dict[str, object] = {}

    def fake_cached(model, api_key, ctor_kwargs):
        captured['request_timeout'] = ctor_kwargs.get('request_timeout')
        captured['max_retries'] = ctor_kwargs.get('max_retries')
        return object()

    with (
        patch.object(clients, 'get_byok_profile', return_value={}),
        patch.object(clients, 'get_byok_key', return_value='AIza-test-byok'),
        patch.object(clients, 'should_route_features_through_gateway', return_value=False),
        patch.object(clients, '_get_model_config', return_value=('gemini-2.5-flash-lite', 'gemini')),
        patch.object(clients, '_cached_openai_chat', side_effect=fake_cached),
    ):
        clients.get_llm('translation', request_timeout=profile.deadline_seconds, max_retries=0)

    assert captured['request_timeout'] == profile.deadline_seconds
    assert captured['max_retries'] == 0


def _ondemand_config():
    from config.translation import resolve_ondemand_config

    return resolve_ondemand_config(
        {
            'TRANSLATION_DEMAND_GATE_ENABLED': 'true',
            'TRANSLATION_ONDEMAND_GEMINI_ENABLED': 'true',
            'TRANSLATION_ONDEMAND_UID_DAILY_CHARS': '1000000',
            'TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS': '100000000',
        }
    )
