"""Behavioral tests for the Regolo provider wiring and EU Privacy Mode dispatcher.

These tests use light mocking (no live API calls). The goal is to exercise
the decision points that broke or surprised reviewers:
- classifier ordering (regolo/ vs OpenRouter /)
- BYOK fallback resolution
- thinking-knob injection on the right models only
- reasoning_content stripping
- error taxonomy classification
- EU Privacy Mode hard-block vs route-to-regolo vs primary
- SSRF defense (base URL is constant)

All tests can run without ENCRYPTION_SECRET — they only touch the LLM
clients module, error helpers, and the dispatcher; nothing reaches the DB
or encryption layer.
"""

from __future__ import annotations

import os
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure tests/unit can import backend modules — mirrors other tests in this dir.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Pre-mock heavy deps BEFORE importing modules under test, per
# backend/CLAUDE.md ("Pre-mock heavy deps before importing the module under
# test"). Without this, importing utils.llm.clients will trigger real
# `anthropic.AsyncAnthropic()` and Firestore client construction that need
# live credentials.
os.environ.setdefault('ENCRYPTION_SECRET', 'test_secret_for_unit_tests_only')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake')
os.environ.setdefault('OPENROUTER_API_KEY', 'or-test-fake')
os.environ.setdefault('GEMINI_API_KEY', 'gem-test-fake')
os.environ.setdefault('REGOLO_API_KEY', 'reg-test-fake')
sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.redis_db', MagicMock())
# database.users transitively pulls in stripe (via utils.subscription) which is
# a heavy SaaS dep we don't need for these tests. Stub it with a MagicMock so
# eu_privacy.py's `import database.users as users_db` returns a stub that the
# test's @patch can target.
sys.modules.setdefault('utils.subscription', MagicMock())
sys.modules.setdefault('database.users', MagicMock())


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestClassifyProvider:
    def test_regolo_prefix_routes_to_regolo(self):
        from utils.llm.clients import _classify_provider

        assert _classify_provider('regolo/Llama-3.3-70B-Instruct') == 'regolo'
        assert _classify_provider('regolo/minimax-m2.5') == 'regolo'
        assert _classify_provider('regolo/Qwen3-Embedding-8B') == 'regolo'

    def test_openrouter_models_still_route_to_openrouter(self):
        """The regolo/ check must come BEFORE the generic / check."""
        from utils.llm.clients import _classify_provider

        assert _classify_provider('google/gemini-3-flash-preview') == 'openrouter'
        assert _classify_provider('anthropic/claude-3.5-sonnet') == 'openrouter'

    def test_anthropic_perplexity_openai_unchanged(self):
        from utils.llm.clients import _classify_provider

        assert _classify_provider('claude-sonnet-4-6') == 'anthropic'
        assert _classify_provider('sonar-pro') == 'perplexity'
        assert _classify_provider('gpt-4.1-mini') == 'openai'


# ---------------------------------------------------------------------------
# Regolo factory + thinking-knob + SSRF defense
# ---------------------------------------------------------------------------


