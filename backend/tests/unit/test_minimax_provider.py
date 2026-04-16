"""Tests for MiniMax provider configuration in utils/llm/clients.py.

Verifies that:
1. MiniMax clients are conditionally created based on MINIMAX_API_KEY
2. Correct models and base URL are used (MiniMax-M2.7, MiniMax-M2.7-highspeed)
3. temperature is set to 1.0 (MiniMax requires (0.0, 1.0], not 0)
4. Persona models use MiniMax when MINIMAX_API_KEY is configured
5. Persona models fall back to OpenRouter when MINIMAX_API_KEY is not configured
"""

import importlib
import sys
import os
import types
from unittest.mock import MagicMock, patch


def _make_tiktoken_mock():
    """Create a proper module mock for tiktoken that passes __spec__ checks."""
    mod = types.ModuleType('tiktoken')
    mod.__spec__ = None  # Prevents importlib.util.find_spec() ValueError
    enc_mock = MagicMock()
    enc_mock.encode.return_value = []
    mod.encoding_for_model = lambda model: enc_mock
    mod.get_encoding = lambda name: enc_mock
    return mod


def _make_anthropic_mock():
    """Create a proper module mock for anthropic."""
    mod = types.ModuleType('anthropic')
    mod.__spec__ = None

    class AsyncAnthropic:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

    mod.AsyncAnthropic = AsyncAnthropic
    return mod


def _make_httpx_mock():
    """Create a proper module mock for httpx."""
    mod = types.ModuleType('httpx')
    mod.__spec__ = None

    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"embedding": {"values": []}}
    mod.post = MagicMock(return_value=resp)
    return mod


def _fresh_import_clients(env_overrides: dict):
    """Import utils.llm.clients with fresh environment and collect ChatOpenAI calls."""
    calls = []

    def capturing_chat_openai(**kwargs):
        calls.append(kwargs)
        return MagicMock()

    # Remove any cached version of the module under test and its dependencies
    for key in list(sys.modules.keys()):
        if key in ('utils.llm.clients', 'utils.llm.usage_tracker'):
            del sys.modules[key]

    mock_usage_tracker = types.ModuleType('utils.llm.usage_tracker')
    mock_usage_tracker.__spec__ = None
    mock_usage_tracker.get_usage_callback = MagicMock(return_value=MagicMock())

    mock_structured = types.ModuleType('models.structured')
    mock_structured.__spec__ = None
    mock_structured.Structured = MagicMock()

    mock_db_client = types.ModuleType('database._client')
    mock_db_client.__spec__ = None

    mock_langchain_openai = types.ModuleType('langchain_openai')
    mock_langchain_openai.__spec__ = None
    mock_langchain_openai.ChatOpenAI = MagicMock(side_effect=capturing_chat_openai)
    mock_langchain_openai.OpenAIEmbeddings = MagicMock(return_value=MagicMock())

    mock_lc_parsers = types.ModuleType('langchain_core.output_parsers')
    mock_lc_parsers.__spec__ = None
    mock_lc_parsers.PydanticOutputParser = MagicMock(return_value=MagicMock())

    mock_lc_core = types.ModuleType('langchain_core')
    mock_lc_core.__spec__ = None

    extra_modules = {
        'tiktoken': _make_tiktoken_mock(),
        'anthropic': _make_anthropic_mock(),
        'httpx': _make_httpx_mock(),
        'database._client': mock_db_client,
        'utils.llm.usage_tracker': mock_usage_tracker,
        'models.structured': mock_structured,
        'langchain_openai': mock_langchain_openai,
        'langchain_core': mock_lc_core,
        'langchain_core.output_parsers': mock_lc_parsers,
    }

    # Build a clean environment
    clean_env = {}
    # Only carry over keys needed for OpenAI default init (avoid side effects)
    for k in ('OPENAI_API_KEY', 'OPENROUTER_API_KEY'):
        if k in os.environ:
            clean_env[k] = os.environ[k]
    clean_env.update(env_overrides)
    # Ensure MINIMAX keys are not inherited unless explicitly provided
    if 'MINIMAX_API_KEY' not in env_overrides:
        clean_env.pop('MINIMAX_API_KEY', None)
    if 'MINIMAX_BASE_URL' not in env_overrides:
        clean_env.pop('MINIMAX_BASE_URL', None)

    with patch.dict('sys.modules', extra_modules):
        with patch.dict('os.environ', clean_env, clear=True):
            mod = importlib.import_module('utils.llm.clients')

    return mod, calls


class TestMiniMaxClientsCreated:
    """MiniMax clients are created when MINIMAX_API_KEY is set."""

    def test_llm_minimax_created(self):
        mod, _ = _fresh_import_clients({'MINIMAX_API_KEY': 'test-minimax-key'})
        assert mod.llm_minimax is not None

    def test_llm_minimax_stream_created(self):
        mod, _ = _fresh_import_clients({'MINIMAX_API_KEY': 'test-minimax-key'})
        assert mod.llm_minimax_stream is not None

    def test_llm_minimax_fast_stream_created(self):
        mod, _ = _fresh_import_clients({'MINIMAX_API_KEY': 'test-minimax-key'})
        assert mod.llm_minimax_fast_stream is not None


