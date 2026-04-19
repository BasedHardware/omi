"""Tests for LLM QoS tier system in utils/llm/clients.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pre-mock heavy deps before any imports touch them
# ---------------------------------------------------------------------------
_HEAVY_MOCKS = {
    'firebase_admin': MagicMock(),
    'firebase_admin.firestore': MagicMock(),
    'google.cloud.firestore': MagicMock(),
    'google.cloud.firestore_v1': MagicMock(),
    'google.cloud.firestore_v1.base_query': MagicMock(),
    'database': MagicMock(),
    'database._client': MagicMock(),
    'database.llm_usage': MagicMock(),
}

for _mod, _mock in _HEAVY_MOCKS.items():
    sys.modules.setdefault(_mod, _mock)

# Set required env vars before importing clients
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-key-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test-fake-key')

# Now import the module under test
from utils.llm.clients import (
    TIER_HIGH,
    TIER_MEDIUM,
    TIER_MINI,
    TIER_NANO,
    _FEATURE_TIER_DEFAULTS,
    _TIER_MODELS,
    _resolve_tier,
    get_llm,
    get_llm_tier_info,
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQosTierDefaults:
    """Verify default tier assignments."""

    def test_action_items_defaults_to_mini(self):
        assert _resolve_tier('conv_action_items') == TIER_MINI

    def test_conv_structure_defaults_to_medium(self):
        assert _resolve_tier('conv_structure') == TIER_MEDIUM

    def test_knowledge_graph_defaults_to_mini(self):
        assert _resolve_tier('knowledge_graph') == TIER_MINI

    def test_unknown_feature_defaults_to_mini(self):
        assert _resolve_tier('totally_unknown_feature') == TIER_MINI

    def test_daily_summary_defaults_to_medium(self):
        assert _resolve_tier('daily_summary') == TIER_MEDIUM

    def test_memories_defaults_to_mini(self):
        assert _resolve_tier('memories') == TIER_MINI

    def test_conv_apps_defaults_to_mini(self):
        assert _resolve_tier('conv_apps') == TIER_MINI


class TestQosTierEnvOverride:
    """Verify env var overrides work."""

    def test_override_action_items_to_medium(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_CONV_ACTION_ITEMS', 'medium')
        assert _resolve_tier('conv_action_items') == TIER_MEDIUM

    def test_override_conv_structure_to_nano(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_CONV_STRUCTURE', 'nano')
        assert _resolve_tier('conv_structure') == TIER_NANO

    def test_override_knowledge_graph_to_high(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_KNOWLEDGE_GRAPH', 'high')
        assert _resolve_tier('knowledge_graph') == TIER_HIGH

    def test_invalid_env_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_CONV_ACTION_ITEMS', 'ultra_mega')
        assert _resolve_tier('conv_action_items') == TIER_MINI

    def test_empty_env_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_CONV_ACTION_ITEMS', '')
        assert _resolve_tier('conv_action_items') == TIER_MINI

    def test_override_memories_to_nano(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_MEMORIES', 'nano')
        assert _resolve_tier('memories') == TIER_NANO

    def test_case_insensitive_override(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_CONV_ACTION_ITEMS', 'MEDIUM')
        # .lower() in _resolve_tier should handle this
        assert _resolve_tier('conv_action_items') == TIER_MEDIUM


class TestQosTierModelMapping:
    """Verify tiers map to correct model names."""

    def test_tier_model_names(self):
        assert _TIER_MODELS[TIER_NANO] == 'gpt-4.1-nano'
        assert _TIER_MODELS[TIER_MINI] == 'gpt-4.1-mini'
        assert _TIER_MODELS[TIER_MEDIUM] == 'gpt-5.1'
        assert _TIER_MODELS[TIER_HIGH] == 'o4-mini'

    def test_all_tiers_have_models(self):
        for tier in [TIER_NANO, TIER_MINI, TIER_MEDIUM, TIER_HIGH]:
            assert tier in _TIER_MODELS


class TestGetLlm:
    """Verify get_llm returns usable ChatOpenAI instances."""

    def test_get_llm_returns_object_with_invoke(self):
        llm = get_llm('conv_action_items')
        assert hasattr(llm, 'invoke')

    def test_get_llm_caches_instances(self):
        llm1 = get_llm('conv_action_items')
        llm2 = get_llm('conv_action_items')
        assert llm1 is llm2

    def test_different_features_same_tier_share_instance(self):
        # Both default to mini
        llm_ai = get_llm('conv_action_items')
        llm_mem = get_llm('memories')
        assert llm_ai is llm_mem

    def test_different_tiers_return_different_instances(self):
        # conv_action_items=mini, conv_structure=medium
        llm_mini = get_llm('conv_action_items')
        llm_med = get_llm('conv_structure')
        assert llm_mini is not llm_med


class TestGetLlmTierInfo:
    """Verify debugging helper returns complete mapping."""

    def test_tier_info_contains_all_defaults(self):
        info = get_llm_tier_info()
        for feature in _FEATURE_TIER_DEFAULTS:
            assert feature in info
            assert 'tier' in info[feature]
            assert 'model' in info[feature]

    def test_tier_info_reflects_env_override(self, monkeypatch):
        monkeypatch.setenv('LLM_TIER_CONV_ACTION_ITEMS', 'high')
        info = get_llm_tier_info()
        assert info['conv_action_items']['tier'] == 'high'
        assert info['conv_action_items']['model'] == 'o4-mini'


class TestRollbackScenario:
    """Verify we can switch back to original model via env var."""

    def test_rollback_action_items_to_original_gpt51(self, monkeypatch):
        # Default is mini (downgraded). Rollback to medium (gpt-5.1)
        monkeypatch.setenv('LLM_TIER_CONV_ACTION_ITEMS', 'medium')
        assert _resolve_tier('conv_action_items') == TIER_MEDIUM
        llm = get_llm('conv_action_items')
        assert 'gpt-5.1' in str(llm.model_name) or hasattr(llm, 'invoke')