class TestRegoloFactory:
    def test_base_url_is_constant(self):
        """SSRF defense — base URL must NEVER be derived from input."""
        from utils.llm.clients import _REGOLO_BASE_URL

        assert _REGOLO_BASE_URL == 'https://api.regolo.ai/v1'
        assert _REGOLO_BASE_URL.startswith('https://')

    def test_thinking_models_set(self):
        from utils.llm.clients import _REGOLO_THINKING_MODELS

        # Live-probed Apr 2026: every qwen-3.x family member + minimax-m2.5
        # needs enable_thinking=False or burns the output budget on hidden
        # reasoning tokens.
        assert 'minimax-m2.5' in _REGOLO_THINKING_MODELS
        assert 'qwen3.5-122b' in _REGOLO_THINKING_MODELS
        assert 'qwen3.5-9b' in _REGOLO_THINKING_MODELS
        assert 'qwen3.6-27b' in _REGOLO_THINKING_MODELS
        # Negatives — Llama, mistral, gpt-oss, gemma, apertus, qwen3-coder-next
        # all return clean output without the knob.
        for non_thinking in [
            'Llama-3.3-70B-Instruct',
            'Llama-3.1-8B-Instruct',
            'mistral-small-4-119b',
            'mistral-small3.2',
            'gpt-oss-120b',
            'gpt-oss-20b',
            'gemma4-31b',
            'apertus-70b',
            'qwen3-coder-next',
        ]:
            assert non_thinking not in _REGOLO_THINKING_MODELS

    def test_factory_strips_regolo_prefix_from_api_model(self):
        """The model name sent to api.regolo.ai must NOT include 'regolo/'."""
        from utils.llm import clients

        # Patch ChatOpenAI ctor to capture kwargs
        captured: dict[str, Any] = {}

        class _FakeChatOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch.object(clients, 'ChatOpenAI', _FakeChatOpenAI):
            # Bypass cache for this test — clear before invoking
            clients._llm_cache.clear()
            clients._get_or_create_regolo_llm('regolo/Llama-3.3-70B-Instruct', streaming=False)

        assert captured.get('model') == 'Llama-3.3-70B-Instruct'
        assert captured.get('base_url') == 'https://api.regolo.ai/v1'
        # Llama is NOT a thinking model — extra_body must be absent.
        assert 'extra_body' not in captured

    def test_thinking_knob_injected_for_minimax(self):
        from utils.llm import clients

        captured: dict[str, Any] = {}

        class _FakeChatOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch.object(clients, 'ChatOpenAI', _FakeChatOpenAI):
            clients._llm_cache.clear()
            clients._get_or_create_regolo_llm('regolo/minimax-m2.5', streaming=False)

        extra = captured.get('extra_body')
        assert extra == {'chat_template_kwargs': {'enable_thinking': False}}, extra

    def test_thinking_knob_injected_for_qwen3_5_122b(self):
        from utils.llm import clients

        captured: dict[str, Any] = {}

        class _FakeChatOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch.object(clients, 'ChatOpenAI', _FakeChatOpenAI):
            clients._llm_cache.clear()
            clients._get_or_create_regolo_llm('regolo/qwen3.5-122b', streaming=False)

        assert captured['extra_body']['chat_template_kwargs']['enable_thinking'] is False

    def test_thinking_knob_injected_for_qwen3_5_9b_and_qwen3_6_27b(self):
        """qwen3.5-9b and qwen3.6-27b are also thinking models — live probe
        without the knob hits max_tokens with no parseable output."""
        from utils.llm import clients

        for model in ['regolo/qwen3.5-9b', 'regolo/qwen3.6-27b']:
            captured: dict[str, Any] = {}

            class _FakeChatOpenAI:
                def __init__(self, **kwargs):
                    captured.update(kwargs)

            with patch.object(clients, 'ChatOpenAI', _FakeChatOpenAI):
                clients._llm_cache.clear()
                clients._get_or_create_regolo_llm(model, streaming=False)

            assert (
                captured.get('extra_body', {}).get('chat_template_kwargs', {}).get('enable_thinking') is False
            ), f'thinking knob missing for {model}'


# ---------------------------------------------------------------------------
# reasoning_content stripper
# ---------------------------------------------------------------------------


class TestStripReasoningContent:
    def test_strips_from_basemessage_additional_kwargs(self):
        from utils.llm.clients import strip_reasoning_content

        msg = MagicMock()
        msg.additional_kwargs = {
            'reasoning_content': 'thinking out loud...',
            'tool_calls': [{'id': 'tc_1'}],
        }
        strip_reasoning_content(msg)
        assert 'reasoning_content' not in msg.additional_kwargs
        assert 'tool_calls' in msg.additional_kwargs  # untouched

    def test_strips_from_top_level_dict(self):
        from utils.llm.clients import strip_reasoning_content

        chunk = {'reasoning_content': 'inner monologue', 'content': 'visible'}
        strip_reasoning_content(chunk)
        assert 'reasoning_content' not in chunk
        assert chunk['content'] == 'visible'

    def test_strips_from_streaming_delta_nested(self):
        from utils.llm.clients import strip_reasoning_content

        chunk = {'delta': {'reasoning_content': 'hidden', 'content': 'shown'}}
        strip_reasoning_content(chunk)
        assert 'reasoning_content' not in chunk['delta']
        assert chunk['delta']['content'] == 'shown'

    def test_none_is_safe(self):
        from utils.llm.clients import strip_reasoning_content

        # Should not raise
        assert strip_reasoning_content(None) is None


# ---------------------------------------------------------------------------
# _RegoloChatProxy.invoke — sync hand-off (M1.1)
#
# These tests exist because the proxy used to be a transparent forwarder via
# __getattr__, so reasoning_content leaked and raw httpx errors bubbled up
# unclassified. The wrapped invoke is the M1.1 patch that fixed that.
# ---------------------------------------------------------------------------


