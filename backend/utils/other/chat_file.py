import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Tuple, Union, cast

import openai
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
)
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

import database.chat as chat_db
from models.chat import ChatSession, FileChat
from utils.executors import db_executor, run_blocking
from utils.llm.gateway_client import (
    file_chat_auto_lane_id,
    file_chat_feature_header,
    get_file_chat_gateway_async_client,
    get_file_chat_gateway_sync_client,
    is_gateway_model_not_found,
    should_route_features_through_gateway,
)
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# Images stay on the live-verified vision lane (image_url). PDF file parts stay on
# a separate documents lane because the request shape differs ({type:file,file:{file_id}}).
# Live probe 2026-08-28 confirmed gpt-5.6-luna accepts that file-part contract, so both
# lanes pin Luna. In gateway feature mode both are omi:auto:file-chat-* lanes, so the
# model call lands in the gateway ledger; OpenAI Files upload/download stays direct
# (file bytes/file_id lifecycle, no model tokens).
_FILE_CHAT_VISION_MODEL = "gpt-5.6-luna"
_FILE_CHAT_DOCUMENT_MODEL = "gpt-5.6-luna"
_FILE_CHAT_COMPLETION_TOKENS = 2048


class UnsupportedChatFileError(Exception):
    """A chat attachment this pipeline cannot process.

    The upload routes own the client contract: a file type we cannot handle is bad request
    input, not a server fault. Without this, PIL (an iPhone .heic photo has no decoder) and
    OpenAI Files (an .ogg voice note is not an accepted extension) escape as 500s.
    """


class StaleChatFileError(Exception):
    """Provider file_id is gone or no longer readable (deleted / 404)."""


class ProviderRejectedChatFileError(Exception):
    """Provider 4xx on the Chat Completions file request, before any tokens."""


def _unsupported_chat_file_error(file_path: Union[str, Path]) -> UnsupportedChatFileError:
    suffix = Path(file_path).suffix.lstrip('.').lower()
    label = f"'{suffix}' files are" if suffix else "this file type is"
    return UnsupportedChatFileError(f"Unsupported attachment: {label} not supported in chat.")


def _safe_file_chats(files_data: List[Dict[str, Any]]) -> List[FileChat]:
    """Build FileChat objects from raw file docs, skipping (not raising on) a malformed one.

    A legacy or partial file document (missing openai_file_id, mime_type, created_at, ...) must not
    500 the whole chat-file flow. Skip such a record, logging the file id and offending field names,
    mirroring utils.apps._safe_build_app.
    """
    files: List[FileChat] = []
    for f in files_data:
        try:
            files.append(FileChat(**f))
        except ValidationError as e:
            logger.warning(
                "Skipping malformed chat file %s: %s",
                f.get('id'),
                [err['loc'][0] for err in e.errors()],
            )
    return files


def _openai_file_ids(files_data: List[Dict[str, Any]]) -> List[str]:
    """Collect openai_file_id values from raw file docs without Pydantic validation.

    Cleanup must delete provider objects even when a legacy doc fails FileChat validation
    (e.g. missing mime_type/created_at) — otherwise Firestore wipe orphans the OpenAI file.
    """
    ids: List[str] = []
    for f in files_data:
        openai_file_id = f.get('openai_file_id')
        if isinstance(openai_file_id, str) and openai_file_id:
            ids.append(openai_file_id)
    return ids


_async_openai: AsyncOpenAI | None = None


def _get_async_openai() -> AsyncOpenAI:
    global _async_openai
    if _async_openai is None:
        _async_openai = AsyncOpenAI(timeout=120.0, max_retries=1)
    return _async_openai


def _get_sync_openai() -> Any:
    """Injectable seam around the OpenAI module's lazy synchronous client."""
    return openai


def _file_chat_gateway_enabled() -> bool:
    """Whether the model call uses the gateway file-chat lanes.

    A misconfigured prod rollout (should_route_features_through_gateway raising)
    must not break file chat: it degrades to the direct kill-switch path exactly
    like FEATURE_MODE=off.
    """
    try:
        return should_route_features_through_gateway()
    except RuntimeError:
        return False


def _file_is_pdf(name: str, mime_type: str) -> bool:
    if (mime_type or '').lower() == 'application/pdf':
        return True
    return Path(name).suffix.lower() == '.pdf'


