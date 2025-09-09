import uuid
import re
import base64
import threading
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from multipart.multipart import shutil

import database.chat as chat_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import (
    ChatSession,
    Message,
    SendMessageRequest,
    CreateSessionRequest,
    GenerateTitleRequest,
    MessageSender,
    ResponseMessage,
    WebSearchCitation,
    MessageConversation,
    FileChat,
)
from models.conversation import Conversation
from routers.sync import retrieve_file_paths, decode_files_to_wav
from utils.apps import get_available_app_by_id
from utils.chat import (
    process_voice_message_segment,
    process_voice_message_segment_stream,
    transcribe_voice_message_segment,
)
from utils.llm.persona import initial_persona_chat_message
from utils.llm.chat import initial_chat_message
from utils.llm.title_generation import generate_thread_title
from utils.llm.chat_processing import process_chat_message_for_insights
from utils.other import endpoints as auth, storage
from utils.other.chat_file import FileChatTool
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream, execute_persona_chat_stream

router = APIRouter()
fc = FileChatTool()


def normalize_app_id(app_id: Optional[str], plugin_id: Optional[str]) -> str:
    """Normalize app_id/plugin_id, converting null/empty values to 'omi' for consistent data model."""
    compat_app_id = app_id or plugin_id

    # For OMI app, use consistent 'omi' identifier instead of null
    if compat_app_id is None or compat_app_id in ['null', '', 'undefined']:
        return 'omi'

    return compat_app_id


def filter_messages(messages, app_id):
    print('filter_messages', len(messages), app_id)
    collected = []
    for message in messages:
        if message.sender == MessageSender.ai and message.plugin_id != app_id:
            break
        collected.append(message)
    print('filter_messages output:', len(collected))
    return collected


def acquire_chat_session(uid: str, app_id: Optional[str] = None):
    chat_session = chat_db.get_chat_session(uid, app_id=app_id)
    if chat_session is None:
        cs = ChatSession(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), plugin_id=app_id)
        chat_session = chat_db.add_chat_session(uid, cs.dict())
    return chat_session


