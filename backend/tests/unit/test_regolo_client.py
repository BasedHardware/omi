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
