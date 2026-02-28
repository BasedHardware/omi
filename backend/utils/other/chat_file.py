import asyncio
import mimetypes
import re
from pathlib import Path
from typing import List, Optional

import openai
from openai import AssistantEventHandler
from PIL import Image

import database.chat as chat_db
from models.chat import ChatSession, FileChat
import logging

logger = logging.getLogger(__name__)


class File:
    def __init__(self, file_path) -> None:
        self.file_path = Path(file_path)
        self.file_id = None
        self.thumbnail_path = ""
        self.thumbnail_name = ""
        self.mime_type = ""
        self.file_name = ""
        self.purpose = "assistants"

    def generate_thumbnail(self, size=(128, 128)):
        with Image.open(self.file_path) as img:
            file_name = Path(self.file_path).stem  # File name without extension
            file_format = img.format.lower()

            img.thumbnail(size)
            self.thumbnail_name = self._to_snake_case(f"{file_name}_thumbnail.{file_format}")

            thumb_path = self.file_path.parent / self.thumbnail_name

            img.save(thumb_path, format=img.format)
            self.thumbnail_path = str(thumb_path)

    def get_mime_type(self):
        mime_type, _ = mimetypes.guess_type(self.file_path)
        self.mime_type = str(mime_type)

    def is_image(self):
        return self.mime_type.startswith("image")

    @staticmethod
    def _to_snake_case(string) -> str:
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
    def upload(file_path) -> dict:
        result = {}
        file = File(file_path)
        file.get_mime_type()

        if file.is_image():
            file.generate_thumbnail()
            file.purpose = "vision"

        with open(file_path, 'rb') as f:
            # upload file to OpenAI
            response = openai.files.create(file=f, purpose=file.purpose)
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

    def process_chat_with_file(self, question, file_ids: List[str]):
        """Process chat with file attachments"""
        self._ensure_thread_and_assistant()
        answer = self.ask(self.uid, question, file_ids, self.thread_id, self.assistant_id)
        return answer

    def process_chat_with_file_stream(self, question, file_ids: List[str], callback=None):
        """Process chat with file attachments (streaming)"""
        self._ensure_thread_and_assistant()
        answer = self.ask_stream(self.uid, question, file_ids, self.thread_id, self.assistant_id, callback)
        return answer

    def _ensure_thread_and_assistant(self):
        """Ensure thread and assistant exist, create if needed, and save to database"""
        created_new = False
        timeout = 30.0  # 30 seconds timeout

        # Handle thread
        if self.thread_id:
            # Try to retrieve existing thread
            try:
                thread = openai.beta.threads.retrieve(self.thread_id, timeout=timeout)
                logger.info(f"Retrieved existing thread: {thread.id}")
            except Exception as e:
                logger.error(f"Failed to retrieve thread {self.thread_id}, creating new one. Error: {e}")
                self.thread_id = None

        if not self.thread_id:
            try:
                thread = openai.beta.threads.create(timeout=timeout)
                self.thread_id = thread.id
                created_new = True
                logger.info(f"Created new thread: {self.thread_id}")
            except Exception as e:
                raise Exception(f"Failed to create OpenAI thread: {e}")

        # Handle assistant
        if self.assistant_id:
            # Try to retrieve existing assistant
            try:
                assistant = openai.beta.assistants.retrieve(self.assistant_id, timeout=timeout)
                logger.info(f"Retrieved existing assistant: {assistant.id}")
            except Exception as e:
                logger.error(f"Failed to retrieve assistant {self.assistant_id}, creating new one. Error: {e}")
                self.assistant_id = None

        if not self.assistant_id:
            try:
                assistant = openai.beta.assistants.create(
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

    def _fill_question(self, uid, question, file_ids: List[str], thread_id: str):
        # OpenAI has a limit of 10 items in content array (1 text + max 9 images)
        files = chat_db.get_chat_files_desc(uid, files_id=file_ids, limit=9)

        files = [FileChat(**file) for file in files]

        contents = []
        attachments = []

        contents.append({"type": "text", "text": question})

        for file in files:
            if file.is_image():
                contents.append(
                    {"type": "image_file", "image_file": {"file_id": file.openai_file_id, "detail": "auto"}}
                )
            else:
                attachments.append({"file_id": file.openai_file_id, "tools": [{"type": "file_search"}]})

        # ask question
        openai.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=contents, attachments=attachments, timeout=30.0
        )

    def ask(self, uid, question, file_ids: List[str], thread_id: str, assistant_id: str):
        self._fill_question(uid, question, file_ids, thread_id)

        # Create run and poll for completion (with 2 minute timeout)
        run = openai.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id,
            timeout=120.0,  # 2 minutes total timeout
        )

        # Check terminal status
        if run.status == 'completed':
            # Get the messages
            messages = openai.beta.threads.messages.list(thread_id=thread_id, timeout=30.0)

            # Return the latest assistant response
            if messages.data and len(messages.data) > 0:
                return messages.data[0].content[0].text.value

            raise Exception("No response received from assistant")
        else:
            # Handle failed states
            error_msg = f"Run {run.status}"
            if hasattr(run, 'last_error') and run.last_error:
                error_msg += f": {run.last_error.message}"
            raise Exception(error_msg)

    def ask_stream(self, uid, question, file_ids: List[str], thread_id: str, assistant_id: str, callback=None):

        self._fill_question(uid, question, file_ids, thread_id)

        output_list = []

        with openai.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=assistant_id,
            event_handler=AssistantEventHandler(),
            timeout=30.0,
        ) as stream:
            for text in stream.text_deltas:
                callback.put_data_nowait(text)
                output_list.append(text)
            stream.until_done()
            callback.end_nowait()

        return ''.join(output_list)

    def cleanup(self):
        """Cleanup chat session files, thread, and assistant"""
        logger.info("start cleanup thread chat with file")
        files = chat_db.get_chat_files(self.uid)
        # delete file in db
        if files:
            chat_db.delete_multi_files(self.uid, files)

            fileObjs = [FileChat(**file) for file in files]
            # clear file in openai
            for file in fileObjs:
                try:
                    openai.files.delete(file.openai_file_id, timeout=30.0)
                except Exception as e:
                    logger.error(f"Failed to delete file {file.openai_file_id}: {e}")

        if self.thread_id:
            try:
                openai.beta.threads.delete(self.thread_id, timeout=30.0)
            except Exception as e:
                logger.error(f"Failed to delete thread {self.thread_id}: {e}")
        if self.assistant_id:
            try:
                openai.beta.assistants.delete(self.assistant_id, timeout=30.0)
            except Exception as e:
                logger.error(f"Failed to delete assistant {self.assistant_id}: {e}")
