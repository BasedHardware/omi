"""The image-chat vision call must use max_completion_tokens, not max_tokens.

PR #10907 swapped the vision model gpt-4.1 -> gpt-5.6-luna but kept max_tokens=2048, which
gpt-5.x rejects with a 400 (use max_completion_tokens). The failure was masked until the
gateway-mode upload block (#11419) was lifted; every image chat then failed with the canned
stream-failure message.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import utils.other.chat_file as cf  # noqa: E402
from models.chat import FileChat  # noqa: E402


class _EmptyStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _Callback:
    async def put_data(self, _text):
        pass

    async def end(self):
        pass


def test_vision_stream_sends_max_completion_tokens():
    captured = {}

    async def fake_content(_file_id):
        return SimpleNamespace(read=lambda: b'image-bytes')

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _EmptyStream()

    fake_client = SimpleNamespace(
        files=SimpleNamespace(content=fake_content),
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)),
    )

    tool = object.__new__(cf.FileChatTool)
    files = [
        FileChat(
            id='f1',
            name='a.png',
            mime_type='image/png',
            openai_file_id='oai-1',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]

    with patch.object(cf, '_get_async_openai', lambda: fake_client):
        asyncio.run(cf.FileChatTool._ask_files_stream(tool, 'what is this?', files, _Callback()))

    assert 'max_tokens' not in captured
    assert captured['max_completion_tokens'] == 2048
    assert captured['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
