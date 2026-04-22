"""Tests for the regolo.ai OpenAI-compat BYOK routing proxy.

Covers: base_url swap, api_key swap, chat_template_kwargs.enable_thinking=false
injection, fallback when no BYOK key, extra_body merge preservation.

See also desktop/docs/REGOLO_INTEGRATION.md for the full integration spec.
"""

import os
import sys
from contextvars import copy_context
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level stubs: prevent Firestore/Redis/Anthropic init on import.
# Mirrors the setup in test_byok_security.py so this file runs standalone.
# ---------------------------------------------------------------------------
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test-fake')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# utils/llm/clients.py imports usage_tracker which reaches database.llm_usage
# which pulls in google-cloud-firestore. Stub the chain so the import graph
# stops at our proxy class.
sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.redis_db', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('database.user_usage', MagicMock())
sys.modules.setdefault('database.llm_usage', MagicMock())


def _reset_caches():
    """Clear the in-memory proxy caches between tests so swapped kwargs
    don't leak across cases."""
    from utils.llm.clients import _openai_cache

    _openai_cache.clear()


class TestRegoloBYOKRouting:
    """The regolo proxy should swap base_url + api_key + extra_body when
    the per-request BYOK key is present, and fall back transparently otherwise."""

    def test_no_byok_key_returns_default(self):
        """Without a regolo BYOK key in the context, _resolve() returns the default client."""
        from utils.llm.clients import _RegoloOpenAIProxy

        default = MagicMock(name='default_chat_openai')
        proxy = _RegoloOpenAIProxy(default=default, regolo_model='minimax-m2.5', ctor_kwargs={})

        def _run():
            resolved = proxy._resolve()
            assert resolved is default, 'expected default when no BYOK key set'

        copy_context().run(_run)

    def test_byok_key_routes_to_regolo(self):
        """With a regolo BYOK key in the context, the proxy must build a new
        ChatOpenAI pointing at api.regolo.ai with the user's key."""
        from utils.byok import set_byok_keys
        from utils.llm.clients import REGOLO_OPENAI_BASE_URL, _RegoloOpenAIProxy

        default = MagicMock(name='default_chat_openai')
        built = MagicMock(name='regolo_chat_openai')
        ctor_calls = []

        def fake_chat_openai(*, model, api_key, **kwargs):
            ctor_calls.append({'model': model, 'api_key': api_key, **kwargs})
            return built

        with patch('utils.llm.clients.ChatOpenAI', side_effect=fake_chat_openai):
            proxy = _RegoloOpenAIProxy(
                default=default,
                regolo_model='minimax-m2.5',
                ctor_kwargs={},
            )

            def _run():
                set_byok_keys({'regolo': 'sk-regolo-test-abc'})
                _reset_caches()
                resolved = proxy._resolve()
                assert resolved is built
                assert len(ctor_calls) == 1
                call = ctor_calls[0]
                assert call['model'] == 'minimax-m2.5'
                assert call['api_key'] == 'sk-regolo-test-abc'
                assert call['base_url'] == REGOLO_OPENAI_BASE_URL

            copy_context().run(_run)

    def test_enable_thinking_false_injected(self):
        """The proxy must inject chat_template_kwargs.enable_thinking=false so OSS
        thinking models (MiniMax, Qwen3.5) return content instead of
        finish_reason=length from exhausted reasoning budget."""
        from utils.byok import set_byok_keys
        from utils.llm.clients import _RegoloOpenAIProxy

        captured: list = []

        def fake_chat_openai(**kwargs):
            captured.append(kwargs)
            return MagicMock()

        default = MagicMock()
        with patch('utils.llm.clients.ChatOpenAI', side_effect=fake_chat_openai):
            proxy = _RegoloOpenAIProxy(
                default=default,
                regolo_model='minimax-m2.5',
                ctor_kwargs={},
            )

            def _run():
                set_byok_keys({'regolo': 'sk-regolo-enable-thinking'})
                _reset_caches()
                proxy._resolve()
                assert len(captured) == 1
                extra_body = captured[0].get('extra_body', {})
                chat_tpl = extra_body.get('chat_template_kwargs', {})
                assert chat_tpl.get('enable_thinking') is False, (
                    'regolo proxy must disable thinking for OSS models; got '
                    f'extra_body={extra_body!r}'
                )

            copy_context().run(_run)

    def test_existing_extra_body_is_preserved(self):
        """Caller-provided extra_body (e.g. prompt cache hints for non-regolo path)
        must merge with enable_thinking, not be overwritten."""
        from utils.byok import set_byok_keys
        from utils.llm.clients import _RegoloOpenAIProxy

        captured: list = []

        def fake_chat_openai(**kwargs):
            captured.append(kwargs)
            return MagicMock()

        default = MagicMock()
        with patch('utils.llm.clients.ChatOpenAI', side_effect=fake_chat_openai):
            proxy = _RegoloOpenAIProxy(
                default=default,
                regolo_model='Llama-3.3-70B-Instruct',
                ctor_kwargs={'extra_body': {'custom_flag': 'keep_me'}, 'callbacks': []},
            )

            def _run():
                set_byok_keys({'regolo': 'sk-regolo-merge-test'})
                _reset_caches()
                proxy._resolve()
                extra_body = captured[0].get('extra_body', {})
                assert extra_body.get('custom_flag') == 'keep_me', 'original extra_body key lost'
                assert extra_body.get('chat_template_kwargs', {}).get('enable_thinking') is False

            copy_context().run(_run)


