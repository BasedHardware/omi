import uuid
import re
import base64
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from multipart.multipart import shutil

import database.chat as chat_db
from database.apps import record_app_usage
from models.app import App
from models.chat import ChatSession, Message, SendMessageRequest, MessageSender, ResponseMessage, MessageMemory, \
    FileChat
from models.memory import Memory
from models.plugin import UsageHistoryType
from routers.sync import retrieve_file_paths, decode_files_to_wav, retrieve_vad_segments
from utils.apps import get_available_app_by_id
from utils.chat import process_voice_message_segment, process_voice_message_segment_stream, transcribe_voice_message_segment
from utils.llm import initial_chat_message, initial_persona_chat_message
from utils.other import endpoints as auth, storage
from utils.other.chat_file import FileChatTool
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream, execute_persona_chat_stream

router = APIRouter()
fc = FileChatTool()


def filter_messages(messages, plugin_id):
    print('filter_messages', len(messages), plugin_id)
    collected = []
    for message in messages:
        if message.sender == MessageSender.ai and message.plugin_id != plugin_id:
            break
        collected.append(message)
    print('filter_messages output:', len(collected))
    return collected


def acquire_chat_session(uid: str, plugin_id: Optional[str] = None):
    chat_session = chat_db.get_chat_session(uid, plugin_id=plugin_id)
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
    print('send_message', data.text, plugin_id, uid)

    if plugin_id in ['null', '']:
        plugin_id = None

    # get chat session
    chat_session = chat_db.get_chat_session(uid, plugin_id=plugin_id)
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

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10, plugin_id=plugin_id)]))

    def process_message(response: str, callback_data: dict):
        memories = callback_data.get('memories_found', [])
        ask_for_nps = callback_data.get('ask_for_nps', False)

        # cited extraction
        cited_memory_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
        if len(cited_memory_idxs) > 0:
            response = re.sub(r'\[\d+\]', '', response)
        memories = [memories[i - 1] for i in cited_memory_idxs if 0 < i and i <= len(memories)]

        memories_id = []
        # check if the items in the memories list are dict
        if memories:
            converted_memories = []
            for m in memories[:5]:
                if isinstance(m, dict):
                    converted_memories.append(Memory(**m))
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
        ai_message.memories = [MessageMemory(**m) for m in (memories if len(memories) < 5 else memories[:5])]
        if app_id:
            record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

        return ai_message, ask_for_nps

    async def generate_stream():
        callback_data = {}
        async for chunk in execute_graph_chat_stream(uid, messages, app, cited=True, callback_data=callback_data, chat_session=chat_session):
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


@router.post('/v1/messages/{message_id}/report', tags=['chat'], response_model=dict)
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

@router.post('/v1/messages', tags=['chat'], response_model=ResponseMessage)
def send_message_v1(
        data: SendMessageRequest, plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    print('send_message', data.text, plugin_id, uid)

    if plugin_id in ['null', '']:
        plugin_id = None

    message = Message(
        id=str(uuid.uuid4()), text=data.text, created_at=datetime.now(timezone.utc), sender='human', type='text',
        plugin_id=plugin_id,
    )

    chat_db.add_message(uid, message.dict())

    app = get_available_app_by_id(plugin_id, uid)
    app = App(**app) if app else None

    app_id = app.id if app else None

    messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10, plugin_id=plugin_id)]))

    response, ask_for_nps, memories = execute_graph_chat(uid, messages, app, cited=True)  # plugin

    # cited extraction
    cited_memory_idxs = {int(i) for i in re.findall(r'\[(\d+)\]', response)}
    if len(cited_memory_idxs) > 0:
        response = re.sub(r'\[\d+\]', '', response)
    memories = [memories[i - 1] for i in cited_memory_idxs if 0 < i and i <= len(memories)]

    memories_id = []
    # check if the items in the memories list are dict
    if memories:
        converted_memories = []
        for m in memories[:5]:
            if isinstance(m, dict):
                converted_memories.append(Memory(**m))
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

    chat_db.add_message(uid, ai_message.dict())
    ai_message.memories = memories if len(memories) < 5 else memories[:5]
    if app_id:
        record_app_usage(uid, app_id, UsageHistoryType.chat_message_sent, message_id=ai_message.id)

    resp = ai_message.dict()
    resp['ask_for_nps'] = ask_for_nps
    return resp


