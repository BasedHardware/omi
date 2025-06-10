import uuid
import re
import base64
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
from models.conversation import CreateConversation, ConversationSource, ConversationPhoto
from utils.conversations.process_conversation import process_conversation, retrieve_in_progress_conversation
import asyncio
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream, execute_persona_chat_stream

import database.redis_db as redis_db
import json
import os

router = APIRouter()

# Simple in-memory cache to prevent reprocessing the same images repeatedly
# Maps image_id -> (timestamp, description) to track recently processed images
_image_processing_cache = {}
_CACHE_DURATION_SECONDS = 300  # 5 minutes

def _is_image_recently_processed(image_id: str, description: str) -> bool:
    """Check if an image was recently processed with the same description"""
    if not image_id or not description:
        return False
    
    current_time = time.time()
    
    # Clean old cache entries first
    expired_keys = [key for key, (timestamp, _) in _image_processing_cache.items() 
                   if current_time - timestamp > _CACHE_DURATION_SECONDS]
    for key in expired_keys:
        del _image_processing_cache[key]
    
    # Check if this image was recently processed
    if image_id in _image_processing_cache:
        timestamp, cached_description = _image_processing_cache[image_id]
        
        # If processed recently with the same description, it's a duplicate
        if current_time - timestamp < _CACHE_DURATION_SECONDS:
            # Check if descriptions are similar
            if _descriptions_are_similar(description.lower().strip(), cached_description.lower().strip()):
                return True
    
    # Cache this image as recently processed
    _image_processing_cache[image_id] = (current_time, description)
    return False

def _handle_openglass_images(files: List[UploadFile], uid: str):
    """
    SIMPLIFIED: Handle OpenGlass images elegantly using existing conversation architecture.
    Supports all three scenarios: audio-only, image-only, audio+image without redundancy.
    """
    import time
    import concurrent.futures
    from concurrent.futures import ThreadPoolExecutor

    def process_single_image(file: UploadFile) -> dict:
        """Process a single image and return complete image data with description"""
        try:
            # Read and validate image
            image_data = file.file.read()
            if len(image_data) == 0:
                return None
            
            # Convert to base64 for processing
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Extract timestamp from filename for consistent ID
            import re
            timestamp_match = re.search(r'openglass_(\d+)', file.filename)
            if timestamp_match:
                consistent_id = f"openglass_{timestamp_match.group(1)}"
            else:
                consistent_id = f"openglass_{int(time.time() * 1000)}"
            
            # Get AI description
            description = get_openai_image_description(base64_image)
            
            result = {
                'id': consistent_id,
                'name': file.filename,
                'description': description,
                'mime_type': file.content_type or 'application/octet-stream',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'image_data': image_data  # Keep for upload
            }
            
            return result
            
        except Exception as e:
            print(f"Error processing OpenGlass image {file.filename}: {e}")
            return None

    # Process all images concurrently
    processed_images = []
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_file = {executor.submit(process_single_image, file): file for file in files}
            
            for future in concurrent.futures.as_completed(future_to_file, timeout=60):
                try:
                    result = future.result(timeout=30)
                    if result:
                        processed_images.append(result)
                except Exception as e:
                    file = future_to_file[future]
                    print(f"Error processing {file.filename}: {e}")
    except Exception as e:
        print(f"Error in concurrent processing: {e}")
    
    # Simple duplicate detection within current batch only
    unique_images = []
    for image in processed_images:
        is_duplicate = any(
            _descriptions_are_similar(image['description'], existing['description'], threshold=0.9)
            for existing in unique_images
        )
        if not is_duplicate:
            unique_images.append(image)
    
    # Upload unique images to cloud storage
    uploaded_images = []
    if unique_images:
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                upload_futures = [executor.submit(upload_single_image_sync, img.copy(), uid) for img in unique_images]
                
                for future in concurrent.futures.as_completed(upload_futures, timeout=60):
                    try:
                        result = future.result(timeout=30)
                        uploaded_images.append(result)
                    except Exception as e:
                        print(f"Error in upload future: {e}")
        
        except Exception as e:
            print(f"Error in concurrent upload processing: {e}")
    
    # ELEGANT: Use existing conversation architecture - much simpler!
    conversation_id = _integrate_with_existing_conversation(uid, uploaded_images)
    
    # Add conversation context to response
    for image in uploaded_images:
        image['linked_conversation_id'] = conversation_id
    
    return uploaded_images

