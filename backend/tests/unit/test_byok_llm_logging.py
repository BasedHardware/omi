import os
import sys
import types
from importlib.util import find_spec
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


def _module_available(name: str) -> bool:
    if name in sys.modules:
        return True
    try:
        return find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


@pytest.fixture(autouse=True)
def _install_optional_import_stubs(monkeypatch):
    if 'database._client' not in sys.modules:
        monkeypatch.setitem(sys.modules, 'database._client', MagicMock())
    if 'database.llm_usage' not in sys.modules:
        llm_usage_stub = types.ModuleType('database.llm_usage')
        llm_usage_stub.record_llm_usage = MagicMock()
        monkeypatch.setitem(sys.modules, 'database.llm_usage', llm_usage_stub)

    if not _module_available('cachetools'):
        cachetools_stub = types.ModuleType('cachetools')

        class _TTLCache(dict):
            def __init__(self, *args, **kwargs):
                super().__init__()

        cachetools_stub.TTLCache = _TTLCache
        monkeypatch.setitem(sys.modules, 'cachetools', cachetools_stub)

    if not _module_available('fastapi'):
        fastapi_stub = types.ModuleType('fastapi')

        class _HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = ''):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi_stub.HTTPException = _HTTPException
        fastapi_stub.Request = MagicMock()
        monkeypatch.setitem(sys.modules, 'fastapi', fastapi_stub)

    if not _module_available('starlette.middleware.base'):
        starlette_stub = types.ModuleType('starlette')
        middleware_stub = types.ModuleType('starlette.middleware')
        base_stub = types.ModuleType('starlette.middleware.base')
        base_stub.BaseHTTPMiddleware = object
        if 'starlette' not in sys.modules:
            monkeypatch.setitem(sys.modules, 'starlette', starlette_stub)
        if 'starlette.middleware' not in sys.modules:
            monkeypatch.setitem(sys.modules, 'starlette.middleware', middleware_stub)
        monkeypatch.setitem(sys.modules, 'starlette.middleware.base', base_stub)

    if not _module_available('starlette.websockets'):
        websockets_stub = types.ModuleType('starlette.websockets')
        websockets_stub.WebSocket = MagicMock()
        monkeypatch.setitem(sys.modules, 'starlette.websockets', websockets_stub)


class _HTTPError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def test_classify_byok_llm_error_authentication():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("bad api key", 401)) == 'invalid'


def test_classify_byok_llm_error_permission():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("project denied", 403)) == 'permission'


def test_classify_byok_llm_error_insufficient_quota():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("insufficient_quota", 429)) == 'quota'


def test_classify_byok_llm_error_ignores_transient_rate_limit():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("rate limit reached, retry later", 429)) is None


@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
@patch('utils.llm.byok_errors._send_byok_llm_error_notification')
def test_handle_llm_error_logs_byok_source(mock_send_notification, mock_get_key, mock_get_uid):
    from utils.llm.byok_errors import handle_llm_error

    with patch('utils.llm.byok_errors.logger.error') as mock_log:
        handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    log_args = mock_log.call_args.args
    assert 'LLM error source=%s' in log_args[0]
    assert log_args[1] == 'byok'
    assert log_args[2] == 'openai'
    assert log_args[8] == 'quota'
    mock_send_notification.assert_called_once_with('user-1', 'openai', 'quota')


@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value=None)
def test_handle_llm_error_logs_platform_source(mock_get_key, mock_get_uid):
    from utils.llm.byok_errors import handle_llm_error

    with patch('utils.llm.byok_errors.logger.error') as mock_log:
        handle_llm_error(_HTTPError("server error", 500), 'openai', feature='memories', model='gpt-test')

    assert mock_log.call_args.args[1] == 'platform'
    assert mock_log.call_args.args[8] == 'unknown'


def test_validate_byok_request_records_current_uid():
    from utils.byok import get_byok_uid, validate_byok_request

    with patch('utils.byok._check_byok_validity', return_value=None):
        validate_byok_request('user-1')

    assert get_byok_uid() == 'user-1'