class TestRegoloProxyInvoke:
    def _make_proxy(self, fake_chat_openai: Any):
        """Build a proxy whose _resolve() returns the given fake."""
        from utils.llm.clients import _RegoloChatProxy

        # Pass the fake as `default`; with no BYOK key set, _resolve() returns it.
        return _RegoloChatProxy(model='Llama-3.3-70B-Instruct', default=fake_chat_openai, ctor_kwargs={})

    def test_invoke_strips_reasoning_content_on_success(self):
        msg = MagicMock()
        msg.additional_kwargs = {'reasoning_content': 'thinking out loud...', 'tool_calls': []}

        fake = MagicMock()
        fake.invoke.return_value = msg

        proxy = self._make_proxy(fake)
        result = proxy.invoke('hello')

        assert result is msg
        assert 'reasoning_content' not in msg.additional_kwargs
        assert 'tool_calls' in msg.additional_kwargs  # untouched

    def test_invoke_classifies_401_as_auth_error(self):
        from utils.llm.regolo_errors import RegoloAuthError

        exc = Exception('unauthorized')
        exc.status_code = 401  # type: ignore[attr-defined]

        fake = MagicMock()
        fake.invoke.side_effect = exc

        proxy = self._make_proxy(fake)
        with pytest.raises(RegoloAuthError):
            proxy.invoke('hello')

    def test_invoke_classifies_429_with_retry_after(self):
        from utils.llm.regolo_errors import RegoloRateLimitError

        exc = MagicMock(spec=Exception)
        exc.status_code = 429
        exc.response = MagicMock()
        exc.response.headers = {'Retry-After': '15'}

        fake = MagicMock()
        fake.invoke.side_effect = exc

        proxy = self._make_proxy(fake)
        with pytest.raises(RegoloRateLimitError) as info:
            proxy.invoke('hello')

        assert info.value.retry_after_s == 15.0

    def test_invoke_classifies_5xx_as_service_error(self):
        from utils.llm.regolo_errors import RegoloServiceError

        exc = Exception('upstream broke')
        exc.status_code = 503  # type: ignore[attr-defined]

        fake = MagicMock()
        fake.invoke.side_effect = exc

        proxy = self._make_proxy(fake)
        with pytest.raises(RegoloServiceError):
            proxy.invoke('hello')


# ---------------------------------------------------------------------------
# _RegoloChatProxy async + streaming hand-off (M1.2)
#
# Async tests use `asyncio.run` to drive coroutines synchronously — same
# pattern as test_byok_security.py:1025+. No pytest-asyncio dependency.
# ---------------------------------------------------------------------------


class TestRegoloProxyAsyncAndStreaming:
    def _make_proxy(self, fake_chat_openai: Any):
        from utils.llm.clients import _RegoloChatProxy

        return _RegoloChatProxy(model='Llama-3.3-70B-Instruct', default=fake_chat_openai, ctor_kwargs={})

    def test_ainvoke_strips_reasoning_content_on_success(self):
        import asyncio

        msg = MagicMock()
        msg.additional_kwargs = {'reasoning_content': 'inner', 'tool_calls': []}

        async def _ainvoke(*a: Any, **kw: Any):
            return msg

        fake = MagicMock()
        fake.ainvoke = _ainvoke

        proxy = self._make_proxy(fake)
        result = asyncio.run(proxy.ainvoke('hi'))

        assert result is msg
        assert 'reasoning_content' not in msg.additional_kwargs

    def test_ainvoke_classifies_429_with_retry_after(self):
        import asyncio
        from utils.llm.regolo_errors import RegoloRateLimitError

        exc = MagicMock(spec=Exception)
        exc.status_code = 429
        exc.response = MagicMock()
        exc.response.headers = {'Retry-After': '7'}

        async def _ainvoke(*a: Any, **kw: Any):
            raise exc

        fake = MagicMock()
        fake.ainvoke = _ainvoke

        proxy = self._make_proxy(fake)
        with pytest.raises(RegoloRateLimitError) as info:
            asyncio.run(proxy.ainvoke('hi'))
        assert info.value.retry_after_s == 7.0

    def test_astream_strips_reasoning_content_per_chunk(self):
        import asyncio

        chunks = [
            {'delta': {'reasoning_content': 'thought-1', 'content': 'a'}},
            {'delta': {'reasoning_content': 'thought-2', 'content': 'b'}},
            {'delta': {'content': 'c'}},
        ]

        async def _agen(*a: Any, **kw: Any):
            for c in chunks:
                yield c

        fake = MagicMock()
        fake.astream = _agen

        proxy = self._make_proxy(fake)

        async def _drain():
            return [c async for c in proxy.astream('hi')]

        out = asyncio.run(_drain())
        assert len(out) == 3
        # All reasoning_content removed, content preserved.
        for c in out:
            assert 'reasoning_content' not in c['delta']
        assert [c['delta']['content'] for c in out] == ['a', 'b', 'c']

    def test_stream_classifies_5xx_during_iteration(self):
        from utils.llm.regolo_errors import RegoloServiceError

        exc = Exception('mid-stream boom')
        exc.status_code = 502  # type: ignore[attr-defined]

        def _sgen(*a: Any, **kw: Any):
            yield {'delta': {'content': 'first'}}
            raise exc

        fake = MagicMock()
        fake.stream = _sgen

        proxy = self._make_proxy(fake)
        consumed: list[Any] = []
        with pytest.raises(RegoloServiceError):
            for chunk in proxy.stream('hi'):
                consumed.append(chunk)

        # First chunk delivered before the failure.
        assert len(consumed) == 1
        assert consumed[0]['delta']['content'] == 'first'