class TestRegoloProviderClassification:
    """Verify _classify_provider routes regolo-hosted model IDs to the 'regolo'
    path and leaves OpenAI / Anthropic / OpenRouter / Perplexity models alone."""

    @pytest.mark.parametrize(
        'model',
        [
            'minimax-m2.5',
            'Llama-3.3-70B-Instruct',
            'qwen3.5-122b',
            'qwen3.5-9b',
            'qwen3-coder-next',
            'Qwen3-Embedding-8B',
            'mistral-small-4-119b',
            'apertus-70b',
            'gpt-oss-120b',
            'gemma4-31b',
        ],
    )
    def test_regolo_models_classify_as_regolo(self, model):
        from utils.llm.clients import _classify_provider

        assert _classify_provider(model) == 'regolo', (
            f'{model!r} should classify as regolo; got {_classify_provider(model)!r}'
        )

    def test_openai_models_unaffected(self):
        from utils.llm.clients import _classify_provider

        for model in ('gpt-4.1-mini', 'gpt-5.4', 'gpt-5.1', 'o4-mini'):
            assert _classify_provider(model) == 'openai'

    def test_anthropic_unaffected(self):
        from utils.llm.clients import _classify_provider

        assert _classify_provider('claude-sonnet-4-6') == 'anthropic'

    def test_openrouter_unaffected(self):
        from utils.llm.clients import _classify_provider

        assert _classify_provider('google/gemini-3-flash-preview') == 'openrouter'

    def test_perplexity_unaffected(self):
        from utils.llm.clients import _classify_provider

        assert _classify_provider('sonar-pro') == 'perplexity'


class TestPrivacyProfile:
    """The 'privacy' QoS profile must map every routable feature to a regolo
    model (or to provider-only features that stay on their pinned path)."""

    def test_privacy_profile_exists(self):
        from utils.llm.clients import MODEL_QOS_PROFILES

        assert 'privacy' in MODEL_QOS_PROFILES, 'privacy profile not registered'

    def test_privacy_profile_has_all_premium_features(self):
        """Every feature present in the premium profile should be covered in
        privacy, so MODEL_QOS=privacy doesn't fall back to 'gpt-4.1-mini'."""
        from utils.llm.clients import MODEL_QOS_PROFILES

        premium_features = set(MODEL_QOS_PROFILES['premium'].keys())
        privacy_features = set(MODEL_QOS_PROFILES['privacy'].keys())
        missing = premium_features - privacy_features
        assert not missing, f'privacy profile missing features: {sorted(missing)}'

    def test_privacy_chat_routes_through_regolo(self):
        """chat_responses in the privacy profile must pick a regolo model."""
        from utils.llm.clients import MODEL_QOS_PROFILES, _classify_provider

        model = MODEL_QOS_PROFILES['privacy']['chat_responses']
        assert _classify_provider(model) == 'regolo', (
            f"chat_responses picked {model!r} which is not regolo-classified"
        )

    def test_privacy_synthesis_routes_through_regolo(self):
        """Structured extraction features must use the tool-capable Llama model."""
        from utils.llm.clients import MODEL_QOS_PROFILES

        for feature in ('conv_action_items', 'memories', 'knowledge_graph'):
            model = MODEL_QOS_PROFILES['privacy'][feature]
            assert 'llama' in model.lower() or 'minimax' in model.lower(), (
                f"{feature} should pick a regolo tool/synthesis model, got {model!r}"
            )

    def test_privacy_keeps_anthropic_for_chat_agent(self):
        """chat_agent has no OSS equivalent good enough — keep it on Claude
        even in privacy profile. The _ANTHROPIC_ONLY_FEATURES gate in get_llm()
        enforces this routing regardless of profile."""
        from utils.llm.clients import MODEL_QOS_PROFILES

        assert MODEL_QOS_PROFILES['privacy']['chat_agent'].startswith('claude')

    def test_privacy_keeps_perplexity_for_web_search(self):
        """Regolo has no web-search equivalent — web_search must stay on sonar."""
        from utils.llm.clients import MODEL_QOS_PROFILES

        assert MODEL_QOS_PROFILES['privacy']['web_search'].startswith('sonar')


