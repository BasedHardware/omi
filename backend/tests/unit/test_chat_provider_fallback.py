import os
import sys
import types
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

sys.modules.setdefault('database._client', MagicMock())
llm_usage_stub = types.ModuleType('database.llm_usage')
llm_usage_stub.record_llm_usage = MagicMock()
sys.modules.setdefault('database.llm_usage', llm_usage_stub)


def test_anthropic_proxy_constructs_default_client_lazily():
    from utils.llm.clients import _AnthropicClientProxy

    created = []

    def _fake_client(**kwargs):
        created.append(kwargs)
        return object()

    proxy = _AnthropicClientProxy()

    with patch('utils.llm.clients.get_byok_key', return_value=None), patch(
        'utils.llm.clients.anthropic.AsyncAnthropic', side_effect=_fake_client
    ):
        assert created == []
        proxy._resolve()

    assert created == [{'timeout': 120.0, 'max_retries': 1}]


def test_agentic_chat_provider_openai_path_is_declared():
    source = (Path(__file__).resolve().parents[2] / 'utils/retrieval/agentic.py').read_text()

    assert "CHAT_PROVIDER = os.getenv('CHAT_PROVIDER'" in source
    assert 'create_react_agent' in source
    assert 'get_openai_agent_llm(streaming=True)' in source
