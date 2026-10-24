"""Storage-URL vision lane for chat image attachments.

#3270 follow-up: images attached to chat can now be answered straight from the
attach-time public storage copy (FileChat.source_url) instead of re-reading
provider-hosted bytes as base64 on every question. Covers both leanings:
- static image + source_url  -> provider gets the storage URL, no files.content
- no source_url              -> unchanged base64 fallback
- video attach + source_url  -> video lanes still win, filmstrip bytes stay
"""

import base64
import os
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import openai
import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from models.chat import ChatFileVideo, FileChat  # noqa: E402
from utils.other import chat_file  # noqa: E402

PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)

QUESTION = 'what is on this shirt?'
STORAGE_URL = 'https://storage.googleapis.com/chat-files/user-1/36f-image.png'


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


def _tool(uid: str = 'user-1') -> chat_file.FileChatTool:
    """A FileChatTool instance without the chat-session-roundtrip constructor."""
    tool = chat_file.FileChatTool.__new__(chat_file.FileChatTool)
    tool.uid = uid
    tool.chat_session = None
    return tool


def _file_row(**overrides) -> FileChat:
    row = {
        'id': 'img-1',
        'name': 'image.png',
        'mime_type': 'image/png',
        'openai_file_id': 'openai-file-1',
        'created_at': datetime.now(timezone.utc),
    }
    row.update(overrides)
    return FileChat(**row)


def _content_parts(messages) -> list:
    assert len(messages) == 1
    content = messages[0]['content']
    if isinstance(content, dict):
        return [content]
    return list(content)


def _image_parts(parts) -> list:
    return [part for part in parts if isinstance(part, dict) and part.get('type') == 'image_url']


def _text_parts(parts) -> list:
    return [part for part in parts if isinstance(part, dict) and part.get('type') == 'text']


# --------------------------------------------------------------------------
# storage-URL lane
# --------------------------------------------------------------------------


def test_sync_lane_uses_storage_url_and_skips_provider_read(monkeypatch):
    file_row = _file_row(source_url=STORAGE_URL)
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)

    def _forbidden(*args, **kwargs):  # pragma: no cover - must never fire
        raise AssertionError('openai.files.content called despite source_url')

    monkeypatch.setattr(openai.files, 'content', _forbidden)
    messages = _tool()._completion_messages_sync(QUESTION, [file_row])
    image_parts = _image_parts(_content_parts(messages))
    assert len(image_parts) == 1
    assert image_parts[0]['image_url']['url'] == STORAGE_URL


@pytest.mark.asyncio
async def test_async_lane_uses_storage_url_and_skips_provider_read(monkeypatch):
    file_row = _file_row(source_url=STORAGE_URL)
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)

    class _ForbiddenFiles:
        def __getattr__(self, name):  # pragma: no cover - must never fire
            raise AssertionError(f'openai.files.{name} called despite source_url')

    async def _fake_async_openai():  # unused: lane must not build provider calls
        return SimpleNamespace(files=_ForbiddenFiles())

    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: SimpleNamespace(files=_ForbiddenFiles()))
    tool_messages = await _tool()._completion_messages(QUESTION, [file_row])
    image_parts = _image_parts(_content_parts(tool_messages))
    assert len(image_parts) == 1
    assert image_parts[0]['image_url']['url'] == STORAGE_URL


# --------------------------------------------------------------------------
# legacy base64 fallback
# --------------------------------------------------------------------------


def test_sync_lane_falls_back_to_base64_without_source_url(monkeypatch):
    file_row = _file_row()
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)
    monkeypatch.setattr(openai.files, 'content', lambda file_id: BytesIO(PNG_BYTES))

    messages = _tool()._completion_messages_sync(QUESTION, [file_row])
    image_parts = _image_parts(_content_parts(messages))
    assert len(image_parts) == 1
    assert image_parts[0]['image_url']['url'].startswith('data:image/png;base64,')
    decoded = base64.b64decode(image_parts[0]['image_url']['url'].split(',', 1)[1])
    assert decoded == PNG_BYTES


@pytest.mark.asyncio
async def test_async_lane_falls_back_to_base64_without_source_url(monkeypatch):
    file_row = _file_row()
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)

    class _Content:
        def read(self):
            return PNG_BYTES

    async def _async_content(file_id):
        return _Content()

    fake_client = SimpleNamespace(files=SimpleNamespace(content=_async_content))
    monkeypatch.setattr(chat_file, '_get_async_openai', lambda: fake_client)

    tool_messages = await _tool()._completion_messages(QUESTION, [file_row])
    image_parts = _image_parts(_content_parts(tool_messages))
    assert len(image_parts) == 1
    assert image_parts[0]['image_url']['url'].startswith('data:image/png;base64,')
    decoded = base64.b64decode(image_parts[0]['image_url']['url'].split(',', 1)[1])
    assert decoded == PNG_BYTES


# --------------------------------------------------------------------------
# video attachments never take the URL shortcut
# --------------------------------------------------------------------------


def test_video_attach_with_source_url_stays_on_provider_bytes(monkeypatch):
    file_row = _file_row(
        video=ChatFileVideo(
            duration_seconds=12.0,
            frame_times=[0.0, 6.0],
            strip_file_id='strip-1',
            strip_times=[0.0, 6.0],
            strip_columns=1,
            strip_cell_width=128,
            strip_cell_height=128,
            transcript='',
        ),
        source_url=STORAGE_URL,
        mime_type='image/png',
    )
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)
    monkeypatch.setattr(openai.files, 'content', lambda file_id: BytesIO(PNG_BYTES))
    monkeypatch.setattr(
        chat_file.FileChatTool,
        '_video_note',
        lambda self, file, times, window=None: f"Attachment {file.name} frames {len(times)}",
    )
    messages = _tool()._completion_messages_sync(QUESTION, [file_row])

    parts = _content_parts(messages)
    image_parts = _image_parts(parts)
    assert len(image_parts) == 1
    assert image_parts[0]['image_url']['url'].startswith('data:image/png;base64,')