# ---------------------------------------------------------------------------
# _RegoloChatProxy retry policy (M1.3)
#
# Retry budget: 3 attempts total on 429 (initial + 2), 1 retry on 5xx, 0 on
# auth/forbidden/not-found. Honors Retry-After when present. Tests patch
# time.sleep / asyncio.sleep so they don't actually wait.
# ---------------------------------------------------------------------------


class TestRegoloProxyRetryPolicy:
    def _make_proxy(self, fake_chat_openai: Any):
        from utils.llm.clients import _RegoloChatProxy

        return _RegoloChatProxy(model='Llama-3.3-70B-Instruct', default=fake_chat_openai, ctor_kwargs={})

    def _build_429(self, retry_after: str = '0') -> Exception:
        exc = MagicMock(spec=Exception)
        exc.status_code = 429
        exc.response = MagicMock()
        exc.response.headers = {'Retry-After': retry_after}
        return exc

    def _build_5xx(self, status: int = 503) -> Exception:
        exc = Exception(f'upstream {status}')
        exc.status_code = status  # type: ignore[attr-defined]
        return exc

    def test_invoke_retries_429_with_retry_after(self):
        """Two 429s with Retry-After=0 then success — total 3 attempts, both
        retries honor Retry-After (0s) instead of using the default backoff."""
        success_msg = MagicMock()
        success_msg.additional_kwargs = {'tool_calls': []}

        side_effects = [self._build_429('0'), self._build_429('0'), success_msg]
        fake = MagicMock()
        fake.invoke.side_effect = side_effects

        proxy = self._make_proxy(fake)
        sleeps: list[float] = []
        with patch('utils.llm.clients.time.sleep', side_effect=sleeps.append):
            result = proxy.invoke('hi')

        assert result is success_msg
        assert fake.invoke.call_count == 3
        assert sleeps == [0.0, 0.0]  # Retry-After=0 honored both times

    def test_invoke_max_3_attempts_on_persistent_429(self):
        from utils.llm.regolo_errors import RegoloRateLimitError

        fake = MagicMock()
        fake.invoke.side_effect = [self._build_429('0'), self._build_429('0'), self._build_429('0')]

        proxy = self._make_proxy(fake)
        with patch('utils.llm.clients.time.sleep'):
            with pytest.raises(RegoloRateLimitError):
                proxy.invoke('hi')

        # 3 total attempts: initial + 2 retries.
        assert fake.invoke.call_count == 3

    def test_invoke_retries_5xx_once_then_raises(self):
        from utils.llm.regolo_errors import RegoloServiceError

        fake = MagicMock()
        fake.invoke.side_effect = [self._build_5xx(503), self._build_5xx(503)]

        proxy = self._make_proxy(fake)
        with patch('utils.llm.clients.time.sleep') as mock_sleep:
            with pytest.raises(RegoloServiceError):
                proxy.invoke('hi')

        # 2 total attempts: initial + 1 retry, then re-raise.
        assert fake.invoke.call_count == 2
        # One sleep between the two attempts.
        assert mock_sleep.call_count == 1

    def test_invoke_does_not_retry_401(self):
        from utils.llm.regolo_errors import RegoloAuthError

        exc = Exception('unauthorized')
        exc.status_code = 401  # type: ignore[attr-defined]
        fake = MagicMock()
        fake.invoke.side_effect = exc

        proxy = self._make_proxy(fake)
        with patch('utils.llm.clients.time.sleep') as mock_sleep:
            with pytest.raises(RegoloAuthError):
                proxy.invoke('hi')

        assert fake.invoke.call_count == 1
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# _RegoloChatProxy telemetry tagging (M1.4)
#
# The proxy injects `provider=regolo` + `model=<name>` into the langchain
# RunnableConfig (both `tags` and `metadata` channels) so the upstream
# `_usage_callback` can attribute usage rows to Regolo. User-supplied tags
# / metadata must be preserved.
# ---------------------------------------------------------------------------


