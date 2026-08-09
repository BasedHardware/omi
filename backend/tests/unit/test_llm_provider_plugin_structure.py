"""Unit tests for maintainable LLM provider/model plug-in seams."""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _is_stub_module(module: object) -> bool:
    return isinstance(module, MagicMock) or not hasattr(module, '__path__')


_HEAVY_MOCKS = {
    'anthropic': MagicMock(),
    'firebase_admin': MagicMock(),
    'firebase_admin.firestore': MagicMock(),
    'google.cloud.firestore': MagicMock(),
    'google.cloud.firestore_v1': MagicMock(),
    'google.cloud.firestore_v1.base_query': MagicMock(),
    'tiktoken': MagicMock(encoding_for_model=MagicMock(return_value=MagicMock())),
    'database._client': MagicMock(),
    'database.llm_usage': MagicMock(),
}

# Keep the real database package importable for sibling tests.
if 'database' not in sys.modules or isinstance(sys.modules.get('database'), MagicMock):
    _database_pkg = types.ModuleType('database')
    _database_pkg.__path__ = [str(BACKEND_DIR / 'database')]
    sys.modules['database'] = _database_pkg

for _mod, _mock in _HEAVY_MOCKS.items():
    sys.modules.setdefault(_mod, _mock)
    if '.' in _mod:
        _parent_name, _child_name = _mod.rsplit('.', 1)
        _parent = sys.modules.get(_parent_name)
        if isinstance(_parent, types.ModuleType):
            setattr(_parent, _child_name, _mock)

# Prefer real langchain packages when available so sibling tests (prompt caching)
# are not poisoned by incomplete stubs installed into sys.modules.
_lc = sys.modules.get('langchain_core')
if _lc is None or _is_stub_module(_lc):
    if 'langchain_core.language_models' not in sys.modules:
        langchain_core_stub = types.ModuleType('langchain_core')
        language_models_stub = types.ModuleType('langchain_core.language_models')

        class BaseChatModel:
            pass

        setattr(language_models_stub, 'BaseChatModel', BaseChatModel)
        sys.modules.setdefault('langchain_core', langchain_core_stub)
        sys.modules['langchain_core.language_models'] = language_models_stub

    # Some older tests install lightweight langchain_core stubs. If this test runs
    # after them, provide the prompt submodule conversation_folder imports.
    if 'langchain_core.prompts' not in sys.modules:
        prompts_stub = types.ModuleType('langchain_core.prompts')

        class ChatPromptTemplate:
            @classmethod
            def from_messages(cls, messages):
                return cls()

        setattr(prompts_stub, 'ChatPromptTemplate', ChatPromptTemplate)
        sys.modules['langchain_core.prompts'] = prompts_stub

    if 'langchain_core.output_parsers' not in sys.modules:
        output_parsers_stub = types.ModuleType('langchain_core.output_parsers')

        class PydanticOutputParser:
            def __init__(self, *args, **kwargs):
                pass

        setattr(output_parsers_stub, 'PydanticOutputParser', PydanticOutputParser)
        sys.modules['langchain_core.output_parsers'] = output_parsers_stub

    if 'langchain_core.callbacks' not in sys.modules:
        callbacks_stub = types.ModuleType('langchain_core.callbacks')

        class BaseCallbackHandler:
            pass

        setattr(callbacks_stub, 'BaseCallbackHandler', BaseCallbackHandler)
        sys.modules['langchain_core.callbacks'] = callbacks_stub

    if 'langchain_core.outputs' not in sys.modules:
        outputs_stub = types.ModuleType('langchain_core.outputs')

        class LLMResult:
            pass

        setattr(outputs_stub, 'LLMResult', LLMResult)
        sys.modules['langchain_core.outputs'] = outputs_stub

if 'langchain_google_genai' not in sys.modules:
    google_genai_stub = types.ModuleType('langchain_google_genai')

    class ChatGoogleGenerativeAI:
        pass

    setattr(google_genai_stub, 'ChatGoogleGenerativeAI', ChatGoogleGenerativeAI)
    sys.modules['langchain_google_genai'] = google_genai_stub

if 'langchain_openai' not in sys.modules:
    openai_stub = types.ModuleType('langchain_openai')

    class ChatOpenAI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def bind(self, **kwargs):
            self.bound_kwargs = kwargs
            return self

    setattr(openai_stub, 'ChatOpenAI', ChatOpenAI)
    setattr(openai_stub, 'OpenAIEmbeddings', MagicMock())
    sys.modules['langchain_openai'] = openai_stub

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
    # Direct providers are the gateway recovery path and retain their existing
    # provider-sized timeout/retry budget.
    assert call['request_timeout'] == 120
    assert call['max_retries'] == 1
    assert call['temperature'] == 0.7


def test_openai_compatible_provider_adds_openai_prefix_for_gpt_models(monkeypatch):
    FakeChatOpenAI.calls.clear()
    providers._llm_cache.clear()
    monkeypatch.setattr(providers, 'ChatOpenAI', FakeChatOpenAI)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-openrouter')

    llm = providers.get_or_create_openai_compatible_llm('openrouter', 'gpt-5.6-luna')

    assert isinstance(llm, FakeChatOpenAI)
    assert FakeChatOpenAI.calls[-1]['model'] == 'openai/gpt-5.6-luna'


def test_openai_compatible_provider_adds_openai_prefix_for_o_series_models(monkeypatch):
    FakeChatOpenAI.calls.clear()
    providers._llm_cache.clear()
    monkeypatch.setattr(providers, 'ChatOpenAI', FakeChatOpenAI)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-openrouter')

    llm = providers.get_or_create_openai_compatible_llm('openrouter', 'o3-mini')

    assert isinstance(llm, FakeChatOpenAI)
    assert FakeChatOpenAI.calls[-1]['model'] == 'openai/o3-mini'


def test_unknown_openai_compatible_provider_fails_loudly():
    with pytest.raises(ValueError, match="Unknown OpenAI-compatible provider"):
        providers.get_or_create_openai_compatible_llm('missing-provider', 'some-model')


def test_route_options_keep_provider_quirks_out_of_callsites():
    assert get_route_options('wrapped_analysis', 'gemini-3-flash-preview', 'openrouter')['temperature'] == 0.7
    assert get_route_options('followup', 'gemini-2.5-flash-lite', 'gemini')['thinking_budget'] == 0
    assert get_route_options('fair_use', 'gpt-5.1', 'openai')['extra_body'] == {"prompt_cache_retention": "24h"}
    assert 'extra_body' not in get_route_options('fair_use', 'gpt-5.1', 'openrouter')


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
