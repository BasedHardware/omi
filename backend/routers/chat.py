import uuid
import re
import base64
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
import os
from fastapi.responses import StreamingResponse
import shutil

import database.chat as chat_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import (
    ChatSession,
    Message,
    SendMessageRequest,
    MessageSender,
    ResponseMessage,
    MessageConversation,
    FileChat,
)
from models.conversation import Conversation
from routers.sync import retrieve_file_paths, decode_files_to_wav
from utils.apps import get_available_app_by_id
from typing import Dict
from utils.chat import (
    process_voice_message_segment,
    process_voice_message_segment_stream,
    transcribe_voice_message_segment,
    acquire_chat_session,
)
from utils.llm.chat import generate_session_title
from utils.other import endpoints as auth, storage
from utils.other.chat_file import FileChatTool
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream, execute_persona_chat_stream
import database.conversations as conversations_db

router = APIRouter()
fc = FileChatTool()
# ----------------- Multi-session endpoints -----------------


@router.get('/v2/chat-sessions', tags=['chat'])
def list_chat_sessions(
    app_id: Optional[str] = None,
    plugin_id: Optional[str] = None,
    limit: int = 20,
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = app_id or plugin_id
    sessions = chat_db.list_chat_sessions(uid, app_id=compat_app_id, limit=limit)
    return sessions


@router.get('/v2/chat-sessions/{chat_session_id}', tags=['chat'])
def get_chat_session_by_id(chat_session_id: str, uid: str = Depends(auth.get_current_user_uid)):
    session = chat_db.get_chat_session_by_id(uid, chat_session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Chat session not found')
        chat_db.touch_chat_session(uid, chat_session_id)
    return session


@router.delete('/v2/chat-sessions/{chat_session_id}', tags=['chat'])
def delete_chat_session_by_id(chat_session_id: str, uid: str = Depends(auth.get_current_user_uid)):
    # clear messages in this session then delete session
    err = chat_db.clear_chat(uid, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')
    chat_db.delete_chat_session(uid, chat_session_id)
    return {"ok": True}


@router.post('/v2/messages', tags=['chat'], response_model=ResponseMessage)
def send_message(
    data: SendMessageRequest,
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = app_id or plugin_id
    dr = data.context.date_range if data.context else None
    conversation_ids = (data.context.conversation_ids or []) if data.context else []
    client_date_range_dict = {'start': dr.start, 'end': dr.end} if (dr and dr.start and dr.end) else {}

    # resolve or acquire session
    chat_session = acquire_chat_session(uid, app_id=compat_app_id, chat_session_id=chat_session_id)

    message = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=datetime.now(timezone.utc),
        sender='human',
        type='text',
        app_id=compat_app_id,
    )
    if data.file_ids is not None:
        # Session-first file handling
        new_file_ids = chat_session.retrieve_new_file(data.file_ids)
        chat_session.add_file_ids(data.file_ids)
        chat_db.add_files_to_chat_session(uid, chat_session.id, data.file_ids)

        if len(new_file_ids) > 0:
            message.files_id = new_file_ids
            files = chat_db.get_chat_files(uid, new_file_ids)
            files = [FileChat(**f) if f else None for f in files]
            message.files = files
            fc.add_files(new_file_ids)

    message.chat_session_id = chat_session.id
    chat_db.add_message_to_chat_session(uid, chat_session.id, message.id)
    chat_db.touch_chat_session(uid, chat_session.id)

    chat_db.add_message(uid, message.dict())

    app_data = get_available_app_by_id(compat_app_id, uid) if compat_app_id else None
    app = App(**app_data) if app_data else None

    app_id_from_app = app.id if app else None

    messages = list(
        reversed(
            [
                Message(**msg)
                for msg in chat_db.get_messages(
                    uid,
                    limit=10,
                    chat_session_id=chat_session.id,
                )
            ]
        )
    )

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)

        is_pinned = bool(conversation_ids)  # scoped to specific conversation(s)

        memories_id = []
        converted_memories = []
        if memories and not is_pinned:
            for m in memories[:5]:
                if isinstance(m, dict):
                    converted_memories.append(Conversation(**m))
                else:
                    converted_memories.append(m)
            memories_id = [m.id for m in converted_memories]

        ai_message = Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            app_id=app_id_from_app,
            type='text',
            memories_id=memories_id,
        )

        ai_message.chat_session_id = chat_session.id
        chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)
        chat_db.touch_chat_session(uid, chat_session.id)

        chat_db.add_message(uid, ai_message.dict())
        # Attach memories for chips from retrieved list only when not pinned/scoped
        ai_message.memories = (
            []
            if is_pinned
            else [
                MessageConversation(**m) if isinstance(m, dict) else m  # m should already be dicts from DB
                for m in (memories if len(memories) < 5 else memories[:5])
            ]
        )
        if app_id:
            record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

        return ai_message, ask_for_nps

    async def generate_stream():
        # Attach client overrides to callback_data for downstream logging visibility
        callback_data = {
            'client_date_range': client_date_range_dict,
        }
        async for chunk in execute_graph_chat_stream(
            uid,
            messages,
            app,
            cited=False,
            callback_data=callback_data,
            chat_session=chat_session,
            client_date_range=client_date_range_dict,
            selected_memory_ids=conversation_ids,
        ):
            if chunk:
                msg = chunk.replace("\n", "__CRLF__")
                yield f'{msg}\n\n'
            else:
                response = callback_data.get('answer')
                if response:
                    ai_message, ask_for_nps = process_message(response, callback_data)
                    ai_message_dict = ai_message.dict()
                    response_message = ResponseMessage(**ai_message_dict)
                    response_message.ask_for_nps = ask_for_nps
                    try:
                        if 'citations' in callback_data:
                            response_message.citations = callback_data.get('citations')
                    except Exception:
                        pass
                    # Preserve markdown; avoid any cleanup that could alter formatting

                    data = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
                    yield f"done: {data}\n\n"

    # Auto-generate title for new sessions based on first user message
    try:
        if chat_session and (getattr(chat_session, 'title', None) in [None, '', 'New Chat']):
            # Only consider first human message in session
            session_msgs = chat_db.get_messages(uid, limit=10, chat_session_id=chat_session.id)
            human_msgs = [m for m in session_msgs if m.get('sender') == 'human']
            if len(human_msgs) <= 1 and data.text and len(data.text.strip()) > 5:
                new_title = generate_session_title(data.text)
                if new_title:
                    chat_db.update_chat_session_title(uid, chat_session.id, new_title)
    except Exception as e:
        print(f"Failed to auto-title session {chat_session.id if chat_session else ''}: {e}")

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.post('/v2/messages/{message_id}/report', tags=['chat'], response_model=dict)
def report_message(message_id: str, uid: str = Depends(auth.get_current_user_uid)):
    message, msg_doc_id = chat_db.get_message(uid, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Message not found')
    if message.sender != 'ai':
        raise HTTPException(status_code=400, detail='Only AI messages can be reported')
    if message.reported:
        raise HTTPException(status_code=400, detail='Message already reported')
    chat_db.report_message(uid, msg_doc_id)
    return {'message': 'Message reported'}


@router.delete('/v2/messages', tags=['chat'])
def clear_chat_messages(
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):

    err = chat_db.clear_chat(uid, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # clean thread chat file
    fc_tool = FileChatTool()
    fc_tool.cleanup(uid)

    if chat_session_id is not None:
        chat_db.delete_chat_session(uid, chat_session_id)

    return StreamingResponse(iter(()), status_code=204)


@router.get('/v2/messages', response_model=List[Message], tags=['chat'])
def get_messages(
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):

    messages = chat_db.get_messages(
        uid,
        limit=10,
        include_conversations=True,
        chat_session_id=chat_session_id,
    )

    print('get_messages', len(messages), chat_session_id)
    return messages


@router.post("/v2/voice-messages")
async def create_voice_message_stream(
    files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)
):
    # wav
    paths = retrieve_file_paths(files, uid)
    if len(paths) == 0:
        raise HTTPException(status_code=400, detail='Paths is invalid')

    wav_paths = decode_files_to_wav(paths)
    if len(wav_paths) == 0:
        raise HTTPException(status_code=400, detail='Wav path is invalid')

    # process
    async def generate_stream():
        async for chunk in process_voice_message_segment_stream(list(wav_paths)[0], uid):
            yield chunk

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.post("/v2/voice-message/transcribe")
async def transcribe_voice_message(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    # Check if files are empty
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail='No files provided')

    wav_paths = []
    other_file_paths = []

    # Process all files in a single loop
    for file in files:
        if file.filename.lower().endswith('.wav'):
            # For WAV files, save directly to a temporary path
            temp_path = f"/tmp/{uid}_{uuid.uuid4()}.wav"
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            wav_paths.append(temp_path)
        else:
            # For other files, collect paths for later conversion
            path = retrieve_file_paths([file], uid)
            if path:
                other_file_paths.extend(path)

    # Convert other files to WAV if needed
    if other_file_paths:
        converted_wav_paths = decode_files_to_wav(other_file_paths)
        if converted_wav_paths:
            wav_paths.extend(converted_wav_paths)

    # Process all WAV files
    for wav_path in wav_paths:
        transcript = transcribe_voice_message_segment(wav_path)

        # Clean up temporary WAV files created directly
        if wav_path.startswith(f"/tmp/{uid}_"):
            try:
                Path(wav_path).unlink()
            except:
                pass

        # If we got a transcript, return it
        if transcript:
            return {"transcript": transcript}

    # If we got here, no transcript was produced
    raise HTTPException(status_code=400, detail='Failed to transcribe audio')


@router.post('/v2/files', response_model=List[FileChat], tags=['chat'])
def upload_file_chat(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    thumbs_name = []
    files_chat = []
    for file in files:
        temp_file = Path(f"{file.filename}")
        with temp_file.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        fc_tool = FileChatTool()
        result = fc_tool.upload(temp_file)

        thumb_name = result.get("thumbnail_name", "")
        if thumb_name != "":
            thumbs_name.append(thumb_name)

        filechat = FileChat(
            id=str(uuid.uuid4()),
            name=result.get("file_name", ""),
            mime_type=result.get("mime_type", ""),
            openai_file_id=result.get("file_id", ""),
            created_at=datetime.now(timezone.utc),
            thumb_name=thumb_name,
        )
        files_chat.append(filechat)

        # cleanup temp_file
        temp_file.unlink()

    if len(thumbs_name) > 0:
        thumbs_path = storage.upload_multi_chat_files(thumbs_name, uid)
        for fc in files_chat:
            if not fc.is_image():
                continue
            thumb_path = thumbs_path.get(fc.thumb_name, "")
            fc.thumbnail = thumb_path
            # cleanup file thumb
            thumb_file = Path(fc.thumb_name)
            thumb_file.unlink()

    # save db
    files_chat_dict = [fc.dict() for fc in files_chat]

    chat_db.add_multi_files(uid, files_chat_dict)

    response = [fc.dict() for fc in files_chat]

    return response


# CLEANUP: Remove after new app goes to prod ----------------------------------------------------------


@router.post('/v1/files', response_model=List[FileChat], tags=['chat'])
def upload_file_chat(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    thumbs_name = []
    files_chat = []
    for file in files:
        temp_file = Path(f"{file.filename}")
        with temp_file.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        fc_tool = FileChatTool()
        result = fc_tool.upload(temp_file)

        thumb_name = result.get("thumbnail_name", "")
        if thumb_name != "":
            thumbs_name.append(thumb_name)

        filechat = FileChat(
            id=str(uuid.uuid4()),
            name=result.get("file_name", ""),
            mime_type=result.get("mime_type", ""),
            openai_file_id=result.get("file_id", ""),
            created_at=datetime.now(timezone.utc),
            thumb_name=thumb_name,
        )
        files_chat.append(filechat)

        # cleanup temp_file
        temp_file.unlink()

    if len(thumbs_name) > 0:
        thumbs_path = storage.upload_multi_chat_files(thumbs_name, uid)
        for fc in files_chat:
            if not fc.is_image():
                continue
            thumb_path = thumbs_path.get(fc.thumb_name, "")
            fc.thumbnail = thumb_path
            # cleanup file thumb
            thumb_file = Path(fc.thumb_name)
            thumb_file.unlink()

    # save db
    files_chat_dict = [fc.dict() for fc in files_chat]

    chat_db.add_multi_files(uid, files_chat_dict)

    response = [fc.dict() for fc in files_chat]

    return response


@router.post('/v1/messages/{message_id}/report', tags=['chat'], response_model=dict)
def report_message(message_id: str, uid: str = Depends(auth.get_current_user_uid)):
    message, msg_doc_id = chat_db.get_message(uid, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Message not found')
    if message.sender != 'ai':
        raise HTTPException(status_code=400, detail='Only AI messages can be reported')
    if message.reported:
        raise HTTPException(status_code=400, detail='Message already reported')
    chat_db.report_message(uid, msg_doc_id)
    return {'message': 'Message reported'}


@router.delete('/v1/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(
    plugin_id: Optional[str] = None, app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    compat_app_id = app_id or plugin_id
    if compat_app_id in ['null', '']:
        compat_app_id = None

    # get current chat session
    chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
    chat_session_id = chat_session['id'] if chat_session else None

    err = chat_db.clear_chat(uid, app_id=compat_app_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # clean thread chat file
    fc_tool = FileChatTool()
    fc_tool.cleanup(uid)

    # clear session
    if chat_session_id is not None:
        chat_db.delete_chat_session(uid, chat_session_id)

    return


@router.post("/v1/voice-message/transcribe")
async def transcribe_voice_message(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    # Check if files are empty
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail='No files provided')

    wav_paths = []
    other_file_paths = []

    # Process all files in a single loop
    for file in files:
        if file.filename.lower().endswith('.wav'):
            # For WAV files, save directly to a temporary path
            temp_path = f"/tmp/{uid}_{uuid.uuid4()}.wav"
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            wav_paths.append(temp_path)
        else:
            # For other files, collect paths for later conversion
            path = retrieve_file_paths([file], uid)
            if path:
                other_file_paths.extend(path)

    # Convert other files to WAV if needed
    if other_file_paths:
        converted_wav_paths = decode_files_to_wav(other_file_paths)
        if converted_wav_paths:
            wav_paths.extend(converted_wav_paths)

    # Process all WAV files
    for wav_path in wav_paths:
        transcript = transcribe_voice_message_segment(wav_path)

        # Clean up temporary WAV files created directly
        if wav_path.startswith(f"/tmp/{uid}_"):
            try:
                Path(wav_path).unlink()
            except:
                pass

        # If we got a transcript, return it
        if transcript:
            return {"transcript": transcript}

    # If we got here, no transcript was produced
    raise HTTPException(status_code=400, detail='Failed to transcribe audio')