class TestRegoloProxyTelemetryTags:
    def _make_proxy(self, fake_chat_openai: Any, model: str = 'mistral-small-4-119b'):
        from utils.llm.clients import _RegoloChatProxy

        return _RegoloChatProxy(model=model, default=fake_chat_openai, ctor_kwargs={})

    def test_invoke_injects_provider_tag_when_no_user_config(self):
        success_msg = MagicMock()
        success_msg.additional_kwargs = {}
        fake = MagicMock()
        fake.invoke.return_value = success_msg

        proxy = self._make_proxy(fake, model='Llama-3.3-70B-Instruct')
        proxy.invoke('hi')

        # Inspect the config the proxy passed to the underlying ChatOpenAI.
        call_kwargs = fake.invoke.call_args.kwargs
        config = call_kwargs.get('config')
        assert config is not None
        assert 'provider=regolo' in config['tags']
        assert 'model=Llama-3.3-70B-Instruct' in config['tags']
        assert config['metadata']['provider'] == 'regolo'
        assert config['metadata']['regolo_model'] == 'Llama-3.3-70B-Instruct'

    def test_invoke_merges_user_supplied_config(self):
        """User-supplied tags + metadata are preserved; Regolo attribution
        always lands on `metadata['regolo_provider']` + `regolo_model` so a
        caller cannot accidentally hide the Regolo attribution by pre-setting
        their own `metadata['provider']`."""
        success_msg = MagicMock()
        success_msg.additional_kwargs = {}
        fake = MagicMock()
        fake.invoke.return_value = success_msg

        proxy = self._make_proxy(fake, model='mistral-small-4-119b')
        user_config = {
            'tags': ['user-trace-id-abc', 'feature=chat'],
            'metadata': {'session_id': 'sess-42', 'provider': 'caller-app'},
        }
        proxy.invoke('hi', config=user_config)

        config = fake.invoke.call_args.kwargs['config']
        # User tags preserved
        assert 'user-trace-id-abc' in config['tags']
        assert 'feature=chat' in config['tags']
        # Regolo tags appended
        assert 'provider=regolo' in config['tags']
        assert 'model=mistral-small-4-119b' in config['tags']
        # User metadata preserved
        assert config['metadata']['session_id'] == 'sess-42'
        # User-supplied 'provider' kept (setdefault); attribution still works
        # via the M1-private `regolo_provider` key + the tag channel.
        assert config['metadata']['provider'] == 'caller-app'
        assert config['metadata']['regolo_provider'] == 'regolo'
        assert config['metadata']['regolo_model'] == 'mistral-small-4-119b'

    def test_invoke_does_not_double_stamp_model_tag(self):
        """If the caller already supplied a `model=` tag (e.g. routing layer),
        the proxy must not append a second one. Regression for an issue caught
        in M1 review where the guard only checked `provider=regolo`."""
        success_msg = MagicMock()
        success_msg.additional_kwargs = {}
        fake = MagicMock()
        fake.invoke.return_value = success_msg

        proxy = self._make_proxy(fake, model='Llama-3.3-70B-Instruct')
        user_config = {'tags': ['model=user-supplied-name']}
        proxy.invoke('hi', config=user_config)

        tags = fake.invoke.call_args.kwargs['config']['tags']
        model_tags = [t for t in tags if t.startswith('model=')]
        assert model_tags == ['model=user-supplied-name'], model_tags
        # provider=regolo still appended (idempotency only blocks duplicates).
        assert 'provider=regolo' in tags

    def test_invoke_idempotent_on_double_call(self):
        """Calling the helper twice (e.g. proxy nested inside another proxy)
        must not duplicate the provider tag."""
        from utils.llm.clients import _inject_regolo_telemetry

        args, kwargs = _inject_regolo_telemetry('Llama-3.3-70B-Instruct', ('input',), {})
        args, kwargs = _inject_regolo_telemetry('Llama-3.3-70B-Instruct', args, kwargs)

        tags = kwargs['config']['tags']
        assert tags.count('provider=regolo') == 1
        assert sum(1 for t in tags if t.startswith('model=')) == 1


# ---------------------------------------------------------------------------
# Regolo error taxonomy
# ---------------------------------------------------------------------------