def _integrate_with_existing_conversation(uid: str, images: List[dict]) -> Optional[str]:
    """
    ELEGANT: Single integration point that uses existing conversation architecture.
    Automatically handles all three scenarios without complex logic.
    """
    # Check if user has active conversation (recording or recent)
    active_conversation = retrieve_in_progress_conversation(uid)
    
    if active_conversation and not active_conversation.get('id', '').startswith('active_session_'):
        # SCENARIO 1 & 2: Add to existing conversation (audio+image or extending image session)
        conversation_id = active_conversation['id']
        conversation_photos = [
            ConversationPhoto(
                id=img['id'],
                url=img.get('url', ''),
                thumbnail_url=img.get('thumbnail', ''),
                description=img['description'],
                created_at=img['created_at'],
                added_at=datetime.now(timezone.utc).isoformat()
            ) for img in images
        ]
        
        conversations_db.add_photos_to_conversation(uid, conversation_id, conversation_photos)
        return conversation_id
    else:
        # SCENARIO 3: Create image-only conversation using intelligent timeout logic (not immediate processing)
        # Use the same timeout pattern as audio conversations instead of immediate processing
        return _create_new_photo_conversation(uid, images)

def _create_image_conversation_via_pipeline(uid: str, images: List[dict]) -> str:
    """
    DEPRECATED: This function bypassed timeout logic by using force_process=True.
    Use _create_new_photo_conversation instead for consistent timeout behavior.
    """
    # This function is deprecated in favor of using the same timeout logic as audio conversations
    return _create_new_photo_conversation(uid, images)

def _link_images_to_recent_conversation(uid: str, processed_images: List[dict]) -> Optional[str]:
    """
    REMOVED: This complex function has been replaced by _integrate_with_existing_conversation()
    which uses the existing conversation pipeline for better consistency and simplicity.
    """
    # This function has been deprecated and replaced by the new simplified architecture
    pass

def _descriptions_are_similar(desc1: str, desc2: str, threshold: float = 0.8) -> bool:
    """
    Check if two image descriptions are similar enough to be considered duplicates.
    Uses simple word overlap for similarity detection.
    """
    if not desc1 or not desc2:
        return False
    
    # Convert to sets of words for comparison
    words1 = set(desc1.split())
    words2 = set(desc2.split())
    
    if not words1 or not words2:
        return False
    
    # Calculate Jaccard similarity (intersection over union)
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    if union == 0:
        return False
    
    similarity = intersection / union
    
    # Also check if one description is a subset of another (for different length descriptions)
    smaller_set = words1 if len(words1) < len(words2) else words2
    larger_set = words2 if len(words1) < len(words2) else words1
    
    subset_ratio = len(smaller_set.intersection(larger_set)) / len(smaller_set) if smaller_set else 0
    
    # Consider similar if either high overall similarity or high subset similarity
    is_similar = similarity >= threshold or subset_ratio >= 0.9
    
    return is_similar

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
    # Check if these are OpenGlass images
    openglass_images = []
    regular_files = []
    
    for file in files:
        # Check if this is an OpenGlass image by filename (definitive)
        is_openglass = file.filename and 'openglass' in file.filename.lower()
        
        if is_openglass:
            openglass_images.append(file)
        else:
            regular_files.append(file)
    
    # Handle OpenGlass images with immediate description processing
    if openglass_images:
        complete_images = _handle_openglass_images(openglass_images, uid)
        return complete_images
    
    # Handle regular files (existing logic)
    if regular_files:
        # Process regular files using the existing FileChatTool workflow
        processed_files = []
        
        # Save uploaded files to temporary paths first
        for file in regular_files:
            try:
                # Create temporary file path
                import tempfile
                import shutil
                
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
                print(f"Error processing regular file {file.filename}: {e}")
                continue
        
        return processed_files
    
    # No files to process
    raise HTTPException(status_code=400, detail="No valid files to process")


