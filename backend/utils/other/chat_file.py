import asyncio
from pathlib import Path
from typing import List, Optional
import openai
from PIL import Image
import mimetypes
import re
import database.chat as chat_db

from models.chat import FileChat
from openai import AssistantEventHandler

from utils.other.pattern import singleton


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


@singleton
class FileChatTool:
    def __init__(self) -> None:
        self.thread = None
        self.assistant = None
        self.file_ids = []

    def upload(self, file_path) -> dict:
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

    def process_chat_with_file(self, uid, question, file_ids: List[str]):
        self.create_thread()
        self.create_assistant()
        answer = self.ask(uid, question, file_ids)
        return answer

    def process_chat_with_file_stream(self, uid, question, file_ids: List[str], callback=None):
        self.create_thread()
        self.create_assistant()
        answer = self.ask_stream(uid, question, file_ids, callback)
        return answer

    def add_files(self, file_ids):
        self.file_ids.extend(file_ids)

    def retrieve_new_file(self, file_ids) -> List:
        return list(set(file_ids) - set(self.file_ids))

    def get_files(self):
        return self.file_ids

    def create_thread(self):
        if self.thread:
            return
        self.thread = openai.beta.threads.create()

    def create_assistant(self):
        if self.assistant:
            return
        self.assistant = openai.beta.assistants.create(
            name="File Reader",
            instructions="You are a helpful assistant that answers questions about the provided file. Use the file_search tool to search the file contents when needed.",
            model="gpt-4o",
            tools=[{"type": "file_search"}],
        )

    def _fill_question(self, uid, question, file_ids: List[str]):
        if not self.thread:
            return "Please create thread"

        # get file from db
        files = chat_db.get_chat_files(uid, file_ids)
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
            thread_id=self.thread.id, role="user", content=contents, attachments=attachments
        )

    def ask(self, uid, question, file_ids: List[str]):
        if not self.thread or not self.assistant:
            return "Please create thread & assistant"

        self._fill_question(uid, question, file_ids)

        # create run with assistant
        run = openai.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.assistant.id,
        )

        # Wait for the response
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=self.thread.id, run_id=run.id)
            if run_status.status == 'completed':
                break

        # Get the messages
        messages = openai.beta.threads.messages.list(thread_id=self.thread.id)

        # Return the latest assistant response
        return messages.data[0].content[0].text.value

    def ask_stream(self, uid, question, file_ids: List[str], callback=None):

        self._fill_question(uid, question, file_ids)

        output_list = []

        with openai.beta.threads.runs.stream(
            thread_id=self.thread.id,
            assistant_id=self.assistant.id,
            event_handler=AssistantEventHandler(),
        ) as stream:
            for text in stream.text_deltas:
                callback.put_data_nowait(text)
                output_list.append(text)
            stream.until_done()
            callback.end_nowait()

        return ''.join(output_list)

    def cleanup(self, uid):
        print("start cleanup thread chat with file")
        files = chat_db.get_chat_files(uid)
        # delete file in db
        if files:
            chat_db.delete_multi_files(uid, files)

            fileObjs = [FileChat(**file) for file in files]
            # clear file in openai
            for file in fileObjs:
                openai.files.delete(file.openai_file_id)

        if self.thread:
            openai.beta.threads.delete(self.thread.id)
            self.thread = None
        if self.assistant:
            openai.beta.assistants.delete(self.assistant.id)
            self.assistant = None
        self.file_ids = []