def test_llm_error_callback_uses_provider_context():
    class _BaseCallbackHandler:
        pass

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def bind(self, *args, **kwargs):
            return self

    class _DummyParser:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyEncoding:
        def encode(self, value):
            return value.split()

    anthropic_stub = types.ModuleType('anthropic')
    anthropic_stub.AsyncAnthropic = _DummyClient

    callbacks_stub = types.ModuleType('langchain_core.callbacks')
    callbacks_stub.BaseCallbackHandler = _BaseCallbackHandler
    language_models_stub = types.ModuleType('langchain_core.language_models')
    language_models_stub.BaseChatModel = _DummyClient
    output_parsers_stub = types.ModuleType('langchain_core.output_parsers')
    output_parsers_stub.PydanticOutputParser = _DummyParser

    google_genai_stub = types.ModuleType('langchain_google_genai')
    google_genai_stub.ChatGoogleGenerativeAI = _DummyClient
    openai_stub = types.ModuleType('langchain_openai')
    openai_stub.ChatOpenAI = _DummyClient
    openai_stub.OpenAIEmbeddings = _DummyClient
    tiktoken_stub = types.ModuleType('tiktoken')
    tiktoken_stub.encoding_for_model = MagicMock(return_value=_DummyEncoding())
    structured_extraction_stub = types.ModuleType('models.structured_extraction')
    structured_extraction_stub.StructuredExtraction = MagicMock()
    usage_tracker_stub = types.ModuleType('utils.llm.usage_tracker')
    usage_tracker_stub.get_usage_callback = MagicMock(return_value=object())
    usage_tracker_stub.get_current_context = MagicMock(return_value=None)

    module_stubs = {
        'anthropic': anthropic_stub,
        'langchain_core.callbacks': callbacks_stub,
        'langchain_core.language_models': language_models_stub,
        'langchain_core.output_parsers': output_parsers_stub,
        'langchain_google_genai': google_genai_stub,
        'langchain_openai': openai_stub,
        'tiktoken': tiktoken_stub,
        'models.structured_extraction': structured_extraction_stub,
        'utils.llm.usage_tracker': usage_tracker_stub,
    }

    with patch.dict(sys.modules, module_stubs):
        sys.modules.pop('utils.llm.clients', None)
        from utils.llm.clients import _LLMErrorCallback

        callback = _LLMErrorCallback('openai', model='gpt-test', feature='memories')
        error = _HTTPError('bad key', 401)

        with patch('utils.llm.clients.handle_llm_error') as mock_handle:
            callback.on_llm_error(error)

        mock_handle.assert_called_once()
        assert mock_handle.call_args.args[:2] == (error, 'openai')

    sys.modules.pop('utils.llm.clients', None)


def test_openai_embeddings_proxy_notifies_on_sync_byok_failure():
    """Regression: the synchronous embed_query/embed_documents paths must route
    BYOK failures through handle_llm_error (so the user is notified) before
    falling back to Omi's key. These explicit methods bypass the __getattr__
    wrapper, so without this routing the notification would be silently skipped.
    """

    class _BaseCallbackHandler:
        pass

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def bind(self, *args, **kwargs):
            return self

    class _DummyParser:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyEncoding:
        def encode(self, value):
            return value.split()

    anthropic_stub = types.ModuleType('anthropic')
    anthropic_stub.AsyncAnthropic = _DummyClient

    callbacks_stub = types.ModuleType('langchain_core.callbacks')
    callbacks_stub.BaseCallbackHandler = _BaseCallbackHandler
    language_models_stub = types.ModuleType('langchain_core.language_models')
    language_models_stub.BaseChatModel = _DummyClient
    output_parsers_stub = types.ModuleType('langchain_core.output_parsers')
    output_parsers_stub.PydanticOutputParser = _DummyParser

    google_genai_stub = types.ModuleType('langchain_google_genai')
    google_genai_stub.ChatGoogleGenerativeAI = _DummyClient
    openai_stub = types.ModuleType('langchain_openai')
    openai_stub.ChatOpenAI = _DummyClient
    openai_stub.OpenAIEmbeddings = _DummyClient
    tiktoken_stub = types.ModuleType('tiktoken')
    tiktoken_stub.encoding_for_model = MagicMock(return_value=_DummyEncoding())
    structured_extraction_stub = types.ModuleType('models.structured_extraction')
    structured_extraction_stub.StructuredExtraction = MagicMock()
    usage_tracker_stub = types.ModuleType('utils.llm.usage_tracker')
    usage_tracker_stub.get_usage_callback = MagicMock(return_value=object())
    usage_tracker_stub.get_current_context = MagicMock(return_value=None)

    module_stubs = {
        'anthropic': anthropic_stub,
        'langchain_core.callbacks': callbacks_stub,
        'langchain_core.language_models': language_models_stub,
        'langchain_core.output_parsers': output_parsers_stub,
        'langchain_google_genai': google_genai_stub,
        'langchain_openai': openai_stub,
        'tiktoken': tiktoken_stub,
        'models.structured_extraction': structured_extraction_stub,
        'utils.llm.usage_tracker': usage_tracker_stub,
    }

    with patch.dict(sys.modules, module_stubs):
        sys.modules.pop('utils.llm.clients', None)
        from utils.llm.clients import _OpenAIEmbeddingsProxy

        default = MagicMock()
        default.embed_query.return_value = [0.1, 0.2]
        proxy = _OpenAIEmbeddingsProxy('text-embedding-3-small', default, {})

        byok_inst = MagicMock()
        byok_inst.embed_query.side_effect = _HTTPError('invalid_api_key', 401)

        with patch.object(_OpenAIEmbeddingsProxy, '_resolve', return_value=byok_inst), patch(
            'utils.llm.clients.handle_llm_error'
        ) as mock_handle:
            result = proxy.embed_query('hello world')

        # The user must be notified about the BYOK failure...
        mock_handle.assert_called_once()
        assert mock_handle.call_args.args[1] == 'openai'
        assert mock_handle.call_args.args[0].status_code == 401
        assert mock_handle.call_args.kwargs.get('operation') == 'embed_query'
        # ...and the call must still transparently fall back to Omi's key.
        default.embed_query.assert_called_once_with('hello world')
        assert result == [0.1, 0.2]

    sys.modules.pop('utils.llm.clients', None)