def _reraise_provider_file_error(error: Exception) -> NoReturn:
    if isinstance(error, openai.NotFoundError):
        raise StaleChatFileError("Unsupported attachment: the uploaded file is no longer available.") from error
    if isinstance(error, openai.BadRequestError):
        raise ProviderRejectedChatFileError("The file could not be processed.") from error
    raise error


def _completion_model(files: List[FileChat]) -> str:
    """Model id for the completions call: a gateway lane id in gateway mode."""
    pdf = bool(files) and any(f.is_pdf() for f in files)
    if _file_chat_gateway_enabled():
        return file_chat_auto_lane_id(pdf=pdf)
    return _direct_completion_model(files)


def _direct_completion_model(files: List[FileChat]) -> str:
    """Provider model for the feature-off and compatibility fallback paths."""
    pdf = bool(files) and any(f.is_pdf() for f in files)
    if pdf:
        return _FILE_CHAT_DOCUMENT_MODEL
    return _FILE_CHAT_VISION_MODEL


def _record_gateway_file_chat_fallback(outcome: str) -> None:
    """Record the terminal result of an admitted gateway compatibility fallback."""
    record_fallback(
        component='llm_gateway',
        from_mode='gateway_file_chat',
        to_mode='direct_file_chat',
        reason='capability_mismatch',
        outcome=outcome,
        log=logger,
    )


class _StreamingCallbackProtocol:
    """Structural protocol for streaming callbacks (AsyncStreamingCallback in retrieval.agentic)."""

    def put_data_nowait(self, text: str) -> None: ...

    async def put_data(self, text: str) -> None: ...

    def end_nowait(self) -> None: ...

    async def end(self) -> None: ...


class File:
    def __init__(self, file_path: Union[str, Path]) -> None:
        self.file_path = Path(file_path)
        self.file_id: Optional[str] = None
        self.thumbnail_path = ""
        self.thumbnail_name = ""
        self.mime_type = ""
        self.file_name = ""
        self.purpose = "user_data"

    def generate_thumbnail(self, size: Tuple[int, int] = (128, 128)) -> None:
        with Image.open(self.file_path) as img:
            file_name = Path(self.file_path).stem  # File name without extension
            assert img.format is not None  # PIL.Image opened from a path always has a format
            file_format = img.format.lower()

            img.thumbnail(size)
            self.thumbnail_name = self._to_snake_case(f"{file_name}_thumbnail.{file_format}")

            thumb_path = self.file_path.parent / self.thumbnail_name

            img.save(thumb_path, format=img.format)
            self.thumbnail_path = str(thumb_path)

    def get_mime_type(self) -> None:
        mime_type, _ = mimetypes.guess_type(self.file_path)
        self.mime_type = str(mime_type)

    def is_image(self) -> bool:
        return self.mime_type.startswith("image")

    def is_pdf(self) -> bool:
        return _file_is_pdf(str(self.file_path), self.mime_type)

    @staticmethod
    def _to_snake_case(string: str) -> str:
        string = re.sub(r"[\s\-]+", "_", string)
        # Add an underscore before any capital letter that is preceded by a lowercase or digit
        string = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", string)
        return string.lower()


