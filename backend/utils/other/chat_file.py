import base64
import mimetypes
import re
from pathlib import Path
from typing import List

import openai
from PIL import Image

import database.chat as chat_db
from models.chat import ChatSession, FileChat


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
        """Process chat with file attachments using Chat Completions API"""
        answer = self.ask(self.uid, question, file_ids)
        return answer

    def process_chat_with_file_stream(self, question, file_ids: List[str], callback=None):
        """Process chat with file attachments (streaming) using Chat Completions API"""
        answer = self.ask_stream(self.uid, question, file_ids, callback)
        return answer

    def ask(self, uid, question, file_ids: List[str]):
        """Use Chat Completions API with file attachments"""
        # Get files from database
        files = chat_db.get_chat_files_desc(uid, files_id=file_ids, limit=10)

        if not files:
            print(f"❌ No files found for provided IDs")
            raise Exception("No files found for provided IDs")

        files = [FileChat(**file) for file in files]

        # Build message content
        content_parts = []

        # Add files first
        for file in files:
            if file.is_image():
                # For images, download and convert to base64 data URL
                try:
                    file_content = openai.files.content(file.openai_file_id)
                    image_data = file_content.read()
                    base64_image = base64.b64encode(image_data).decode('utf-8')

                    # Get the image format from mime type (e.g., "image/jpeg" -> "jpeg")
                    image_format = file.mime_type.split('/')[-1] if '/' in file.mime_type else 'jpeg'

                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{file.mime_type};base64,{base64_image}", "detail": "auto"},
                        }
                    )
                except Exception as e:
                    print(f"  ❌ Failed to download image: {e}")
                    raise
            else:
                # For documents, use the file type with file_id
                content_parts.append({"type": "file", "file": {"file_id": file.openai_file_id}})

        # Add the question text last
        content_parts.append({"type": "text", "text": question})

        # Create message structure
        message = {"role": "user", "content": content_parts}

        try:
            response = openai.chat.completions.create(model="gpt-5", messages=[message], timeout=120.0)

            answer = response.choices[0].message.content
            return answer

        except Exception as e:
            print(f"❌ Chat completion failed with error: {e}")
            raise

    def ask_stream(self, uid, question, file_ids: List[str], callback=None):
        """Use Chat Completions API with file attachments (streaming)"""
        # Get files from database
        files = chat_db.get_chat_files_desc(uid, files_id=file_ids, limit=10)

        if not files:
            print(f"❌ No files found for provided IDs")
            raise Exception("No files found for provided IDs")

        files = [FileChat(**file) for file in files]

        # Build message content
        content_parts = []

        # Add files first
        for file in files:
            if file.is_image():
                # For images, download and convert to base64 data URL
                try:
                    file_content = openai.files.content(file.openai_file_id)
                    image_data = file_content.read()
                    base64_image = base64.b64encode(image_data).decode('utf-8')

                    # Get the image format from mime type (e.g., "image/jpeg" -> "jpeg")
                    image_format = file.mime_type.split('/')[-1] if '/' in file.mime_type else 'jpeg'

                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{file.mime_type};base64,{base64_image}", "detail": "auto"},
                        }
                    )
                except Exception as e:
                    print(f"  ❌ Failed to download image: {e}")
                    raise
            else:
                # For documents, use the file type with file_id
                content_parts.append({"type": "file", "file": {"file_id": file.openai_file_id}})

        # Add the question text last
        content_parts.append({"type": "text", "text": question})

        # Create message structure
        message = {"role": "user", "content": content_parts}

        output_list = []

        try:
            stream = openai.chat.completions.create(model="gpt-5", messages=[message], stream=True, timeout=120.0)

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    callback.put_data_nowait(text)
                    output_list.append(text)

            callback.end_nowait()
            return ''.join(output_list)

        except Exception as e:
            print(f"❌ Streaming chat completion failed with error: {e}")
            callback.end_nowait()
            raise

    def cleanup(self):
        """Cleanup chat session files"""
        print("start cleanup chat files")
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
                    print(f"Failed to delete file {file.openai_file_id}: {e}")