def get_openai_image_description(base64_image: str) -> str:
    """Get AI description for an image using OpenAI GPT-4o Vision"""
    try:
        from openai import OpenAI
        import os
        
        # Check if API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return "Image captured by OpenGlass (AI description unavailable)"
        
        client = OpenAI(
            api_key=api_key,
            timeout=30.0
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What's in this image? Describe in detail what you see. The camera quality may be low, but do your best to accurately describe what you see anyway. Do not comment on the image quality; only describe the content."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=150
        )
        
        description = response.choices[0].message.content
        
        if description and description.strip():
            return description.strip()
        else:
            return "Image captured by OpenGlass"
            
    except Exception as e:
        print(f"Error getting OpenAI image description: {e}")
        return "Image captured by OpenGlass (AI description failed)"

def is_image_interesting_for_summary(description: str) -> bool:
    """Determine if image is interesting enough for conversation summaries"""
    from openai import OpenAI
    import os
    
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
        timeout=30.0
    )
    
    try:
        filter_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": f"Is this image interesting enough to save in a conversation summary? Only reject if the image is completely black, white, or extremely blurry with no discernible content. Description: {description}\n\nRespond with only 'INTERESTING: YES' or 'INTERESTING: NO'"
                }
            ],
            max_tokens=10
        )
        
        filter_result = filter_response.choices[0].message.content or "INTERESTING: YES"
        return "YES" in filter_result.upper()
    except Exception as e:
        print(f"Error in interesting filter: {e}")
        return True  # Default to interesting on error

def upload_image_to_bucket(image_data: bytes, uid: str, original_filename: str) -> str:
    """Upload image to cloud storage and return signed URL"""
    try:
        import tempfile
        import os
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(image_data)
            temp_file_path = temp_file.name
        
        try:
            # Use direct blob upload instead of transfer_manager to avoid FFI pickling issues
            bucket = storage._get_bucket_safely(storage.chat_files_bucket, "chat image upload")
            if not bucket:
                return ""
            
            # Use original filename for blob name (matching upload_multi_chat_files structure)
            blob_name = f'{uid}/{original_filename}'
            blob = bucket.blob(blob_name)
            
            # Upload directly using blob
            blob.upload_from_filename(temp_file_path)
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Return signed URL for private bucket access (24 hour expiry)
            try:
                return storage._get_signed_url(blob, 1440)
            except Exception as url_error:
                print(f"Warning: Could not generate signed URL for full image: {url_error}")
                # Return empty string but don't fail - image still processed with description
                return ""
            
        except Exception as e:
            print(f"Warning: Could not upload image to cloud storage: {e}")
            # Clean up temp file even on error
            try:
                os.unlink(temp_file_path)
            except:
                pass
            return ""
            
    except Exception as e:
        print(f"Error in upload_image_to_bucket: {e}")
        return ""