@router.post('/v2/messages', tags=['chat'], response_model=ResponseMessage)
def send_message(
    data: SendMessageRequest,
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = normalize_app_id(app_id, plugin_id)
    print('send_message', data.text, compat_app_id, uid)

    # get chat session - use specific session if provided, otherwise get/create default for app
    if chat_session_id:
        chat_session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail='Chat session not found')
    else:
        chat_session = acquire_chat_session(uid, compat_app_id)

    chat_session = ChatSession(**chat_session) if chat_session else None

    message = Message(
        id=str(uuid.uuid4()),
        text=data.text,
        created_at=datetime.now(timezone.utc),
        sender='human',
        type='text',
        app_id=compat_app_id,
    )
    if data.file_ids is not None:
        new_file_ids = fc.retrieve_new_file(data.file_ids)
        if chat_session:
            new_file_ids = chat_session.retrieve_new_file(data.file_ids)
            chat_session.add_file_ids(data.file_ids)
            chat_db.add_files_to_chat_session(uid, chat_session.id, data.file_ids)

        if len(new_file_ids) > 0:
            message.files_id = new_file_ids
            files = chat_db.get_chat_files(uid, new_file_ids)
            files = [FileChat(**f) if f else None for f in files]
            message.files = files
            fc.add_files(new_file_ids)

    if chat_session:
        message.chat_session_id = chat_session.id
        chat_db.add_message_to_chat_session(uid, chat_session.id, message.id)

    chat_db.add_message(uid, message.dict())

    # Process human message for insights (memories/todos) - non-blocking
    if message.sender == MessageSender.human:
        print(f"🧠 Starting insights processing for human message: {message.id}")
        threading.Thread(target=process_chat_message_for_insights, args=(uid, message, compat_app_id)).start()

    # For OMI app (compat_app_id is None), skip app lookup since OMI doesn't have an app record
    if compat_app_id is not None:
        app = get_available_app_by_id(compat_app_id, uid)
        app = App(**app) if app else None
    else:
        app = None  # OMI app - no app record needed

    app_id_from_app = app.id if app else None

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10, app_id=compat_app_id)]))

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)
        web_citations = callback_data.get('web_search_citations', [])

        # cited extraction
        cited_conversation_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
        if len(cited_conversation_idxs) > 0:
            response = re.sub(r'\[\d+\]', '', response)
        memories = [memories[i - 1] for i in cited_conversation_idxs if 0 < i and i <= len(memories)]

        memories_id = []
        # check if the items in the conversations list are dict
        if memories:
            converted_memories = []
            for m in memories[:5]:
                if isinstance(m, dict):
                    converted_memories.append(Conversation(**m))
                else:
                    converted_memories.append(m)
            memories_id = [m.id for m in converted_memories]

        # Create base AI message
        ai_message = Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            app_id=compat_app_id,
            type='text',
            memories_id=memories_id,
        )
        if chat_session:
            ai_message.chat_session_id = chat_session.id
            chat_db.add_message_to_chat_session(uid, chat_session.id, ai_message.id)

        chat_db.add_message(uid, ai_message.dict())
        ai_message.memories = [MessageConversation(**m) for m in (memories if len(memories) < 5 else memories[:5])]
        if app_id:
            record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

        # Create ResponseMessage with structured citations
        response_message = ResponseMessage(
            **ai_message.dict(),
            ask_for_nps=ask_for_nps,
            web_search_citations=[WebSearchCitation(**citation) for citation in web_citations] if web_citations else [],
        )

        return response_message, ask_for_nps

    async def generate_stream():
        callback_data = {}
        async for chunk in execute_graph_chat_stream(
            uid,
            messages,
            app,
            cited=True,
            callback_data=callback_data,
            chat_session=chat_session,
            web_search_enabled=data.web_search_enabled,
        ):
            if chunk:
                msg = chunk.replace("\n", "__CRLF__")
                yield f'{msg}\n\n'
            else:
                response = callback_data.get('answer')
                if response:
                    response_message, ask_for_nps = process_message(response, callback_data)
                    # response_message is already a ResponseMessage with citations included
                    encoded_data = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
                    yield f"done: {encoded_data}\n\n"

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
    app_id: Optional[str] = None,
    plugin_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = normalize_app_id(app_id, plugin_id)
    # get current chat session - use specific session if provided, otherwise get default for app
    if chat_session_id:
        chat_session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail='Chat session not found')
    else:
        chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
        chat_session_id = chat_session['id'] if chat_session else None

    err = chat_db.clear_chat(uid, app_id=compat_app_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # Note: Keep the session/thread alive - only messages are cleared

    # clean thread chat file in background to avoid blocking response
    import threading

    def cleanup_in_background():
        try:
            fc_tool = FileChatTool()
            fc_tool.cleanup(uid)
        except Exception as e:
            print(f"Background cleanup error: {str(e)}")

    threading.Thread(target=cleanup_in_background, daemon=True).start()

    return {
        "status": "success",
        "message": "Messages cleared successfully",
        "cleared": {
            "app_id": compat_app_id,
            "chat_session_id": chat_session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def initial_message_util(uid: str, app_id: Optional[str] = None, target_chat_session_id: Optional[str] = None):
    print('initial_message_util', app_id, target_chat_session_id)

    # init chat session - use specific session if provided
    if target_chat_session_id:
        # Recreate the cleared session with the same ID
        cs = ChatSession(id=target_chat_session_id, created_at=datetime.now(timezone.utc), plugin_id=app_id)
        chat_session = chat_db.add_chat_session(uid, cs.dict())
        # For a cleared session, start fresh (no previous messages)
        prev_messages = []
        print('initial_message_util recreated session', target_chat_session_id, 'for', app_id)
    else:
        # Get/create default session
        chat_session = acquire_chat_session(uid, app_id=app_id)
        # Get messages from the specific session only
        prev_messages = list(
            reversed(chat_db.get_messages(uid, limit=5, app_id=app_id, chat_session_id=chat_session['id']))
        )
        print('initial_message_util returned', len(prev_messages), 'prev messages for', app_id)

    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None

    # persona
    text: str
    if app and app.is_a_persona():
        text = initial_persona_chat_message(uid, app, prev_messages)
    else:
        prev_messages_str = ''
        if prev_messages:
            prev_messages_str = 'Previous conversation history:\n'
            prev_messages_str += Message.get_messages_as_string([Message(**msg) for msg in prev_messages])
        print('initial_message_util', len(prev_messages_str), app_id)
        text = initial_chat_message(uid, app, prev_messages_str)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        app_id=app_id,
        from_external_integration=False,
        type='text',
        memories_id=[],
        chat_session_id=chat_session['id'],
    )
    chat_db.add_message(uid, ai_message.dict())
    chat_db.add_message_to_chat_session(uid, chat_session['id'], ai_message.id)
    return ai_message


@router.post('/v2/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(
    app_id: Optional[str] = None, plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    compat_app_id = normalize_app_id(app_id, plugin_id)
    return initial_message_util(uid, compat_app_id, None)


@router.get('/v2/messages', response_model=List[Message], tags=['chat'])
def get_messages(
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = normalize_app_id(app_id, plugin_id)
    # Use specific session if provided, otherwise get default for app
    if chat_session_id:
        chat_session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail='Chat session not found')
        actual_chat_session_id = chat_session_id
    else:
        chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
        actual_chat_session_id = chat_session['id'] if chat_session else None

    messages = chat_db.get_messages(
        uid, limit=100, include_conversations=True, app_id=compat_app_id, chat_session_id=actual_chat_session_id
    )
    print('get_messages', len(messages), compat_app_id)
    return messages


# **************************************
# ********** CHAT SESSIONS *************
# **************************************


@router.get('/v2/chat-sessions', response_model=List[ChatSession], tags=['chat'])
def list_chat_sessions(app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    """List all chat sessions for a specific app or all sessions if app_id is None."""
    sessions = chat_db.get_chat_sessions(uid, app_id)
    return [ChatSession(**session) for session in sessions]


@router.post('/v2/chat-sessions', response_model=ChatSession, tags=['chat'])
def create_chat_session(data: CreateSessionRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new chat session for a specific app."""
    session = chat_db.create_chat_session(uid, data.app_id, data.title)
    return ChatSession(**session)


@router.delete('/v2/chat-sessions/{session_id}', tags=['chat'])
def delete_chat_session(session_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Delete a specific chat session."""
    # Verify session exists and belongs to user
    session = chat_db.get_chat_session_by_id(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Chat session not found')

    # Delete the session
    chat_db.delete_chat_session(uid, session_id)
    return {"status": "ok"}


@router.post('/v2/chat-sessions/{session_id}/generate-title', tags=['chat'])
def generate_chat_session_title(
    session_id: str, data: GenerateTitleRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Generate a title for a chat session based on the first message."""
    # Verify session exists and belongs to user
    session = chat_db.get_chat_session_by_id(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Chat session not found')

    # Generate title using LLM
    try:
        generated_title = generate_thread_title(data.first_message)

        # Update the session with the new title
        success = chat_db.update_chat_session_title(uid, session_id, generated_title)
        if not success:
            raise HTTPException(status_code=500, detail='Failed to update session title')

        return {"title": generated_title, "status": "success"}

    except Exception as e:
        print(f"Error generating title: {e}")
        raise HTTPException(status_code=500, detail='Failed to generate title')


@router.post('/v2/messages/{message_id}/process-insights', tags=['chat'])
def process_message_for_insights(
    message_id: str, app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Process a chat message through memories/todos/trends extraction pipeline.
    Only processes human messages for insights generation.
    """
    try:
        # Get the message from database
        result = chat_db.get_message(uid, message_id)
        if not result:
            raise HTTPException(status_code=404, detail='Message not found')

        message_obj, doc_id = result

        # Process through insights pipeline (async - doesn't block response)
        threading.Thread(target=process_chat_message_for_insights, args=(uid, message_obj, app_id)).start()

        return {"status": "processing", "message": "Insights extraction started"}

    except Exception as e:
        print(f"Error starting message insights processing: {e}")
        raise HTTPException(status_code=500, detail='Failed to start insights processing')


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


@router.delete('/v1/messages', tags=['chat'])
def clear_chat_messages(
    plugin_id: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
):
    compat_app_id = normalize_app_id(app_id, plugin_id)
    # get current chat session - use specific session if provided, otherwise get default for app
    if chat_session_id:
        chat_session = chat_db.get_chat_session_by_id(uid, chat_session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail='Chat session not found')
    else:
        chat_session = chat_db.get_chat_session(uid, app_id=compat_app_id)
        chat_session_id = chat_session['id'] if chat_session else None

    err = chat_db.clear_chat(uid, app_id=compat_app_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # Note: Keep the session/thread alive - only messages are cleared

    # clean thread chat file in background to avoid blocking response
    import threading

    def cleanup_in_background():
        try:
            fc_tool = FileChatTool()
            fc_tool.cleanup(uid)
        except Exception as e:
            print(f"Background cleanup error: {str(e)}")

    threading.Thread(target=cleanup_in_background, daemon=True).start()

    return {
        "status": "success",
        "message": "Messages cleared successfully",
        "cleared": {
            "app_id": compat_app_id,
            "chat_session_id": chat_session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


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


@router.post('/v1/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(
    plugin_id: Optional[str] = None, app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    compat_app_id = normalize_app_id(app_id, plugin_id)
    return initial_message_util(uid, compat_app_id, None)