@router.post('/v1/messages/upload', tags=['chat'], response_model=ResponseMessage)
async def send_message_with_file(
        file: UploadFile = File(...), plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    print('send_message_with_file', file.filename, plugin_id, uid)
    content = await file.read()
    # TODO: steps
    # - File should be uploaded to cloud storage
    # - File content should be extracted and parsed, then sent to LLM, and ask it to "read it" say 5 words, and say "What questions do you have?"
    # - Follow up questions, in langgraph should go through the path selection, and if referring to the file
    # - A new graph path should be created that references the previous file.
    # - if an image is received, it should ask gpt4vision for a description, but this is probably a different path
    # - Limit content of the file to 10000 tokens, otherwise is too big.
    # - If file is too big, it should do a mini RAG (later)


@router.delete('/v1/messages', tags=['chat'], response_model=Message)
def clear_chat_messages(plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    if plugin_id in ['null', '']:
        plugin_id = None

    # get current chat session
    chat_session = chat_db.get_chat_session(uid, plugin_id=plugin_id)
    chat_session_id = chat_session['id'] if chat_session else None

    err = chat_db.clear_chat(uid, plugin_id=plugin_id, chat_session_id=chat_session_id)
    if err:
        raise HTTPException(status_code=500, detail='Failed to clear chat')

    # clean thread chat file
    fc_tool = FileChatTool()
    fc_tool.cleanup(uid)

    # clear session
    if chat_session_id is not None:
        chat_db.delete_chat_session(uid, chat_session_id)

    return initial_message_util(uid, plugin_id)


def initial_message_util(uid: str, app_id: Optional[str] = None):
    print('initial_message_util', app_id)

    # init chat session
    chat_session = acquire_chat_session(uid, plugin_id=app_id)

    prev_messages = list(reversed(chat_db.get_messages(uid, limit=5, plugin_id=app_id)))
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
        plugin_id=app_id,
        from_external_integration=False,
        type='text',
        memories_id=[],
        chat_session_id=chat_session['id'],
    )
    chat_db.add_message(uid, ai_message.dict())
    chat_db.add_message_to_chat_session(uid, chat_session['id'], ai_message.id)
    return ai_message


@router.post('/v1/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(plugin_id: Optional[str], uid: str = Depends(auth.get_current_user_uid)):
    return initial_message_util(uid, plugin_id)


@router.get('/v1/messages', response_model=List[Message], tags=['chat'])
def get_messages_v1(uid: str = Depends(auth.get_current_user_uid)):
    messages = chat_db.get_messages(uid, limit=100, include_memories=True)
    if not messages:
        return [initial_message_util(uid)]
    return messages


@router.get('/v2/messages', response_model=List[Message], tags=['chat'])
def get_messages(plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    if plugin_id in ['null', '']:
        plugin_id = None

    chat_session = chat_db.get_chat_session(uid, plugin_id=plugin_id)
    chat_session_id = chat_session['id'] if chat_session else None

    messages = chat_db.get_messages(uid, limit=100, include_memories=True, plugin_id=plugin_id,
                                    chat_session_id=chat_session_id)
    print('get_messages', len(messages), plugin_id)
    if not messages:
        return [initial_message_util(uid, plugin_id)]
    return messages


@router.post("/v1/voice-messages")
async def create_voice_message(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    paths = retrieve_file_paths(files, uid)
    if len(paths) == 0:
        raise HTTPException(status_code=400, detail='Paths is invalid')

    # wav
    wav_paths = decode_files_to_wav(paths)
    if len(wav_paths) == 0:
        raise HTTPException(status_code=400, detail='Wav path is invalid')

    # segmented
    segmented_paths = set()
    retrieve_vad_segments(wav_paths[0], segmented_paths)
    if len(segmented_paths) == 0:
        raise HTTPException(status_code=400, detail='Segmented paths is invalid')

    resp = process_voice_message_segment(list(segmented_paths)[0], uid)
    if not resp:
        raise HTTPException(status_code=400, detail='Bad params')

    return resp


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


@router.post("/v1/voice-message/transcribe")
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
