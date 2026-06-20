"""Unit tests for maintainable LLM provider/model plug-in seams."""

import os
import sys
from unittest.mock import MagicMock

import pytest

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

# Some older tests install lightweight langchain_core stubs. If this test runs
# after them, provide the prompt submodule conversation_folder imports.
if 'langchain_core' in sys.modules and 'langchain_core.prompts' not in sys.modules:
    import types

    prompts_stub = types.ModuleType('langchain_core.prompts')

    class ChatPromptTemplate:
        @classmethod
        def from_messages(cls, messages):
            return cls()

    setattr(prompts_stub, 'ChatPromptTemplate', ChatPromptTemplate)
    sys.modules['langchain_core.prompts'] = prompts_stub

os.environ.setdefault('OPENAI_API_KEY', 'sk-test')
os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test')

from utils.llm import providers
from utils.llm.conversation_folder import FolderAssignment, get_default_folder_id, validate_folder_assignment
from utils.llm.model_config import get_route_options


@pytest.fixture(autouse=True)
def clear_provider_cache():
    providers._llm_cache.clear()
    yield
    providers._llm_cache.clear()


class FakeChatOpenAI:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeChatOpenAI.calls.append(kwargs)

    def bind(self, **kwargs):
        self.bound_kwargs = kwargs
        return self


def test_openai_compatible_provider_applies_base_url_headers_and_google_prefix(monkeypatch):
    FakeChatOpenAI.calls.clear()
    providers._llm_cache.clear()
    monkeypatch.setattr(providers, 'ChatOpenAI', FakeChatOpenAI)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-openrouter')

    llm = providers.get_or_create_openai_compatible_llm(
        'openrouter', 'gemini-3-flash-preview', options={'temperature': 0.7}
    )

    assert isinstance(llm, FakeChatOpenAI)
    call = FakeChatOpenAI.calls[-1]
    assert call['model'] == 'google/gemini-3-flash-preview'
    assert call['api_key'] == 'sk-openrouter'
    assert call['base_url'] == 'https://openrouter.ai/api/v1'
    assert call['default_headers'] == {'X-Title': 'Omi Chat'}
    assert call['temperature'] == 0.7


def test_unknown_openai_compatible_provider_fails_loudly():
    with pytest.raises(ValueError, match="Unknown OpenAI-compatible provider"):
        providers.get_or_create_openai_compatible_llm('missing-provider', 'some-model')


def test_route_options_keep_provider_quirks_out_of_callsites():
    assert get_route_options('wrapped_analysis', 'gemini-3-flash-preview', 'openrouter')['temperature'] == 0.7
    assert get_route_options('followup', 'gemini-2.5-flash-lite', 'gemini')['thinking_budget'] == 0
    assert get_route_options('fair_use', 'gpt-5.1', 'openai')['extra_body'] == {"prompt_cache_retention": "24h"}


def test_validate_folder_assignment_rejects_unknown_folder_id():
    folders = [
        {'id': 'default', 'name': 'General', 'is_default': True},
        {'id': 'work', 'name': 'Work'},
    ]

    result = validate_folder_assignment(FolderAssignment(folder_id='missing', confidence=0.95), folders, 'default')

    assert result.folder_id == 'default'
    assert result.confidence == 0.3
    assert result.validation_status == 'invalid_folder_id_defaulted'


def test_validate_folder_assignment_low_confidence_uses_default():
    folders = [
        {'id': 'default', 'name': 'General', 'is_default': True},
        {'id': 'work', 'name': 'Work'},
    ]

    result = validate_folder_assignment(FolderAssignment(folder_id='work', confidence=0.4), folders, 'default')

    assert result.folder_id == 'default'
    assert result.confidence == 0.4
    assert result.validation_status == 'low_confidence_defaulted'


def test_validate_folder_assignment_accepts_valid_high_confidence():
    folders = [
        {'id': 'default', 'name': 'General', 'is_default': True},
        {'id': 'work', 'name': 'Work'},
    ]

    result = validate_folder_assignment(
        FolderAssignment(folder_id='work', confidence=0.9, reasoning='Clearly about work'), folders, 'default'
    )

    assert result.folder_id == 'work'
    assert result.confidence == 0.9
    assert result.reasoning == 'Clearly about work'
    assert result.validation_status == 'accepted'


def test_default_folder_id_is_extracted_once_for_route_logic():
    assert get_default_folder_id([{'id': 'a'}, {'id': 'b', 'is_default': True}]) == 'b'
    assert get_default_folder_id([{'id': 'a'}]) is None
