"""Behavioral coverage for Assistants sunset → Chat Completions file chat.

SCA-362 / SCA-361: non-vision file chat must not touch beta.threads / beta.assistants,
and provider 4xx must become a single typed error frame (no canned second answer).
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
import openai
import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from models.chat import FileChat  # noqa: E402
from utils.other import chat_file  # noqa: E402
from utils.retrieval import graph  # noqa: E402
from utils.retrieval.agentic import AGENT_STREAM_FAILURE_MESSAGE  # noqa: E402
import utils.retrieval.tools.file_tools as file_tools  # noqa: E402


class _Callback:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.ended = False

    async def put_data(self, text: str) -> None:
        self.chunks.append(text)

    async def end(self) -> None:
        self.ended = True

    def end_nowait(self) -> None:
        self.ended = True


class _AsyncStream:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as error:
            raise StopAsyncIteration from error


class _ForbiddenAssistants:
    def __getattr__(self, name: str):
        raise AssertionError(f'Assistants API {name} must not be called')


def _pdf_file() -> FileChat:
    return FileChat(
        id='file-1',
        name='note.pdf',
        mime_type='application/pdf',
        openai_file_id='openai-file-1',
        created_at=datetime.now(timezone.utc),
    )


def _token(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def _not_found() -> openai.NotFoundError:
    return openai.NotFoundError(
        message='Error code: 404 - No such File object',
        response=SimpleNamespace(request=None, status_code=404, headers={}),
        body={'error': {'param': 'file_id', 'message': 'No such File object'}},
    )


@pytest.mark.asyncio
async def test_doc_file_chat_uses_completions_and_never_assistants(monkeypatch):
    request: dict[str, object] = {}

    async def create_completion(**kwargs):
        request.update(kwargs)
        return _AsyncStream([_token('PDF summary')])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion)))
    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: client)
    monkeypatch.setattr(chat_file.openai, 'beta', _ForbiddenAssistants())
    monkeypatch.setattr(
        chat_file.chat_db,
        'get_chat_files_desc',
        lambda *_args, **_kwargs: [_pdf_file().model_dump()],
    )
    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'user-1'
    tool.chat_session_id = 'session-1'
    callback = _Callback()

    answer = await tool.process_chat_with_file_stream('summarize', ['file-1'], callback)

    assert answer == 'PDF summary'
    assert callback.chunks == ['PDF summary']
    assert callback.ended is True
    assert request['model'] == 'gpt-5.6-luna'
    assert request['max_completion_tokens'] == 2048
    assert 'max_tokens' not in request
    assert request['messages'][0]['content'][1] == {'type': 'file', 'file': {'file_id': 'openai-file-1'}}
    assert getattr(tool, 'thread_id', None) is None
    assert getattr(tool, 'assistant_id', None) is None
    assert not hasattr(chat_file.chat_db, 'update_chat_session_openai_ids')


@pytest.mark.asyncio
async def test_stale_file_id_is_typed_unsupported_attachment(monkeypatch):
    async def create_completion(**_kwargs):
        raise _not_found()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion)))
    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: client)
    monkeypatch.setattr(
        chat_file.chat_db,
        'get_chat_files_desc',
        lambda *_args, **_kwargs: [_pdf_file().model_dump()],
    )

    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'uid1'
    tool.chat_session_id = 'session1'
    message = SimpleNamespace(files_id=['file-1'], text='summarize')
    session = SimpleNamespace(id='session1', file_ids=['file-1'])
    callback_data: dict[str, object] = {}

    with monkeypatch.context() as ctx:
        ctx.setattr(graph, 'FileChatTool', lambda *_args: tool)
        chunks = [
            chunk
            async for chunk in graph._execute_file_chat_stream('uid1', [message], session, callback_data=callback_data)
        ]

    assert chunks[0].startswith('error: ')
    assert 'Unsupported attachment' in chunks[0]
    assert chunks[1] is None
    assert len(chunks) == 2
    assert callback_data['error'] == 'unsupported_attachment'
    assert 'Unsupported attachment' in str(callback_data['answer'])
    assert AGENT_STREAM_FAILURE_MESSAGE not in chunks[0]


@pytest.mark.asyncio
async def test_mid_stream_completion_error_is_journey_failure(monkeypatch):
    async def create_completion(**_kwargs):
        async def _gen():
            yield _token('Hello')
            raise RuntimeError('provider dropped after first token')

        return _gen()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion)))
    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: client)
    monkeypatch.setattr(
        chat_file.chat_db,
        'get_chat_files_desc',
        lambda *_args, **_kwargs: [_pdf_file().model_dump()],
    )

    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'uid1'
    tool.chat_session_id = 'session1'
    message = SimpleNamespace(files_id=['file-1'], text='summarize')
    session = SimpleNamespace(id='session1', file_ids=['file-1'])
    callback_data: dict[str, object] = {}

    with monkeypatch.context() as ctx:
        ctx.setattr(graph, 'FileChatTool', lambda *_args: tool)
        chunks = [
            chunk
            async for chunk in graph._execute_file_chat_stream('uid1', [message], session, callback_data=callback_data)
        ]

    assert 'data: Hello' in chunks
    assert any(isinstance(chunk, str) and chunk.startswith('error: ') for chunk in chunks)
    assert chunks[-1] is None
    assert callback_data['error'] == 'stream_failure'
    assert callback_data['answer'] == AGENT_STREAM_FAILURE_MESSAGE


def test_upload_pdf_uses_user_data_and_rejects_non_pdf(tmp_path, monkeypatch):
    created: dict[str, object] = {}

    def _create(*, file, purpose):
        created['purpose'] = purpose
        return SimpleNamespace(id='file-1', filename='note.pdf')

    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))

    pdf_path = tmp_path / 'note.pdf'
    pdf_path.write_bytes(b'%PDF-1.1\n%%EOF\n')
    result = chat_file.FileChatTool.upload(pdf_path)
    assert result['file_id'] == 'file-1'
    assert created['purpose'] == 'user_data'

    txt_path = tmp_path / 'note.txt'
    txt_path.write_text('hello')
    with pytest.raises(chat_file.UnsupportedChatFileError, match='txt'):
        chat_file.FileChatTool.upload(txt_path)


def test_search_files_tool_provider_failure_is_soft(monkeypatch):
    session = {
        'id': 's1',
        'created_at': datetime.now(timezone.utc),
        'file_ids': ['f1'],
    }
    monkeypatch.setattr(file_tools.chat_db, 'get_chat_session_by_id', lambda *_args: session)

    class _Boom:
        def __init__(self, *_args, **_kwargs):
            pass

        def process_chat_with_file(self, *_args, **_kwargs):
            raise RuntimeError('failed to create OpenAI thread')

    monkeypatch.setattr(file_tools, 'FileChatTool', _Boom)

    result = file_tools.search_files_tool.func(
        question='what does this say?',
        config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}},
    )
    assert isinstance(result, str)
    assert result.startswith('I encountered an error while searching the files')