class FileChatTool:
    def __init__(self, uid: str, chat_session_id: str) -> None:
        self.uid = uid
        self.chat_session_id = chat_session_id

        # Load chat session from database
        session_data = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if not session_data:
            raise ValueError(f"Chat session {chat_session_id} not found for user {uid}")

        self.chat_session = ChatSession(**session_data)

    @staticmethod
    def upload(file_path: Union[str, Path]) -> Dict[str, Any]:
        # OpenAI Files upload/download stays direct by design: it is the file
        # bytes/file_id lifecycle, not a model call; only the completions hop
        # is gateway-metered.
        result: Dict[str, Any] = {}
        file = File(file_path)
        file.get_mime_type()

        if file.is_image():
            try:
                file.generate_thumbnail()
            except UnidentifiedImageError as error:
                # An image mime type Pillow has no decoder for (.heic from an iPhone camera roll).
                raise _unsupported_chat_file_error(file_path) from error
            file.purpose = "vision"
        elif file.is_pdf():
            file.purpose = "user_data"
        else:
            # Chat Completions file parts accept PDFs. Reject other docs at attach,
            # never after the user sends the chat.
            raise _unsupported_chat_file_error(file_path)

        with open(file_path, 'rb') as f:
            # upload file to OpenAI
            try:
                response = openai.files.create(file=f, purpose=cast(Any, file.purpose))
            except openai.BadRequestError as error:
                # The provider rejects the extension (audio/video, archives it does not index).
                raise _unsupported_chat_file_error(file_path) from error
            if response:
                file.file_id = response.id
                file.file_name = response.filename

                result["file_name"] = response.filename
                result["file_id"] = response.id
                result["mime_type"] = file.mime_type
                if file.is_image():
                    result["thumbnail"] = file.thumbnail_path
                    result["thumbnail_name"] = file.thumbnail_name
        return result

    def process_chat_with_file(self, question: str, file_ids: List[str]) -> str:
        """Process chat with file attachments (non-streaming, agentic tool path)."""
        files_data = chat_db.get_chat_files_desc(self.uid, files_id=file_ids, limit=9)
        files = _safe_file_chats(files_data)
        return self._ask_files(question, files)

    async def process_chat_with_file_stream(
        self,
        question: str,
        file_ids: List[str],
        callback: Optional[_StreamingCallbackProtocol] = None,
    ) -> str:
        """Process chat with file attachments (streaming)."""
        # Offloaded: the Firestore read is sync and blocks the event loop in this async path.
        # If this pre-stream setup fails, signal the streaming callback's end before propagating
        # so it is not left dangling.
        assert callback is not None  # streaming path always supplies a callback
        try:
            files_data = await run_blocking(
                db_executor, chat_db.get_chat_files_desc, self.uid, files_id=file_ids, limit=9
            )
            files = _safe_file_chats(files_data)
        except Exception:
            callback.end_nowait()
            raise

        return await self._ask_files_stream(question, files, callback)

    async def _ask_files_stream(
        self,
        question: str,
        files: List[FileChat],
        callback: Optional[_StreamingCallbackProtocol] = None,
    ) -> str:
        """One Chat Completions stream: images as base64 image_url, PDFs as file parts."""
        assert callback is not None
        output_list: List[str] = []
        gateway_fallback_used = False
        try:
            try:
                try:
                    messages = await self._completion_messages(question, files)
                    gateway_enabled = _file_chat_gateway_enabled()
                    model = _completion_model(files)
                    if gateway_enabled:
                        # Gateway lanes accept max_completion_tokens on every model
                        # and stay in the ledger; typed SDK errors keep their meaning.
                        try:
                            stream = await get_file_chat_gateway_async_client().chat.completions.create(
                                model=model,
                                messages=messages,
                                stream=True,
                                max_completion_tokens=_FILE_CHAT_COMPLETION_TOKENS,
                                extra_headers=file_chat_feature_header(model, uid=self.uid),
                            )
                        except openai.NotFoundError as error:
                            if not is_gateway_model_not_found(error):
                                raise
                            gateway_fallback_used = True
                            model = _direct_completion_model(files)
                            stream = await _get_async_openai().chat.completions.create(
                                model=model,
                                messages=messages,
                                stream=True,
                                max_completion_tokens=_FILE_CHAT_COMPLETION_TOKENS,
                            )
                    else:
                        model = _direct_completion_model(files)
                        stream = await _get_async_openai().chat.completions.create(
                            model=model,
                            messages=messages,
                            stream=True,
                            max_completion_tokens=_FILE_CHAT_COMPLETION_TOKENS,
                        )
                except (openai.NotFoundError, openai.BadRequestError) as error:
                    _reraise_provider_file_error(error)
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        await callback.put_data(delta.content)
                        output_list.append(delta.content)
            finally:
                await callback.end()
        except Exception:
            if gateway_fallback_used:
                _record_gateway_file_chat_fallback('exhausted')
            raise
        if gateway_fallback_used:
            _record_gateway_file_chat_fallback('recovered')
        return ''.join(output_list)

    def _ask_files(self, question: str, files: List[FileChat]) -> str:
        """Non-streaming Chat Completions path used by search_files_tool."""
        gateway_fallback_used = False
        try:
            try:
                messages = self._completion_messages_sync(question, files)
                gateway_enabled = _file_chat_gateway_enabled()
                model = _completion_model(files)
                if gateway_enabled:
                    try:
                        response = get_file_chat_gateway_sync_client().chat.completions.create(
                            model=model,
                            messages=messages,
                            max_completion_tokens=_FILE_CHAT_COMPLETION_TOKENS,
                            extra_headers=file_chat_feature_header(model, uid=self.uid),
                        )
                    except openai.NotFoundError as error:
                        if not is_gateway_model_not_found(error):
                            raise
                        gateway_fallback_used = True
                        model = _direct_completion_model(files)
                        response = _get_sync_openai().chat.completions.create(
                            model=model,
                            messages=messages,
                            max_completion_tokens=_FILE_CHAT_COMPLETION_TOKENS,
                        )
                else:
                    model = _direct_completion_model(files)
                    response = _get_sync_openai().chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=_FILE_CHAT_COMPLETION_TOKENS,
                    )
            except (openai.NotFoundError, openai.BadRequestError) as error:
                _reraise_provider_file_error(error)
            choice = response.choices[0] if response.choices else None
            content = choice.message.content if choice and choice.message else None
            if not content:
                raise ProviderRejectedChatFileError("The file could not be processed.")
        except Exception:
            if gateway_fallback_used:
                _record_gateway_file_chat_fallback('exhausted')
            raise
        if gateway_fallback_used:
            _record_gateway_file_chat_fallback('recovered')
        return content

    async def _completion_messages(self, question: str, files: List[FileChat]) -> List[ChatCompletionMessageParam]:
        contents: List[ChatCompletionContentPartParam] = [{"type": "text", "text": question}]
        openai_client = _get_async_openai()
        for file in files:
            if file.is_image():
                try:
                    file_content = await openai_client.files.content(file.openai_file_id)
                    raw = file_content.read()
                except (openai.NotFoundError, openai.BadRequestError) as error:
                    _reraise_provider_file_error(error)
                b64 = base64.b64encode(raw).decode('utf-8')
                mime = file.mime_type or 'image/png'
                contents.append(
                    cast(
                        ChatCompletionContentPartParam,
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "auto"},
                        },
                    )
                )
            elif file.is_pdf():
                contents.append(
                    cast(
                        ChatCompletionContentPartParam,
                        {"type": "file", "file": {"file_id": file.openai_file_id}},
                    )
                )
            else:
                raise UnsupportedChatFileError(
                    f"Unsupported attachment: '{Path(file.name).suffix.lstrip('.').lower() or 'this'}' "
                    "files are not supported in chat."
                )
        return [cast(ChatCompletionMessageParam, {"role": "user", "content": contents})]

    def _completion_messages_sync(self, question: str, files: List[FileChat]) -> List[ChatCompletionMessageParam]:
        contents: List[ChatCompletionContentPartParam] = [{"type": "text", "text": question}]
        for file in files:
            if file.is_image():
                try:
                    file_content = openai.files.content(file.openai_file_id)
                    raw = file_content.read()
                except (openai.NotFoundError, openai.BadRequestError) as error:
                    _reraise_provider_file_error(error)
                b64 = base64.b64encode(raw).decode('utf-8')
                mime = file.mime_type or 'image/png'
                contents.append(
                    cast(
                        ChatCompletionContentPartParam,
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "auto"},
                        },
                    )
                )
            elif file.is_pdf():
                contents.append(
                    cast(
                        ChatCompletionContentPartParam,
                        {"type": "file", "file": {"file_id": file.openai_file_id}},
                    )
                )
            else:
                raise UnsupportedChatFileError(
                    f"Unsupported attachment: '{Path(file.name).suffix.lstrip('.').lower() or 'this'}' "
                    "files are not supported in chat."
                )
        return [cast(ChatCompletionMessageParam, {"role": "user", "content": contents})]

    def cleanup(self) -> None:
        """Cleanup chat session files on OpenAI. Thread/assistant deletes are gone with Assistants."""
        logger.info("start cleanup chat with file")
        files = chat_db.get_chat_files(self.uid)
        if files:
            # Delete OpenAI objects from raw docs first — do not gate on FileChat validation,
            # or a malformed doc with openai_file_id leaks after Firestore delete (#9608 follow-up).
            for openai_file_id in _openai_file_ids(files):
                try:
                    openai.files.delete(openai_file_id, timeout=30.0)
                except Exception as error:
                    logger.error('file chat file deletion failed error_type=%s', type(error).__name__)
            chat_db.delete_multi_files(self.uid, files)