def test_openai_embeddings_proxy_async_falls_back_on_byok_failure():
    """The async aembed_* paths should degrade like the sync methods: notify via
    handle_llm_error, then fall back to Omi's key on a BYOK key failure."""
    import asyncio
    from unittest.mock import AsyncMock

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass

    anthropic_stub = types.ModuleType('anthropic')
    anthropic_stub.AsyncAnthropic = _DummyClient
    callbacks_stub = types.ModuleType('langchain_core.callbacks')
    callbacks_stub.BaseCallbackHandler = object
    language_models_stub = types.ModuleType('langchain_core.language_models')
    language_models_stub.BaseChatModel = _DummyClient
    output_parsers_stub = types.ModuleType('langchain_core.output_parsers')
    output_parsers_stub.PydanticOutputParser = _DummyClient
    google_genai_stub = types.ModuleType('langchain_google_genai')
    google_genai_stub.ChatGoogleGenerativeAI = _DummyClient
    openai_stub = types.ModuleType('langchain_openai')
    openai_stub.ChatOpenAI = _DummyClient
    openai_stub.OpenAIEmbeddings = _DummyClient
    tiktoken_stub = types.ModuleType('tiktoken')
    tiktoken_stub.encoding_for_model = MagicMock(return_value=MagicMock())
    structured_extraction_stub = types.ModuleType('models.structured_extraction')
    structured_extraction_stub.StructuredExtraction = MagicMock()
    usage_tracker_stub = types.ModuleType('utils.llm.usage_tracker')
    usage_tracker_stub.get_usage_callback = MagicMock(return_value=object())
    usage_tracker_stub.get_current_context = MagicMock(return_value=None)

    module_stubs = {
        'anthropic': anthropic_stub,
        'langchain_core.callbacks': callbacks_stub,
        'langchain_core.language_models': language_models_stub,
        'langchain_core.output_parsers': output_parsers_stub,
        'langchain_google_genai': google_genai_stub,
        'langchain_openai': openai_stub,
        'tiktoken': tiktoken_stub,
        'models.structured_extraction': structured_extraction_stub,
        'utils.llm.usage_tracker': usage_tracker_stub,
    }

    with patch.dict(sys.modules, module_stubs):
        sys.modules.pop('utils.llm.clients', None)
        from utils.llm.clients import _OpenAIEmbeddingsProxy

        default = MagicMock()
        default.aembed_query = AsyncMock(return_value=[0.3, 0.4])
        proxy = _OpenAIEmbeddingsProxy('text-embedding-3-small', default, {})

        byok_inst = MagicMock()
        byok_inst.aembed_query = AsyncMock(side_effect=_HTTPError('invalid_api_key', 401))

        with patch.object(_OpenAIEmbeddingsProxy, '_resolve', return_value=byok_inst), patch(
            'utils.llm.clients.handle_llm_error'
        ) as mock_handle:
            result = asyncio.run(proxy.aembed_query('hello world'))

        mock_handle.assert_called_once()
        assert mock_handle.call_args.kwargs.get('operation') == 'aembed_query'
        default.aembed_query.assert_awaited_once_with('hello world')
        assert result == [0.3, 0.4]

    sys.modules.pop('utils.llm.clients', None)
