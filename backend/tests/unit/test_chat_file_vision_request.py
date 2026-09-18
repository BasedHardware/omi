import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from models.chat import FileChat  # noqa: E402
from utils.other import chat_file  # noqa: E402


class _Callback:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.ended = False

    async def put_data(self, text: str) -> None:
        self.chunks.append(text)

    async def end(self) -> None:
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


@pytest.mark.asyncio
async def test_vision_chat_uses_luna_completion_budget_field(monkeypatch):
    request: dict[str, object] = {}

    async def get_file_content(_file_id: str):
        return SimpleNamespace(read=lambda: b'image bytes')

    async def create_completion(**kwargs):
        request.update(kwargs)
        return _AsyncStream(
            [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='A test image.'))])]
        )

    client = SimpleNamespace(
        files=SimpleNamespace(content=get_file_content),
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion)),
    )
    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: client)

    tool = object.__new__(chat_file.FileChatTool)
    callback = _Callback()
    image = FileChat(
        id='file-1',
        name='image.png',
        mime_type='image/png',
        openai_file_id='openai-file-1',
        created_at=datetime.now(timezone.utc),
    )

    answer = await tool._ask_files_stream('What do you see?', [image], callback)

    assert answer == 'A test image.'
    assert callback.chunks == ['A test image.']
    assert callback.ended is True
    assert request['model'] == 'gpt-5.6-luna'
    assert request['max_completion_tokens'] == 2048
    assert 'max_tokens' not in request