class TestRegoloErrors:
    def test_401_maps_to_auth_error(self):
        from utils.llm.regolo_errors import RegoloAuthError, classify_regolo_error

        exc = MagicMock()
        exc.status_code = 401
        result = classify_regolo_error(exc)
        assert isinstance(result, RegoloAuthError)
        assert result.fallback_eligible is False

    def test_403_maps_to_forbidden(self):
        from utils.llm.regolo_errors import RegoloForbiddenError, classify_regolo_error

        exc = MagicMock()
        exc.status_code = 403
        assert isinstance(classify_regolo_error(exc), RegoloForbiddenError)

    def test_429_extracts_retry_after(self):
        from utils.llm.regolo_errors import RegoloRateLimitError, classify_regolo_error

        exc = MagicMock()
        exc.status_code = 429
        exc.response = MagicMock()
        exc.response.headers = {'Retry-After': '12'}
        result = classify_regolo_error(exc)
        assert isinstance(result, RegoloRateLimitError)
        assert result.retry_after_s == 12.0
        assert result.fallback_eligible is True

    def test_5xx_is_fallback_eligible(self):
        from utils.llm.regolo_errors import RegoloServiceError, classify_regolo_error

        exc = MagicMock()
        exc.status_code = 503
        result = classify_regolo_error(exc)
        assert isinstance(result, RegoloServiceError)
        assert result.fallback_eligible is True

    def test_unknown_status_treated_as_service_error(self):
        from utils.llm.regolo_errors import RegoloServiceError, classify_regolo_error

        exc = MagicMock()
        exc.status_code = None
        exc.response = None
        result = classify_regolo_error(exc)
        # Default fallback so transient/unknown stays retryable.
        assert isinstance(result, RegoloServiceError)


# ---------------------------------------------------------------------------
# Regolo embedding proxy + EU index provisioning gate (M2.5)
# ---------------------------------------------------------------------------


class TestRegoloEmbeddingProxy:
    def test_factory_constructs_with_regolo_base_url(self):
        """The default embeddings client must point at api.regolo.ai/v1, not OpenAI."""
        from utils.llm import clients

        captured: dict[str, Any] = {}

        class _FakeEmbeddings:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch.object(clients, 'OpenAIEmbeddings', _FakeEmbeddings):
            proxy = clients._RegoloEmbeddingProxy(
                model='Qwen3-Embedding-8B',
                default=_FakeEmbeddings(
                    model='Qwen3-Embedding-8B',
                    base_url='https://api.regolo.ai/v1',
                ),
                ctor_kwargs={},
            )
            # Force re-resolve via BYOK path so we can assert the kwargs.
            with patch.object(clients, 'get_byok_key', return_value='byok-test'):
                clients._openai_cache.clear()
                proxy._resolve()

        assert captured.get('model') == 'Qwen3-Embedding-8B'
        assert captured.get('base_url') == 'https://api.regolo.ai/v1'
        assert captured.get('api_key') == 'byok-test'

    def test_module_level_regolo_embeddings_uses_4096_model(self):
        from utils.llm.clients import (
            _REGOLO_EMBEDDING_DIM,
            _REGOLO_EMBEDDING_MODEL,
            regolo_embeddings,
        )

        assert _REGOLO_EMBEDDING_MODEL == 'Qwen3-Embedding-8B'
        assert _REGOLO_EMBEDDING_DIM == 4096
        # Object slot equals the model name
        assert regolo_embeddings._model == 'Qwen3-Embedding-8B'

    def test_resolver_falls_back_to_default_when_no_byok(self):
        from utils.llm import clients

        sentinel = object()
        proxy = clients._RegoloEmbeddingProxy(
            model='Qwen3-Embedding-8B',
            default=sentinel,  # type: ignore[arg-type]
            ctor_kwargs={},
        )
        with patch.object(clients, 'get_byok_key', return_value=None):
            assert proxy._resolve() is sentinel


class TestEuEmbeddingIndexGate:
    def setup_method(self):
        self._original = os.environ.get('PINECONE_INDEX_NAME_EU')
        os.environ.pop('PINECONE_INDEX_NAME_EU', None)

    def teardown_method(self):
        if self._original is None:
            os.environ.pop('PINECONE_INDEX_NAME_EU', None)
        else:
            os.environ['PINECONE_INDEX_NAME_EU'] = self._original

    def test_unset_returns_false(self):
        from utils.llm.eu_privacy import eu_embedding_index_provisioned

        assert eu_embedding_index_provisioned() is False

    def test_empty_returns_false(self):
        from utils.llm.eu_privacy import eu_embedding_index_provisioned

        os.environ['PINECONE_INDEX_NAME_EU'] = '   '
        assert eu_embedding_index_provisioned() is False

    def test_non_empty_returns_true(self):
        from utils.llm.eu_privacy import eu_embedding_index_provisioned

        os.environ['PINECONE_INDEX_NAME_EU'] = 'omi-eu-prod-4096'
        assert eu_embedding_index_provisioned() is True

    def test_memory_search_hard_blocks_when_index_unset(self):
        """EMBEDDING_DEPENDENT_FEATURES stay HARD_BLOCKED until the EU index is provisioned."""
        from utils.llm.eu_privacy import (
            FeatureRouteKind,
            resolve_feature_model,
            set_eu_privacy_for_request,
        )

        set_eu_privacy_for_request(True)
        with patch('database.users.is_eu_privacy_mode_enabled', return_value=True):
            route = resolve_feature_model('user-x', 'memory_search')

        assert route.kind is FeatureRouteKind.HARD_BLOCK
        assert route.banner is not None

    def test_memory_search_routes_to_regolo_when_index_set(self):
        from utils.llm.eu_privacy import (
            FeatureRouteKind,
            resolve_feature_model,
            set_eu_privacy_for_request,
        )

        os.environ['PINECONE_INDEX_NAME_EU'] = 'omi-eu-prod-4096'
        set_eu_privacy_for_request(True)
        with patch('database.users.is_eu_privacy_mode_enabled', return_value=True):
            route = resolve_feature_model('user-x', 'memory_search')

        assert route.kind is FeatureRouteKind.REGOLO
        assert route.model == 'regolo/Qwen3-Embedding-8B'


