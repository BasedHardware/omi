"""Owned media bridge to the existing chat file and pre-recorded STT services."""

import tempfile
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from utils.executors import run_blocking, storage_executor, db_executor
from utils.messaging.contracts import Artifact

MAX_MEDIA_BYTES = 20_000_000
MEDIA_TYPES = (
    'image/jpeg',
    'image/png',
    'application/pdf',
    'text/plain',
    'text/csv',
    'audio/ogg',
    'audio/mp4',
    'text/vcard',
)


class ChatMediaStore:
    def ingest(self, uid, attachment, data):
        from database import chat
        from models.chat import FileChat
        from utils.other.chat_file import FileChatTool
        from utils.other import storage

        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError('Media too large')
        name = Path(attachment.name).name
        if not name or name in ('.', '..'):
            raise ValueError('Invalid filename')
        with tempfile.TemporaryDirectory(prefix='omi-channel-') as directory:
            path = Path(directory) / name
            path.write_bytes(data)
            result = FileChatTool.upload(path, file_name=name)
            thumb = result.get('thumbnail')
            urls = storage.upload_multi_chat_files([thumb], uid) if thumb else {}
            row = FileChat(
                id=str(uuid4()),
                name=name,
                mime_type=result['mime_type'],
                openai_file_id=result['file_id'],
                created_at=datetime.now(timezone.utc),
                thumbnail=urls.get(str(thumb), ''),
            ).model_dump()
            if thumb:
                Path(thumb).unlink(missing_ok=True)
            # Store ownership metadata in the same user's file collection.
            row['size'] = len(data)
            chat.add_multi_files(uid, [row])
        return Artifact(row['id'], row['mime_type'], len(data), name)

    def transcribe(self, data):
        from utils.stt.pre_recorded import prerecorded_from_bytes

        words = prerecorded_from_bytes(data, diarize=False)
        if isinstance(words, tuple):
            words = words[0]
        return ' '.join(str(word.get('punctuated_word') or word.get('word', '')) for word in words).strip()

    def resolve(self, uid, artifact):
        from database import chat
        from utils.other.chat_file import download_owned_chat_file

        rows = chat.get_chat_files(uid, [artifact.file_store_ref])
        if len(rows) != 1:
            raise PermissionError('File is not owned by this user')
        row = rows[0]
        if row['mime_type'] != artifact.mime_type or row['name'] != artifact.name:
            raise PermissionError('Artifact metadata mismatch')
        data = download_owned_chat_file(uid, artifact.file_store_ref, max_bytes=MAX_MEDIA_BYTES)
        if len(data) != artifact.size or len(data) > MAX_MEDIA_BYTES:
            raise ValueError('Artifact size mismatch')
        return data

    def artifact(self, uid, file_id):
        from database import chat

        rows = chat.get_chat_files(uid, [file_id])
        if len(rows) != 1 or 'size' not in rows[0]:
            raise PermissionError('Owned deliverable file unavailable')
        row = rows[0]
        return Artifact(file_id, row['mime_type'], row['size'], row['name'])


async def prepare_media(adapter, message, uid, session, guard):
    from dataclasses import replace
    from database import chat

    artifacts = list(message.media)
    text = message.text
    for attachment in message.attachments:
        await guard()
        if attachment.size < 0 or attachment.size > MAX_MEDIA_BYTES:
            raise ValueError('Media too large')
        data = await adapter.download(attachment)
        await guard()
        if attachment.voice:
            transcript = await run_blocking(storage_executor, adapter.media.transcribe, data)
            if not transcript:
                raise ValueError('Voice transcription empty')
            text += '\n' + transcript
        else:
            artifact = await run_blocking(storage_executor, adapter.media.ingest, uid, attachment, data)
            await guard()
            artifacts.append(artifact)
    if artifacts:
        await run_blocking(
            db_executor, chat.add_files_to_chat_session, uid, session['id'], [a.file_store_ref for a in artifacts]
        )
    return replace(message, text=text, media=tuple(artifacts), attachments=())
