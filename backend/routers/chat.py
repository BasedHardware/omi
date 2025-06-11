import uuid
import re
import base64
import os
import tempfile
from datetime import datetime, timezone, timedelta, time
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from multipart.multipart import shutil

import database.chat as chat_db
import database.conversations as conversations_db
from database.apps import record_app_usage
from models.app import App, UsageHistoryType
from models.chat import ChatSession, Message, SendMessageRequest, MessageSender, ResponseMessage, MessageConversation, \
    FileChat, MessageType
from models.conversation import Conversation
from routers.sync import retrieve_file_paths, decode_files_to_wav
from utils.apps import get_available_app_by_id
from utils.chat import process_voice_message_segment, process_voice_message_segment_stream, \
    transcribe_voice_message_segment
from utils.llm.persona import initial_persona_chat_message
from utils.llm.chat import initial_chat_message
from utils.other import endpoints as auth, storage
from utils.other.chat_file import FileChatTool
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream, execute_persona_chat_stream

router = APIRouter()



fc = FileChatTool()


def filter_messages(messages, plugin_id):
    collected = []
    for message in messages:
        if message.sender == MessageSender.ai and message.plugin_id != plugin_id:
            break
        collected.append(message)
    return collected


def acquire_chat_session(uid: str, plugin_id: Optional[str] = None):
    chat_session = chat_db.get_chat_session(uid, app_id=plugin_id)
    if chat_session is None:
        cs = ChatSession(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            plugin_id=plugin_id
        )
        chat_session = chat_db.add_chat_session(uid, cs.dict())
    return chat_session


@router.post('/v2/messages', tags=['chat'], response_model=ResponseMessage)
def send_message(
        data: SendMessageRequest, plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    if plugin_id in ['null', '']:
        plugin_id = None

    # get chat session
    chat_session = chat_db.get_chat_session(uid, app_id=plugin_id)
    chat_session = ChatSession(**chat_session) if chat_session else None

    message = Message(
        id=str(uuid.uuid4()), text=data.text, created_at=datetime.now(timezone.utc), sender='human', type='text',
        plugin_id=plugin_id
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

    app = get_available_app_by_id(plugin_id, uid)
    app = App(**app) if app else None

    app_id = app.id if app else None

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10, app_id=plugin_id)]))

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)

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

        ai_message = Message(
            id=str(uuid.uuid4()),
            text=response,
            created_at=datetime.now(timezone.utc),
            sender='ai',
            plugin_id=app_id,
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

        return ai_message, ask_for_nps

    async def generate_stream():
        callback_data = {}
        async for chunk in execute_graph_chat_stream(uid, messages, app, cited=True, callback_data=callback_data,
                                                     chat_session=chat_session):
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
                    data = base64.b64encode(bytes(response_message.model_dump_json(), 'utf-8')).decode('utf-8')
                    yield f"done: {data}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


@router.post('/v2/messages/{message_id}/report', tags=['chat'], response_model=dict)
def report_message(
        message_id: str, uid: str = Depends(auth.get_current_user_uid)
):
    message, msg_doc_id = chat_db.get_message(uid, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Message not found')
    if message.sender != 'ai':
        raise HTTPException(status_code=400, detail='Only AI messages can be reported')
    if message.reported:
        raise HTTPException(status_code=400, detail='Message already reported')
    chat_db.report_message(uid, msg_doc_id)
    return {'message': 'Message reported'}


@router.delete('/v2/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(app_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    if app_id in ['null', '']:
        app_id = None

    # get current chat session
    chat_session = chat_db.get_chat_session(uid, app_id=app_id)
    chat_session_id = chat_session['id'] if chat_session else None

    err = chat_db.clear_chat(uid, app_id=app_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # clean thread chat file
    fc_tool = FileChatTool()
    fc_tool.cleanup(uid)

    # clear session
    if chat_session_id is not None:
        chat_db.delete_chat_session(uid, chat_session_id)

    return initial_message_util(uid, app_id)


def initial_message_util(uid: str, app_id: Optional[str] = None):
    # get current chat session
    chat_session = chat_db.get_chat_session(uid, app_id=app_id)
    # get prev messages
    prev_messages = chat_db.get_messages(uid, app_id=app_id, limit=10) if chat_session else []
    prev_messages_str = Message.get_messages_as_string(prev_messages[:5])

    # load app
    app = get_available_app_by_id(app_id) if app_id else None

    text = ''
    if app:
        text = initial_persona_chat_message(prev_messages_str, app.prompt)
    else:
        text = initial_chat_message(prev_messages_str)

    message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender='ai',
        plugin_id=app_id,
        from_external_integration=False,
        type='text',
        memories_id=[],
    )

    # save message to the database
    chat_db.add_message(uid, message.dict(), app_id=app_id)
    return message


@router.post('/v2/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(app_id: Optional[str], uid: str = Depends(auth.get_current_user_uid)):
    return initial_message_util(uid, app_id)


@router.get('/v2/messages', response_model=List[Message], tags=['chat'])
def get_messages(plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    if plugin_id in ['null', '']:
        plugin_id = None

    messages = chat_db.get_messages(uid, app_id=plugin_id, limit=40)
    return messages


@router.post("/v2/voice-messages")
async def create_voice_message_stream(files: List[UploadFile] = File(...),
                                      uid: str = Depends(auth.get_current_user_uid)):
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

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


@router.post("/v2/voice-message/transcribe")
async def transcribe_voice_message(files: List[UploadFile] = File(...),
                                   uid: str = Depends(auth.get_current_user_uid)):
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


@router.post('/v2/files', tags=['chat'])
def upload_file_chat(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    """
    Handle regular chat file uploads.
    
    Note: For OpenGlass images, use the dedicated /openglass/v1/images endpoint instead.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Check for OpenGlass files and redirect appropriately
    openglass_files = [
        file.filename for file in files 
        if file.filename and 'openglass' in file.filename.lower()
    ]
    
    if openglass_files:
        raise HTTPException(
            status_code=400, 
            detail=f"OpenGlass files detected: {openglass_files}. Please use /openglass/v1/images endpoint for OpenGlass image uploads."
        )
    
    # Process regular files using the existing FileChatTool workflow
    processed_files = []
    
    for file in files:
        try:
            # Create temp file with original extension
            file_ext = os.path.splitext(file.filename)[1] if file.filename else ''
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            temp_path = temp_file.name
            
            # Save uploaded file to temp path
            with open(temp_path, 'wb') as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Use FileChatTool to upload to OpenAI and get file info
            file_info = fc.upload(temp_path)
            
            # Add additional info needed for the response
            file_info.update({
                'id': str(uuid.uuid4()),
                'name': file.filename or 'unknown',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'deleted': False,
            })
            
            processed_files.append(file_info)
            
            # Clean up temp file
            os.unlink(temp_path)
            
        except Exception as e:
            print(f"Error processing file {file.filename}: {e}")
            continue
    
    if not processed_files:
        raise HTTPException(status_code=500, detail="Failed to process any files")
    
    return processed_files