class TestMiniMaxClientsNoneWithoutKey:
    """MiniMax clients are None when MINIMAX_API_KEY is not set."""

    def test_llm_minimax_none_without_key(self):
        mod, _ = _fresh_import_clients({'MINIMAX_API_KEY': ''})
        assert mod.llm_minimax is None

    def test_llm_minimax_stream_none_without_key(self):
        mod, _ = _fresh_import_clients({'MINIMAX_API_KEY': ''})
        assert mod.llm_minimax_stream is None

    def test_llm_minimax_fast_stream_none_without_key(self):
        mod, _ = _fresh_import_clients({'MINIMAX_API_KEY': ''})
        assert mod.llm_minimax_fast_stream is None


class TestMiniMaxClientConfiguration:
    """MiniMax clients use correct models and base URL."""

    def test_minimax_uses_default_base_url(self):
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        minimax_calls = [c for c in calls if c.get('model') in ('MiniMax-M2.7', 'MiniMax-M2.7-highspeed')]
        assert len(minimax_calls) > 0
        for call in minimax_calls:
            assert 'minimax.io/v1' in call.get(
                'base_url', ''
            ), f"base_url {call.get('base_url')!r} should contain minimax.io/v1"

    def test_minimax_uses_custom_base_url(self):
        _, calls = _fresh_import_clients(
            {'MINIMAX_API_KEY': 'test-key', 'MINIMAX_BASE_URL': 'https://custom.minimax.io/v1'}
        )
        minimax_calls = [c for c in calls if c.get('model') in ('MiniMax-M2.7', 'MiniMax-M2.7-highspeed')]
        assert len(minimax_calls) > 0
        for call in minimax_calls:
            assert call.get('base_url') == 'https://custom.minimax.io/v1'

    def test_minimax_temperature_is_1_0(self):
        """MiniMax requires temperature in (0.0, 1.0], default must be 1.0."""
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        minimax_calls = [c for c in calls if c.get('model') in ('MiniMax-M2.7', 'MiniMax-M2.7-highspeed')]
        assert len(minimax_calls) > 0
        for call in minimax_calls:
            assert call.get('temperature') == 1.0, f"temperature must be 1.0 for MiniMax, got {call.get('temperature')}"

    def test_minimax_m2_7_and_highspeed_models_used(self):
        """Only MiniMax-M2.7 and MiniMax-M2.7-highspeed models are used."""
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        minimax_models = {c.get('model') for c in calls if 'minimax.io' in c.get('base_url', '')}
        assert 'MiniMax-M2.7' in minimax_models, f"Expected MiniMax-M2.7 in {minimax_models}"
        assert 'MiniMax-M2.7-highspeed' in minimax_models, f"Expected MiniMax-M2.7-highspeed in {minimax_models}"

    def test_no_unsupported_minimax_models(self):
        """Only approved MiniMax models are used — no other model names."""
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        minimax_calls = [c for c in calls if 'minimax.io' in c.get('base_url', '')]
        approved = {'MiniMax-M2.7', 'MiniMax-M2.7-highspeed'}
        for call in minimax_calls:
            assert call.get('model') in approved, f"Unexpected MiniMax model: {call.get('model')!r}"


class TestPersonaModelsUseMiniMax:
    """Persona models use MiniMax when MINIMAX_API_KEY is configured."""

    def test_persona_mini_uses_minimax_highspeed_model(self):
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        persona_mini_calls = [c for c in calls if c.get('model') == 'MiniMax-M2.7-highspeed']
        assert len(persona_mini_calls) > 0, "persona mini stream should use MiniMax-M2.7-highspeed"

    def test_persona_medium_uses_minimax_m2_7_model(self):
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        persona_medium_minimax_calls = [
            c for c in calls if c.get('model') == 'MiniMax-M2.7' and 'minimax.io' in c.get('base_url', '')
        ]
        assert len(persona_medium_minimax_calls) > 0, "persona medium stream should use MiniMax-M2.7"

    def test_persona_uses_openrouter_when_no_minimax_key(self):
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': '', 'OPENROUTER_API_KEY': 'openrouter-key'})
        openrouter_calls = [c for c in calls if 'openrouter.ai' in c.get('base_url', '')]
        assert (
            len(openrouter_calls) >= 2
        ), "at least two persona models should use OpenRouter when MINIMAX_API_KEY is not set"

    def test_persona_mini_uses_streaming(self):
        """Persona models must be streaming for real-time responses."""
        _, calls = _fresh_import_clients({'MINIMAX_API_KEY': 'test-key'})
        minimax_streaming_calls = [c for c in calls if 'minimax.io' in c.get('base_url', '') and c.get('streaming')]
        assert len(minimax_streaming_calls) >= 2, "MiniMax persona models must enable streaming"