# ---------------------------------------------------------------------------
# EU Privacy Mode dispatcher
# ---------------------------------------------------------------------------


class TestEUPrivacyDispatcher:
    def setup_method(self):
        # Reset request-scoped contextvar between tests
        from utils.llm import eu_privacy

        eu_privacy._eu_privacy_ctx.set(None)

    def test_eu_off_returns_primary_route(self):
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(False)
        with patch('utils.llm.eu_privacy.get_model', return_value='gpt-4.1-mini'):
            route = resolve_feature_model('uid-1', 'chat_responses')
        assert route.kind is FeatureRouteKind.PRIMARY
        assert route.model == 'gpt-4.1-mini'
        assert route.banner is None

    def test_eu_on_supported_feature_routes_to_regolo(self):
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(True)
        route = resolve_feature_model('uid-1', 'chat_responses')
        assert route.kind is FeatureRouteKind.REGOLO
        assert route.model and route.model.startswith('regolo/')

    def test_eu_on_embedding_feature_hard_blocks(self):
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(True)
        route = resolve_feature_model('uid-1', 'memory_search')
        assert route.kind is FeatureRouteKind.HARD_BLOCK
        assert route.model is None
        assert route.banner is not None
        # Banner must mention EU Privacy Mode so user knows why
        assert 'EU Privacy Mode' in route.banner

    def test_knowledge_graph_extraction_routes_to_regolo_search_blocks(self):
        """Subtle distinction: `knowledge_graph` is LLM extraction (supported)
        vs `knowledge_graph_search` which is vector lookup (hard-blocked).
        Easy to conflate; this test prevents regressions."""
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(True)
        # Extraction (LLM) — supported
        route = resolve_feature_model('uid-1', 'knowledge_graph')
        assert route.kind is FeatureRouteKind.REGOLO
        # Search (embedding) — hard-blocked
        eu_privacy._eu_privacy_ctx.set(True)
        route = resolve_feature_model('uid-1', 'knowledge_graph_search')
        assert route.kind is FeatureRouteKind.HARD_BLOCK

    def test_every_supported_feature_has_a_model(self):
        """Every entry in REGOLO_SUPPORTED_FEATURES must have a corresponding
        model in _EU_FEATURE_MODELS, otherwise resolve_feature_model returns
        a fallback that may not be the operator's intent."""
        from utils.llm.eu_privacy import REGOLO_SUPPORTED_FEATURES, _EU_FEATURE_MODELS

        missing = REGOLO_SUPPORTED_FEATURES - set(_EU_FEATURE_MODELS.keys())
        assert not missing, f'features without explicit model picks: {sorted(missing)}'

    def test_every_eu_model_uses_regolo_prefix(self):
        """Sanity: every value in _EU_FEATURE_MODELS must classify as 'regolo'
        per _classify_provider, otherwise the dispatcher would route to the
        wrong factory."""
        from utils.llm.clients import _classify_provider
        from utils.llm.eu_privacy import _EU_FEATURE_MODELS

        for feature, model in _EU_FEATURE_MODELS.items():
            assert _classify_provider(model) == 'regolo', f'{feature}={model} does not classify as regolo'

    def test_eu_on_vision_hard_blocks(self):
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(True)
        route = resolve_feature_model('uid-1', 'vision')
        assert route.kind is FeatureRouteKind.HARD_BLOCK

    def test_eu_on_chat_agent_hard_blocks(self):
        """chat_agent is Anthropic-only and must NOT silently fall back."""
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(True)
        route = resolve_feature_model('uid-1', 'chat_agent')
        assert route.kind is FeatureRouteKind.HARD_BLOCK

    def test_eu_on_unknown_feature_hard_blocks_by_default(self):
        """Defensive default: any feature we forgot to categorize must be blocked,
        not silently routed to a non-EU provider."""
        from utils.llm import eu_privacy
        from utils.llm.eu_privacy import FeatureRouteKind, resolve_feature_model

        eu_privacy.set_eu_privacy_for_request(True)
        route = resolve_feature_model('uid-1', 'feature_we_forgot_to_add')
        assert route.kind is FeatureRouteKind.HARD_BLOCK
        assert 'not yet certified' in (route.banner or '')

    def test_eu_flag_fails_closed_on_firestore_error(self):
        """Privacy fail-safe: if Firestore is unreachable, default to ON.
        An outage briefly blocking unsupported features is operationally
        better than briefly leaking EU user data to non-EU providers."""
        from utils.llm import eu_privacy

        eu_privacy._eu_privacy_ctx.set(None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('REGOLO_EU_FAIL_OPEN', None)
            with patch('utils.llm.eu_privacy.users_db.get_eu_privacy_mode', side_effect=RuntimeError('fs down')):
                assert eu_privacy.get_eu_privacy_for_request('uid-1') is True

    def test_eu_flag_can_fail_open_via_env_flag(self):
        """REGOLO_EU_FAIL_OPEN=1 lets operators trade strict residency for
        availability when Firestore is unreachable."""
        from utils.llm import eu_privacy

        eu_privacy._eu_privacy_ctx.set(None)
        with patch.dict(os.environ, {'REGOLO_EU_FAIL_OPEN': '1'}):
            with patch('utils.llm.eu_privacy.users_db.get_eu_privacy_mode', side_effect=RuntimeError('fs down')):
                assert eu_privacy.get_eu_privacy_for_request('uid-1') is False

    def test_clear_eu_privacy_context_resets_ctx(self):
        """Background tasks must clear inherited contextvars."""
        from utils.llm import eu_privacy

        eu_privacy.set_eu_privacy_for_request(True)
        assert eu_privacy._eu_privacy_ctx.get() is True
        eu_privacy.clear_eu_privacy_context()
        assert eu_privacy._eu_privacy_ctx.get() is None


# ---------------------------------------------------------------------------
# Streaming tool-call fixture replay
#
# Skipped until the live fixture is captured (run
# tests/fixtures/capture_regolo_tool_call_stream.sh with a real REGOLO_API_KEY).
# Phase 1 acceptance gate 9: every captured delta must be parseable by
# LangChain's native OpenAI accumulator. If this test fails after the fixture
# is committed, write a custom accumulator in _RegoloChatProxy.
# ---------------------------------------------------------------------------


_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'fixtures', 'regolo_tool_call_stream.json'
)


