"""File chat's completions call is gateway-routed under gateway feature mode.

The model call (vision + PDF Chat Completions) must use the gateway file-chat
lanes — never a raw direct SDK client — while OpenAI Files upload/download
stays direct by design. A misconfigured prod rollout degrades to the direct
kill-switch path instead of raising.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

import utils.other.chat_file as cf  # noqa: E402
from utils.llm.gateway_client import (  # noqa: E402
    FILE_CHAT_DOCUMENTS_AUTO_LANE_ID,
    FILE_CHAT_VISION_AUTO_LANE_ID,
    LLM_GATEWAY_FEATURE_MODE_ENV_VAR,
    LLM_GATEWAY_USER_UID_HEADER,
    LLM_GATEWAY_USAGE_FEATURE_HEADER,
)

_MINIMAL_PDF = b'%PDF-1.1\n%%EOF\n'


def _gateway_mode(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)


def _vision_files():
    file_chat = SimpleNamespace(
        is_pdf=lambda: False, is_image=lambda: True, openai_file_id='file-1', mime_type='image/png', name='pic.png'
    )
    return [file_chat]


def _pdf_files():
    file_chat = SimpleNamespace(
        is_pdf=lambda: True, is_image=lambda: False, openai_file_id='file-2', mime_type='application/pdf', name='a.pdf'
    )
    return [file_chat]


def _tool(files):
    session = SimpleNamespace(id='s1')

    def _init(self, uid, sid):
        self.uid = uid
        self.chat_session = session

    with patch.object(cf.FileChatTool, '__init__', _init), patch.object(cf, 'chat_db'):
        return cf.FileChatTool('uid-1', 'session-1')


def _callback():
    callback = MagicMock()
    callback.put_data = AsyncMock()
    callback.end = AsyncMock()
    return callback


async def _fake_stream(*_args, **_kwargs):
    async def iterator():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='answer'))])

    return iterator()


async def _failing_stream(*_args, **_kwargs):
    async def iterator():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='partial'))])
        raise RuntimeError('direct stream failed')

    return iterator()


def _not_found(*, code=None, param=None):
    return openai.NotFoundError(
        message='not found',
        response=SimpleNamespace(request=None, status_code=404, headers={}),
        body={'message': 'not found', 'type': 'api_error', 'code': code, 'param': param},
    )


@pytest.mark.asyncio
async def test_stream_completion_uses_gateway_client_and_lane_under_gateway_mode(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = AsyncMock(side_effect=_fake_stream)
    direct_client = MagicMock()
    direct_client.chat.completions.create = AsyncMock(side_effect=AssertionError('direct client must not be used'))

    tool = _tool(_vision_files())
    callback = _callback()
    with patch.object(cf, 'get_file_chat_gateway_async_client', return_value=gateway_client), patch.object(
        cf, '_get_async_openai', return_value=direct_client
    ), patch.object(
        cf.FileChatTool, '_completion_messages', AsyncMock(return_value=[{'role': 'user', 'content': 'q'}])
    ):
        output = await tool._ask_files_stream('q', _vision_files(), callback)

    assert output == 'answer'
    kwargs = gateway_client.chat.completions.create.call_args.kwargs
    assert kwargs['model'] == FILE_CHAT_VISION_AUTO_LANE_ID
    assert kwargs['stream'] is True
    assert 'max_completion_tokens' in kwargs
    assert kwargs['extra_headers'][LLM_GATEWAY_USER_UID_HEADER] == 'uid-1'
    assert kwargs['extra_headers'][LLM_GATEWAY_USAGE_FEATURE_HEADER] == 'file_chat_vision'
    direct_client.chat.completions.create.assert_not_called()


def test_lane_selection_splits_vision_from_documents(monkeypatch):
    _gateway_mode(monkeypatch)
    assert cf.file_chat_auto_lane_id(pdf=True) == FILE_CHAT_DOCUMENTS_AUTO_LANE_ID
    assert cf.file_chat_auto_lane_id(pdf=False) == FILE_CHAT_VISION_AUTO_LANE_ID
    assert cf._completion_model(_vision_files()) == FILE_CHAT_VISION_AUTO_LANE_ID
    assert cf._completion_model(_pdf_files()) == FILE_CHAT_DOCUMENTS_AUTO_LANE_ID


def test_sync_completion_uses_gateway_client_under_gateway_mode(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = MagicMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    )
    with patch.object(cf, 'get_file_chat_gateway_sync_client', return_value=gateway_client), patch.object(
        cf, 'openai'
    ) as direct_openai:
        direct_openai.chat.completions.create = MagicMock(side_effect=AssertionError('direct client must not be used'))
        tool = _tool(_pdf_files())
        with patch.object(
            cf.FileChatTool, '_completion_messages_sync', MagicMock(return_value=[{'role': 'user', 'content': 'q'}])
        ):
            result = tool._ask_files('q', _pdf_files())

    assert result == 'ok'
    kwargs = gateway_client.chat.completions.create.call_args.kwargs
    assert kwargs['model'] == FILE_CHAT_DOCUMENTS_AUTO_LANE_ID
    assert 'max_completion_tokens' in kwargs
    assert kwargs['extra_headers'][LLM_GATEWAY_USER_UID_HEADER] == 'uid-1'
    assert kwargs['extra_headers'][LLM_GATEWAY_USAGE_FEATURE_HEADER] == 'file_chat_documents'


def test_completions_stay_direct_when_gateway_mode_is_misconfigured_in_prod(monkeypatch):
    # Prod runtime with gateway mode on but the allow-prod flag missing makes
    # should_route_features_through_gateway raise; file chat must still work on
    # the direct kill-switch path.
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.setenv('K_SERVICE', 'omi-backend')
    monkeypatch.delenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', raising=False)

    assert cf._file_chat_gateway_enabled() is False
    assert cf._completion_model(_vision_files()) == cf._FILE_CHAT_VISION_MODEL


def test_completions_stay_direct_outside_gateway_mode(monkeypatch):
    monkeypatch.delenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, raising=False)
    assert cf._file_chat_gateway_enabled() is False
    assert cf._completion_model(_pdf_files()) == cf._FILE_CHAT_DOCUMENT_MODEL


def test_upload_does_not_touch_the_gateway(monkeypatch, tmp_path):
    _gateway_mode(monkeypatch)
    file_path = tmp_path / 'note.pdf'
    file_path.write_bytes(_MINIMAL_PDF)

    fake_files = SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(id='file-1', filename='note.pdf'))
    with patch.object(cf.openai, 'files', fake_files), patch.object(
        cf, 'get_file_chat_gateway_sync_client', MagicMock(side_effect=AssertionError('upload is not a model call'))
    ):
        result = cf.FileChatTool.upload(file_path)

    assert result['file_id'] == 'file-1'


@pytest.mark.asyncio
async def test_async_entrypoint_routes_through_gateway(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = AsyncMock(side_effect=_fake_stream)

    tool = _tool(_vision_files())
    callback = _callback()
    with patch.object(cf, 'get_file_chat_gateway_async_client', return_value=gateway_client), patch.object(
        cf.FileChatTool, '_completion_messages', AsyncMock(return_value=[{'role': 'user', 'content': 'q'}])
    ), patch.object(cf, 'run_blocking', AsyncMock(return_value=[])), patch.object(
        cf, '_safe_file_chats', MagicMock(return_value=_vision_files())
    ):
        output = await tool.process_chat_with_file_stream('q', ['file-1'], callback)

    assert output == 'answer'
    assert gateway_client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_stream_completion_falls_back_direct_when_deployed_gateway_lacks_lane(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = AsyncMock(side_effect=_not_found(code='model_not_found'))
    direct_client = MagicMock()
    direct_client.chat.completions.create = AsyncMock(side_effect=_fake_stream)
    fallback = MagicMock()

    tool = _tool(_pdf_files())
    callback = _callback()
    with patch.object(cf, 'get_file_chat_gateway_async_client', return_value=gateway_client), patch.object(
        cf, '_get_async_openai', return_value=direct_client
    ), patch.object(
        cf.FileChatTool, '_completion_messages', AsyncMock(return_value=[{'role': 'user', 'content': 'q'}])
    ), patch.object(
        cf, 'record_fallback', fallback
    ):
        output = await tool._ask_files_stream('q', _pdf_files(), callback)

    assert output == 'answer'
    assert direct_client.chat.completions.create.call_args.kwargs['model'] == cf._FILE_CHAT_DOCUMENT_MODEL
    fallback.assert_called_once_with(
        component='llm_gateway',
        from_mode='gateway_file_chat',
        to_mode='direct_file_chat',
        reason='capability_mismatch',
        outcome='recovered',
        log=cf.logger,
    )


@pytest.mark.asyncio
async def test_stream_completion_records_exhausted_when_direct_fallback_fails(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = AsyncMock(side_effect=_not_found(code='model_not_found'))
    direct_client = MagicMock()
    direct_client.chat.completions.create = AsyncMock(side_effect=_failing_stream)
    fallback = MagicMock()

    tool = _tool(_pdf_files())
    callback = _callback()
    with patch.object(cf, 'get_file_chat_gateway_async_client', return_value=gateway_client), patch.object(
        cf, '_get_async_openai', return_value=direct_client
    ), patch.object(
        cf.FileChatTool, '_completion_messages', AsyncMock(return_value=[{'role': 'user', 'content': 'q'}])
    ), patch.object(
        cf, 'record_fallback', fallback
    ):
        with pytest.raises(RuntimeError, match='direct stream failed'):
            await tool._ask_files_stream('q', _pdf_files(), callback)

    fallback.assert_called_once_with(
        component='llm_gateway',
        from_mode='gateway_file_chat',
        to_mode='direct_file_chat',
        reason='capability_mismatch',
        outcome='exhausted',
        log=cf.logger,
    )
    callback.end.assert_awaited_once()


@pytest.mark.asyncio
async def test_gateway_file_404_stays_a_stale_attachment_failure(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = AsyncMock(side_effect=_not_found(param='file_id'))
    direct_client = MagicMock()
    fallback = MagicMock()

    tool = _tool(_pdf_files())
    callback = _callback()
    with patch.object(cf, 'get_file_chat_gateway_async_client', return_value=gateway_client), patch.object(
        cf, '_get_async_openai', return_value=direct_client
    ), patch.object(
        cf.FileChatTool, '_completion_messages', AsyncMock(return_value=[{'role': 'user', 'content': 'q'}])
    ), patch.object(
        cf, 'record_fallback', fallback
    ):
        with pytest.raises(cf.StaleChatFileError):
            await tool._ask_files_stream('q', _pdf_files(), callback)

    direct_client.chat.completions.create.assert_not_called()
    fallback.assert_not_called()


def test_sync_completion_falls_back_direct_when_deployed_gateway_lacks_lane(monkeypatch):
    _gateway_mode(monkeypatch)
    gateway_client = MagicMock()
    gateway_client.chat.completions.create = MagicMock(side_effect=_not_found(code='model_not_found'))
    direct_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    direct_client = MagicMock()
    direct_client.chat.completions.create = MagicMock(return_value=direct_response)
    fallback = MagicMock()

    tool = _tool(_pdf_files())
    with patch.object(cf, 'get_file_chat_gateway_sync_client', return_value=gateway_client), patch.object(
        cf, '_get_sync_openai', return_value=direct_client
    ), patch.object(
        cf.FileChatTool, '_completion_messages_sync', MagicMock(return_value=[{'role': 'user', 'content': 'q'}])
    ), patch.object(
        cf, 'record_fallback', fallback
    ):
        result = tool._ask_files('q', _pdf_files())

    assert result == 'ok'
    assert direct_client.chat.completions.create.call_args.kwargs['model'] == cf._FILE_CHAT_DOCUMENT_MODEL
    fallback.assert_called_once()