def upload_thumbnail(image_bytes: bytes, image_name: str, uid: str) -> str:
    """Generate and upload thumbnail from image bytes"""
    try:
        from PIL import Image
        import tempfile
        import io
        
        # Create thumbnail from bytes directly
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.thumbnail((128, 128))
            
            # Save thumbnail to temporary file
            thumbnail_path = f"/tmp/{uuid.uuid4()}_thumb_{image_name}"
            img.save(thumbnail_path, format='JPEG')
            
            try:
                # Get bucket for direct upload (avoiding transfer_manager)
                bucket = storage._get_bucket_safely(storage.chat_files_bucket, "chat thumbnail upload")
                if not bucket:
                    return ""
                
                # Create blob with proper path structure
                blob_name = f'{uid}/thumbnails/{os.path.basename(thumbnail_path)}'
                blob = bucket.blob(blob_name)
                
                # Upload directly
                blob.upload_from_filename(thumbnail_path)
                
                # Clean up local thumbnail file
                Path(thumbnail_path).unlink()
                
                # Return signed URL for private bucket access (24 hour expiry)
                try:
                    return storage._get_signed_url(blob, 1440)
                except Exception as url_error:
                    print(f"Warning: Could not generate signed URL for thumbnail: {url_error}")
                    return ""
                
            except Exception as upload_error:
                print(f"Warning: Could not upload thumbnail to cloud storage: {upload_error}")
                # Clean up local thumbnail file
                try:
                    Path(thumbnail_path).unlink()
                except:
                    pass
                return ""
            
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return ""

def upload_single_image_sync(image_data: dict, uid: str) -> dict:
    """Upload a single image synchronously - used within ThreadPoolExecutor"""
    try:
        image_bytes = image_data.pop('image_data', None)  # Remove from dict after use
        image_name = image_data.get('name', 'unknown.jpg')
        
        # Always determine if interesting for summaries first (regardless of upload success)
        is_interesting = is_image_interesting_for_summary(image_data.get('description', ''))
        
        # Set default values
        signed_url = ""
        thumbnail_url = ""
        
        # Attempt cloud storage upload only if we have image bytes
        if image_bytes:
            try:
                # Upload to cloud storage
                signed_url = upload_image_to_bucket(image_bytes, uid, image_name)
                
                # Generate and upload thumbnail from bytes (no temp file needed)
                thumbnail_url = upload_thumbnail(image_bytes, image_name, uid)
                
            except Exception as upload_error:
                print(f"Warning: Upload failed for image {image_name}: {upload_error}")
                # Continue processing - we still have the description
        
        # Update image data with upload results (empty strings if upload failed)
        image_data.update({
            'thumbnail': thumbnail_url,
            'url': signed_url,
            'is_interesting': is_interesting,
            'upload_success': bool(signed_url),  # Track upload status for debugging
        })
        
        return image_data
        
    except Exception as e:
        print(f"Error processing image {image_data.get('name', 'unknown')}: {e}")
        # Still return the image data with description, just mark upload as failed
        image_data.update({
            'thumbnail': '',
            'url': '',
            'is_interesting': True,  # Default to interesting
            'upload_success': False,
        })
        return image_data