class TestPrivacyModeDispatch:
    """The per-request X-Privacy-Mode header must override the active QoS
    profile and route through the 'privacy' profile entries."""

    def test_privacy_mode_off_uses_active_profile(self):
        """Without the privacy flag set, get_model() returns the active
        profile's entry — the existing behavior."""
        from utils.byok import set_privacy_mode
        from utils.llm.clients import get_model

        def _run():
            set_privacy_mode(False)
            model = get_model('chat_responses')
            assert 'gpt' in model.lower(), f'expected OpenAI model, got {model!r}'

        copy_context().run(_run)

    def test_privacy_mode_on_uses_privacy_profile(self):
        """With the privacy flag set, get_model() returns the privacy
        profile's entry — a regolo-hosted OSS model."""
        from utils.byok import set_privacy_mode
        from utils.llm.clients import _classify_provider, get_model

        def _run():
            set_privacy_mode(True)
            model = get_model('chat_responses')
            assert _classify_provider(model) == 'regolo', (
                f'chat_responses with privacy mode on should route to regolo; got {model!r}'
            )

        copy_context().run(_run)

    def test_privacy_mode_respects_env_override(self):
        """Per-feature env overrides (MODEL_QOS_<FEATURE>) beat the privacy
        profile — operators still need manual escape hatches."""
        import os

        from utils.byok import set_privacy_mode
        from utils.llm.clients import get_model

        def _run():
            os.environ['MODEL_QOS_CHAT_RESPONSES'] = 'gpt-4.1-mini'
            try:
                set_privacy_mode(True)
                assert get_model('chat_responses') == 'gpt-4.1-mini'
            finally:
                os.environ.pop('MODEL_QOS_CHAT_RESPONSES', None)

        copy_context().run(_run)

    def test_privacy_mode_header_truthy_parsing(self):
        """A range of truthy spellings should all enable privacy mode;
        falsy/absent values leave it off."""
        from utils.byok import _parse_privacy_mode

        for val in ('1', 'on', 'true', 'True', 'YES', 'enabled', 'Enabled'):
            assert _parse_privacy_mode(val) is True, f'expected True for {val!r}'

        for val in (None, '', '0', 'off', 'false', 'no', 'anything_else'):
            assert _parse_privacy_mode(val) is False, f'expected False for {val!r}'


class TestPrivacyFallbackSignalling:
    """Fallback-reason contextvar + mark_privacy_fallback validator."""

    def test_default_fallback_is_none(self):
        from utils.byok import get_privacy_fallback_reason

        def _run():
            assert get_privacy_fallback_reason() is None

        copy_context().run(_run)

    def test_mark_and_read_valid_reason(self):
        from utils.byok import (
            PRIVACY_FALLBACK_VISION_UNSUPPORTED,
            get_privacy_fallback_reason,
            mark_privacy_fallback,
        )

        def _run():
            mark_privacy_fallback(PRIVACY_FALLBACK_VISION_UNSUPPORTED)
            assert get_privacy_fallback_reason() == PRIVACY_FALLBACK_VISION_UNSUPPORTED

        copy_context().run(_run)

    def test_unknown_reason_is_rejected(self):
        """Prevent banner-noise: unknown reasons don't make it into the header."""
        from utils.byok import get_privacy_fallback_reason, mark_privacy_fallback

        def _run():
            mark_privacy_fallback('definitely_not_a_valid_reason')
            assert get_privacy_fallback_reason() is None, (
                'mark_privacy_fallback should silently drop unknown reasons'
            )

        copy_context().run(_run)

    def test_all_constant_reasons_are_valid(self):
        """Every PRIVACY_FALLBACK_* constant must be in the accepted set —
        otherwise downstream calls using the constants would be rejected."""
        from utils.byok import (
            PRIVACY_FALLBACK_NO_KEY,
            PRIVACY_FALLBACK_REGOLO_OUTAGE,
            PRIVACY_FALLBACK_REGOLO_RATE_LIMITED,
            PRIVACY_FALLBACK_VISION_UNSUPPORTED,
            _PRIVACY_FALLBACK_REASONS,
        )

        for reason in (
            PRIVACY_FALLBACK_VISION_UNSUPPORTED,
            PRIVACY_FALLBACK_REGOLO_OUTAGE,
            PRIVACY_FALLBACK_REGOLO_RATE_LIMITED,
            PRIVACY_FALLBACK_NO_KEY,
        ):
            assert reason in _PRIVACY_FALLBACK_REASONS


class TestRegoloByokHeader:
    """The backend BYOK_HEADERS map must expose the regolo header name so the
    middleware routes X-BYOK-Regolo into the contextvar."""

    def test_regolo_header_registered(self):
        from utils.byok import BYOK_HEADERS

        assert BYOK_HEADERS.get('regolo') == 'x-byok-regolo'

    def test_all_header_names_are_lowercase(self):
        """FastAPI lowercases header names; ensure the map reflects that so
        lookups succeed."""
        from utils.byok import BYOK_HEADERS

        for provider, header in BYOK_HEADERS.items():
            assert header == header.lower(), f'{provider} header is not lowercase: {header!r}'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
