import base64
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import openai
from openai import AsyncOpenAI, AssistantEventHandler
from openai.types.beta.threads import TextContentBlock
from openai.types.chat import (
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
)
from PIL import Image
from pydantic import ValidationError

import database.chat as chat_db
from models.chat import ChatSession, FileChat
from utils.executors import db_executor, run_blocking
from utils.llm.gateway_client import raise_if_gateway_feature_mode_blocks_direct_model_surface
import logging

logger = logging.getLogger(__name__)


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
        _async_openai = AsyncOpenAI()
    return _async_openai


def _assert_direct_file_chat_allowed() -> None:
    raise_if_gateway_feature_mode_blocks_direct_model_surface('file_chat.openai_files_assistants_vision')


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
        self.purpose = "assistants"

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

        # Get thread and assistant IDs from session (may be None)
        self.thread_id = self.chat_session.openai_thread_id
        self.assistant_id = self.chat_session.openai_assistant_id

    @staticmethod
    def upload(file_path: Union[str, Path]) -> Dict[str, Any]:
        _assert_direct_file_chat_allowed()
        result: Dict[str, Any] = {}
        file = File(file_path)
        file.get_mime_type()

        if file.is_image():
            file.generate_thumbnail()
            file.purpose = "vision"

        with open(file_path, 'rb') as f:
            # upload file to OpenAI
            response = openai.files.create(file=f, purpose=cast(Any, file.purpose))
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
        """Process chat with file attachments"""
        _assert_direct_file_chat_allowed()
        self._ensure_thread_and_assistant()
        answer = self.ask(self.uid, question, file_ids, self.thread_id, self.assistant_id)
        return answer

    async def process_chat_with_file_stream(
        self,
        question: str,
        file_ids: List[str],
        callback: Optional[_StreamingCallbackProtocol] = None,
    ) -> str:
        """Process chat with file attachments (streaming)"""
        _assert_direct_file_chat_allowed()
        # Offloaded: the Firestore read is sync and blocks the event loop in this async path.
        # If this pre-stream setup fails, signal the streaming callback's end before propagating
        # (mirrors the _ensure_thread_and_assistant failure path below) so it is not left dangling.
        assert callback is not None  # streaming path always supplies a callback
        try:
            files_data = await run_blocking(
                db_executor, chat_db.get_chat_files_desc, self.uid, files_id=file_ids, limit=9
            )
            files = _safe_file_chats(files_data)
            all_images = all(f.is_image() for f in files) if files else False
        except Exception:
            callback.end_nowait()
            raise

        if all_images and files:
            logger.info(f"[FileChat] All {len(files)} files are images, using Chat Completions vision API")
            answer = await self._ask_vision_stream(question, files, callback)
            return answer

        # _ensure_thread_and_assistant can fail before ask_stream runs.
        # ask_stream has its own try/finally on callback, so only guard
        # the setup phase here.
        try:
            self._ensure_thread_and_assistant()
        except Exception:
            callback.end_nowait()
            raise
        answer = self.ask_stream(self.uid, question, file_ids, self.thread_id, self.assistant_id, callback)
        return answer

    async def _ask_vision_stream(
        self,
        question: str,
        files: List[FileChat],
        callback: Optional[_StreamingCallbackProtocol] = None,
    ) -> str:
        """Use Chat Completions API with vision for image-only chats (streaming)"""
        assert callback is not None
        output_list: List[str] = []
        try:
            contents: List[ChatCompletionContentPartParam] = [{"type": "text", "text": question}]
            openai_client = _get_async_openai()
            for file in files:
                file_content = await openai_client.files.content(file.openai_file_id)
                b64 = base64.b64encode(file_content.read()).decode('utf-8')
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

            messages: List[ChatCompletionMessageParam] = [
                cast(ChatCompletionMessageParam, {"role": "user", "content": contents})
            ]
            stream = await openai_client.chat.completions.create(
                model="gpt-4.1",
                messages=messages,
                stream=True,
                max_tokens=2048,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    await callback.put_data(delta.content)
                    output_list.append(delta.content)
        finally:
            await callback.end()
        return ''.join(output_list)

    def _ensure_thread_and_assistant(self) -> None:
        """Ensure thread and assistant exist, create if needed, and save to database"""
        created_new = False
        timeout = 30.0  # 30 seconds timeout

        # Handle thread
        if self.thread_id:
            # Try to retrieve existing thread
            try:
                thread = openai.beta.threads.retrieve(self.thread_id, timeout=timeout)  # type: ignore[reportDeprecated]  # Assistants API still in use
                logger.info(f"Retrieved existing thread: {thread.id}")
            except Exception as e:
                logger.error(f"Failed to retrieve thread {self.thread_id}, creating new one. Error: {e}")
                self.thread_id = None

        if not self.thread_id:
            try:
                thread = openai.beta.threads.create(timeout=timeout)  # type: ignore[reportDeprecated]  # Assistants API still in use
                self.thread_id = thread.id
                created_new = True
                logger.info(f"Created new thread: {self.thread_id}")
            except Exception as e:
                raise Exception(f"Failed to create OpenAI thread: {e}")

        # Handle assistant
        if self.assistant_id:
            # Try to retrieve existing assistant
            try:
                assistant = openai.beta.assistants.retrieve(self.assistant_id, timeout=timeout)  # type: ignore[reportDeprecated]  # Assistants API still in use
                logger.info(f"Retrieved existing assistant: {assistant.id}")
            except Exception as e:
                logger.error(f"Failed to retrieve assistant {self.assistant_id}, creating new one. Error: {e}")
                self.assistant_id = None

        if not self.assistant_id:
            try:
                assistant = openai.beta.assistants.create(  # type: ignore[reportDeprecated]  # Assistants API still in use
                    name="File Reader",
                    instructions="You are a helpful assistant that answers questions about the provided file. Use the file_search tool to search the file contents when needed.",
                    model="gpt-4.1",
                    tools=[{"type": "file_search"}],
                    timeout=timeout,
                )
                self.assistant_id = assistant.id
                created_new = True
                logger.info(f"Created new assistant: {self.assistant_id}")
            except Exception as e:
                raise Exception(f"Failed to create OpenAI assistant: {e}")

        # Save to database if we created new ones
        if created_new:
            try:
                chat_db.update_chat_session_openai_ids(
                    self.uid, self.chat_session_id, self.thread_id, self.assistant_id
                )
            except Exception as e:
                logger.error(f"Failed to save thread/assistant IDs to database: {e}")
                # Continue anyway - IDs will be recreated next time

    def _fill_question(self, uid: str, question: str, file_ids: List[str], thread_id: str) -> None:
        # OpenAI has a limit of 10 items in content array (1 text + max 9 images)
        files = chat_db.get_chat_files_desc(uid, files_id=file_ids, limit=9)

        files_typed = _safe_file_chats(files)

        contents: List[Dict[str, Any]] = []
        attachments: List[Dict[str, Any]] = []

        contents.append({"type": "text", "text": question})

        for file in files_typed:
            if file.is_image():
                contents.append(
                    {"type": "image_file", "image_file": {"file_id": file.openai_file_id, "detail": "auto"}}
                )
            else:
                attachments.append({"file_id": file.openai_file_id, "tools": [{"type": "file_search"}]})

        # ask question
        openai.beta.threads.messages.create(  # type: ignore[reportDeprecated]  # Assistants API still in use
            thread_id=thread_id,
            role="user",
            content=contents,  # type: ignore[arg-type]  # openai accepts a permissive dict shape here
            attachments=attachments,  # type: ignore[arg-type]  # openai accepts a permissive dict shape here
            timeout=30.0,
        )

    def ask(
        self,
        uid: str,
        question: str,
        file_ids: List[str],
        thread_id: Optional[str],
        assistant_id: Optional[str],
    ) -> str:
        assert thread_id is not None and assistant_id is not None  # caller ensures IDs are set
        self._fill_question(uid, question, file_ids, thread_id)

        # Create run and poll for completion (with 2 minute timeout)
        run = openai.beta.threads.runs.create_and_poll(  # type: ignore[reportDeprecated]  # Assistants API still in use
            thread_id=thread_id,
            assistant_id=assistant_id,
            timeout=120.0,  # 2 minutes total timeout
        )

        # Check terminal status
        if run.status == 'completed':
            # Get the messages
            messages = openai.beta.threads.messages.list(thread_id=thread_id, timeout=30.0)  # type: ignore[reportDeprecated]  # Assistants API still in use

            # Return the latest assistant response
            if messages.data and len(messages.data) > 0:
                first_block = messages.data[0].content[0]
                if isinstance(first_block, TextContentBlock):
                    return first_block.text.value
                # Fall back to the original attribute access for any non-text block,
                # which raises AttributeError — matching the prior behavior.
                return first_block.text.value  # type: ignore[union-attr]  # preserve prior crash semantics for non-text blocks

            raise Exception("No response received from assistant")
        else:
            # Handle failed states
            error_msg = f"Run {run.status}"
            if hasattr(run, 'last_error') and run.last_error:
                error_msg += f": {run.last_error.message}"
            raise Exception(error_msg)

    def ask_stream(
        self,
        uid: str,
        question: str,
        file_ids: List[str],
        thread_id: Optional[str],
        assistant_id: Optional[str],
        callback: Optional[_StreamingCallbackProtocol] = None,
    ) -> str:
        assert thread_id is not None and assistant_id is not None and callback is not None

        output_list: List[str] = []

        try:
            self._fill_question(uid, question, file_ids, thread_id)

            with openai.beta.threads.runs.stream(  # type: ignore[reportDeprecated]  # Assistants API still in use
                thread_id=thread_id,
                assistant_id=assistant_id,
                event_handler=AssistantEventHandler(),
                timeout=30.0,
            ) as stream:
                for text in stream.text_deltas:
                    callback.put_data_nowait(text)
                    output_list.append(text)
                stream.until_done()
        finally:
            callback.end_nowait()

        return ''.join(output_list)

    def cleanup(self) -> None:
        """Cleanup chat session files, thread, and assistant"""
        logger.info("start cleanup thread chat with file")
        files = chat_db.get_chat_files(self.uid)
        if files:
            # Delete OpenAI objects from raw docs first — do not gate on FileChat validation,
            # or a malformed doc with openai_file_id leaks after Firestore delete (#9608 follow-up).
            for openai_file_id in _openai_file_ids(files):
                try:
                    openai.files.delete(openai_file_id, timeout=30.0)
                except Exception as e:
                    logger.error(f"Failed to delete file {openai_file_id}: {e}")
            chat_db.delete_multi_files(self.uid, files)

        if self.thread_id:
            try:
                openai.beta.threads.delete(self.thread_id, timeout=30.0)  # type: ignore[reportDeprecated]  # Assistants API still in use
            except Exception as e:
                logger.error(f"Failed to delete thread {self.thread_id}: {e}")
        if self.assistant_id:
            try:
                openai.beta.assistants.delete(self.assistant_id, timeout=30.0)  # type: ignore[reportDeprecated]  # Assistants API still in use
            except Exception as e:
                logger.error(f"Failed to delete assistant {self.assistant_id}: {e}")