def _link_unique_images_to_recent_conversation(uid: str, unique_images: List[dict]) -> Optional[str]:
    """
    Simple linking: Link unique images to the most recent active conversation.
    
    Args:
        uid: User ID
        unique_images: List of unique image dictionaries (duplicates already removed)
        
    Returns:
        str: Conversation ID if photos were linked, None otherwise
    """
    try:
        # Get only the most recent conversation - keep it simple
        recent_conversations = conversations_db.get_recent_conversations(uid, limit=1)
        
        if not recent_conversations:
            return None
            
        conv = recent_conversations[0]
        created_at_value = conv['created_at']
        
        # Parse conversation creation time
        if isinstance(created_at_value, datetime):
            conv_created = created_at_value
        elif isinstance(created_at_value, (int, float)):
            conv_created = datetime.fromtimestamp(created_at_value, tz=timezone.utc)
        else:
            conv_created = datetime.fromisoformat(created_at_value.replace('Z', '+00:00'))
        
        now = datetime.now(timezone.utc)
        time_diff = now - conv_created
        
        # Simple timeout logic based on conversation type
        conv_status = conv.get('status', 'unknown')
        has_audio = bool(conv.get('transcript_segments') and len(conv.get('transcript_segments', [])) > 0)
        
        # ELEGANT: Never add photos to completed conversations - they are immutable
        if conv_status == 'completed':
            return None
        
        # Simplified timeout rules for active conversations only
        if conv_status == 'in_progress':
            max_timeout_hours = 4  # Active conversations get 4 hours
        elif conv_status == 'processing':
            max_timeout_hours = 1  # Processing conversations get 1 hour  
        else:
            # Unknown status conversations get short timeout
            max_timeout_minutes = 10
            max_timeout_hours = max_timeout_minutes / 60
        
        if time_diff.total_seconds() > max_timeout_hours * 3600:
            return None
        
        # Link the images
        conversation_id = conv['id']
        
        # ELEGANT: Verify existing conversation has required fields before linking
        # This prevents linking to old conversations that don't have proper structure
        if 'structured' not in conv or conv['structured'] is None:
            return None  # Force creation of new conversation
        
        conversation_photos = []
        for image_data in unique_images:
            conversation_photo = ConversationPhoto(
                id=image_data.get('id', 'unknown'),
                url=image_data.get('url', ''),
                thumbnail_url=image_data.get('thumbnail', ''),
                description=image_data.get('description', ''),
                created_at=image_data.get('created_at'),
                added_at=datetime.now(timezone.utc).isoformat()
            )
            conversation_photos.append(conversation_photo)
        
        if conversation_photos:
            conversations_db.add_photos_to_conversation(uid, conversation_id, conversation_photos)
            
            # ELEGANT: Set this conversation as in-progress for photo sessions
            # This allows the stop button to find and process it
            redis_db.set_in_progress_conversation_id(uid, conversation_id, ttl=3600)  # 1 hour TTL for photo sessions
            
            # CRITICAL: Also update the conversation status in database to 'in_progress'
            # So that retrieve_in_progress_conversation() doesn't reject it
            conversations_db.update_conversation_status(uid, conversation_id, 'in_progress')
            
            return conversation_id
        
        return None
          
    except Exception as e:
        print(f"Error linking images: {e}")
        return None

def _create_new_photo_conversation(uid: str, images: List[dict]) -> Optional[str]:
    """
    Elegantly create a new conversation for photo-only sessions.
    SIMPLE: Create as in-progress, let stop button process it.
    """
    try:
        from models.conversation import CreateConversation, ConversationSource, Structured
        import uuid
        
        # Create conversation photos
        conversation_photos = []
        for image_data in images:
            conversation_photo = ConversationPhoto(
                id=image_data.get('id', 'unknown'),
                url=image_data.get('url', ''),
                thumbnail_url=image_data.get('thumbnail', ''),
                description=image_data.get('description', ''),
                created_at=image_data.get('created_at'),
                added_at=datetime.now(timezone.utc).isoformat()
            )
            conversation_photos.append(conversation_photo)
        
        # SIMPLE: Create conversation as in-progress with ALL required fields
        # Use exact same structure as audio+photo conversations
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        conversation_dict = {
            'id': conversation_id,
            'uid': uid,
            'structured': Structured().dict(),  # Required field - convert to dict
            'source': ConversationSource.openglass.value,  # Convert enum to string
            'language': 'en',
            'transcript_segments': [],  # Empty for photo-only
            'started_at': now,
            'finished_at': now,
            'created_at': now,
            'status': 'in_progress',  # String value, not enum
            'discarded': False,
            'deleted': False,
            'geolocation': None,
            'plugins_results': [],
            'processing_memory_id': None,
            'visibility': 'private'
        }
        
        # Save conversation to database (without photos - they'll be added separately)
        conversations_db.upsert_conversation(uid, conversation_dict)
        
        # CRITICAL: Save photos separately to database after conversation is created
        # This prevents photos from being deleted by upsert_conversation
        if conversation_photos:
            conversations_db.store_conversation_photos(uid, conversation_id, conversation_photos)
        
        # Set in Redis for stop button to find
        redis_db.set_in_progress_conversation_id(uid, conversation_id, ttl=3600)
        
        return conversation_id
            
    except Exception as e:
        print(f"Error creating in-progress photo conversation: {e}")
        import traceback
        traceback.print_exc()
        return None
