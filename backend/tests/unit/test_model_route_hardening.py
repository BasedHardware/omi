"""Hardening for the model auto-router route loading (review follow-ups).

1. Persisted dynamic routes are allowlisted by model. ``_is_dynamic_route_allowed`` now fails closed
   when the route's model is not one of the models used by the static QoS profiles (the only models
   the auto-router ever selects from), so a corrupted, stale, or hand-edited Firestore route document
   cannot redirect a feature to an arbitrary model within an allowed provider class.

2. ``get_dynamic_route_info`` (the ``get_model``/``get_llm`` hot path) no longer triggers a
   synchronous Firestore load. The background refresh loop maintains the in-memory route table, so
   ordinary LLM calls inside async request/agent paths never block the event loop on a Firestore read.

model_config pulls in prometheus_client transitively (utils.metrics -> gateway_client), which is
stubbed here so the module imports without the dependency installed.
"""

import sys
import types
from unittest.mock import MagicMock, patch

if 'prometheus_client' not in sys.modules:
    _prom = types.ModuleType('prometheus_client')
    _prom.Counter = MagicMock()
    _prom.Gauge = MagicMock()
    _prom.Histogram = MagicMock()
    _prom.generate_latest = MagicMock()
    _prom.CONTENT_TYPE_LATEST = 'text/plain'
    sys.modules['prometheus_client'] = _prom

import utils.llm.model_config as mc  # noqa: E402

# --- Issue 1: dynamic routes are model-allowlisted (fail closed) ---


def test_known_route_pairs_includes_profile_pairs_and_excludes_unknown():
    pairs = mc._known_route_pairs()
    assert ('gpt-5.4-mini', 'openai') in pairs
    assert ('gpt-4.1-mini', 'openai') in pairs
    assert ('totally-made-up-model-9000', 'openai') not in pairs


def test_dynamic_route_allowed_for_known_pair():
    with patch.object(mc, '_active_profile', {'feat_x': ('gpt-4.1-mini', 'openai')}), patch.object(
        mc, '_PINNED_FEATURES', {}
    ):
        assert mc._is_dynamic_route_allowed('feat_x', 'gpt-4.1-mini', 'openai') is True


def test_dynamic_route_rejected_for_unknown_model():
    # An allowed provider but an unknown model must fail closed -- this is the core of the issue.
    with patch.object(mc, '_active_profile', {'feat_x': ('gpt-4.1-mini', 'openai')}), patch.object(
        mc, '_PINNED_FEATURES', {}
    ):
        assert mc._is_dynamic_route_allowed('feat_x', 'evil-model-9000', 'openai') is False


def test_dynamic_route_rejected_for_known_model_wrong_provider():
    # A known model paired with a provider it is never used with must also fail closed.
    with patch.object(mc, '_active_profile', {'feat_x': ('gpt-4.1-mini', 'openai')}), patch.object(
        mc, '_PINNED_FEATURES', {}
    ):
        assert mc._is_dynamic_route_allowed('feat_x', 'gpt-4.1-mini', 'gemini') is False


# --- Issue 2: the hot path performs no synchronous Firestore load ---


def test_get_dynamic_route_info_does_not_trigger_loader():
    loader = MagicMock(return_value=None)
    # _auto_router_enabled True + a non-byok active profile is exactly when the pre-fix hot path would
    # have invoked the (synchronous Firestore) loader; the fix must not call it regardless.
    with patch.object(mc, '_auto_router_enabled', True), patch.object(mc, '_byok_profile_name', '__never_byok__'):
        mc.set_dynamic_route_loader(loader)  # resets the refresh timer, so a lazy reload would fire now
        try:
            mc.get_dynamic_route_info('chat_agent')
            loader.assert_not_called()
        finally:
            mc.set_dynamic_route_loader(None)