@pytest.mark.skipif(
    not os.path.exists(_FIXTURE_PATH),
    reason='Run capture_regolo_tool_call_stream.sh with REGOLO_API_KEY to enable.',
)
class TestRegoloStreamingToolCallReplay:
    def test_every_delta_has_expected_shape(self):
        """Each captured chunk must look like the OpenAI streaming shape so
        LangChain's native accumulator handles it. Specifically: top-level
        `choices[i].delta` with optional `content`/`tool_calls`."""
        import json

        with open(_FIXTURE_PATH) as f:
            deltas = json.load(f)
        assert deltas, 'fixture is empty'
        for d in deltas:
            choices = d.get('choices') or []
            assert isinstance(choices, list)
            for c in choices:
                # Every chunk past the prologue must carry a delta dict.
                if 'delta' in c:
                    assert isinstance(c['delta'], dict)

    def test_tool_call_arguments_concatenate_to_valid_json(self):
        """The tool_calls.function.arguments deltas must concatenate into
        valid JSON — that's what the accumulator relies on."""
        import json

        with open(_FIXTURE_PATH) as f:
            deltas = json.load(f)
        # Walk all chunks and accumulate per-tool-call argument strings.
        per_index_args: dict[int, str] = {}
        for d in deltas:
            for c in d.get('choices') or []:
                delta = c.get('delta') or {}
                for tc in delta.get('tool_calls') or []:
                    idx = tc.get('index', 0)
                    args = (tc.get('function') or {}).get('arguments', '')
                    per_index_args[idx] = per_index_args.get(idx, '') + args
        assert per_index_args, 'fixture has no tool_call deltas — recapture with a tool-eligible prompt'
        for idx, joined in per_index_args.items():
            # Must be parseable JSON — otherwise our accumulator is broken
            # OR Regolo emitted in a non-OpenAI shape that needs translation.
            json.loads(joined)