# --------------------------------------------------------------------------
# upload contract: FileChat serializes the new optional field
# --------------------------------------------------------------------------


def test_filechat_model_dump_keeps_source_url_but_not_internal_fields():
    file_row = _file_row(source_url=STORAGE_URL, thumb_name='image_thumb.png', thumbnail='http://t')
    dumped = file_row.model_dump()
    assert dumped['source_url'] == STORAGE_URL
    assert 'thumb_name' not in dumped


def test_safe_file_chats_accepts_rows_without_source_url_and_with_source_url():
    with_url = _file_row(source_url=STORAGE_URL).model_dump()
    without_url = _file_row().model_dump()
    built = chat_file.safe_file_chats([with_url, without_url])
    assert [f.source_url for f in built] == [STORAGE_URL, None]




# --------------------------------------------------------------------------
# provider error path when the storage URL is unreachable
# (pinned per review: the URL lane carries no provider bytes, so a broken
# public blob behaves as a provider rejection like any other attachment error)
# --------------------------------------------------------------------------


def _bad_request(body: object) -> openai.BadRequestError:
    return openai.BadRequestError(
        message='Error code: 400 - image_url fetch failed',
        response=SimpleNamespace(request=None, status_code=400, headers={}),
        body=body,
    )


def test_sync_provider_rejection_on_unreachable_source_url_is_a_typed_provider_error(monkeypatch):
    file_row = _file_row(source_url=STORAGE_URL)
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)
    monkeypatch.setattr(chat_file, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(chat_file, '_file_chat_gateway_enabled', lambda: False)

    seen_messages: list = []

    class _Rejection:
        @staticmethod
        def create(**kwargs):
            seen_messages.append(kwargs.get('messages'))
            raise _bad_request({'message': 'Error retrieving image from url', 'type': 'invalid_request_error'})

    monkeypatch.setattr(
        chat_file,
        '_get_sync_openai',
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=_Rejection())),
    )

    with pytest.raises(chat_file.ProviderRejectedChatFileError):
        _tool()._ask_files(QUESTION, [file_row])

    # the message carried the storage URL part: the failure is provider-side,
    # and the URL lane did not re-read provider-hosted bytes
    image_parts = _image_parts(_content_parts(seen_messages[0]))
    assert image_parts[0]['image_url']['url'] == STORAGE_URL


@pytest.mark.asyncio
async def test_async_provider_rejection_on_unreachable_source_url_is_a_typed_provider_error(monkeypatch):
    file_row = _file_row(source_url=STORAGE_URL)
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)
    monkeypatch.setattr(chat_file, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(chat_file, '_file_chat_gateway_enabled', lambda: False)

    seen_messages: list = []

    class _Rejection:
        @staticmethod
        async def create(**kwargs):
            seen_messages.append(kwargs.get('messages'))
            raise _bad_request({'message': 'Error retrieving image from url', 'type': 'invalid_request_error'})

    monkeypatch.setattr(
        chat_file,
        '_get_async_openai',
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=_Rejection())),
    )

    with pytest.raises(chat_file.ProviderRejectedChatFileError):
        await _tool()._ask_files_stream(QUESTION, [file_row], _Callback())

    image_parts = _image_parts(_content_parts(seen_messages[0]))
    assert image_parts[0]['image_url']['url'] == STORAGE_URL


@pytest.mark.asyncio
async def test_async_gateway_model_not_found_falls_back_with_url_lane_intact(monkeypatch):
    file_row = _file_row(source_url=STORAGE_URL)
    monkeypatch.setattr(chat_file, 'require_generated_compute', lambda *a, **k: None)
    monkeypatch.setattr(chat_file, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(chat_file, '_file_chat_gateway_enabled', lambda: True)
    monkeypatch.setattr(chat_file, 'file_chat_feature_header', lambda *a, **k: {})

    class _GatewayClient:
        chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: _raise_model_not_found(),
            )
        )

    monkeypatch.setattr(chat_file, 'get_file_chat_gateway_async_client', lambda: _GatewayClient())
    monkeypatch.setattr(chat_file, 'is_gateway_model_not_found', lambda _error: True)

    recorded: list[tuple] = []
    monkeypatch.setattr(chat_file, '_record_gateway_file_chat_fallback', lambda stage: recorded.append(stage))

    seen_direct_calls: list = []

    class _DirectStream:
        def __init__(self) -> None:
            self._done = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='recovered answer'))])

    class _DirectRecovery:
        @staticmethod
        async def create(**kwargs):
            seen_direct_calls.append(kwargs)
            return _DirectStream()

    monkeypatch.setattr(
        chat_file,
        '_get_async_openai',
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=_DirectRecovery())),
    )

    callback = _Callback()
    answer = await _tool()._ask_files_stream(QUESTION, [file_row], callback)

    assert answer == 'recovered answer'
    assert callback.chunks == ['recovered answer']
    assert recorded == ['recovered']
    # the fallback streamed with the storage-URL part intact
    image_parts = _image_parts(_content_parts(seen_direct_calls[0]['messages']))
    assert image_parts[0]['image_url']['url'] == STORAGE_URL


def _raise_model_not_found():
    raise openai.NotFoundError(
        message='Error code: 404 - model not found',
        response=SimpleNamespace(request=None, status_code=404, headers={}),
        body={'message': 'model not found'},
    )
