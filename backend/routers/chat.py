import uuid
import re
import base64
from datetime import datetime, timezone, timedelta
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
from utils.conversations.process_conversation import process_conversation
import asyncio
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream, execute_persona_chat_stream

import database.redis_db as redis_db
import json

router = APIRouter()

def _handle_openglass_images(files: List[UploadFile], uid: str):
    """
    Handle OpenGlass images for immediate processing with AI descriptions.
    Returns complete image data including descriptions in the upload response.
    """
    import time
    import concurrent.futures
    from concurrent.futures import ThreadPoolExecutor
    
    print(f"🎯 _handle_openglass_images CALLED with {len(files)} files for user {uid}")
    print(f"📸 Processing {len(files)} OpenGlass images for user {uid}")

    def process_single_image(file: UploadFile) -> dict:
        """Process a single image and return complete image data with description"""
        try:
            print(f"📸 Processing OpenGlass image: {file.filename}")
            
            # Read and validate image
            image_data = file.file.read()
            if len(image_data) == 0:
                print(f"❌ Empty image file: {file.filename}")
                return None
            
            # Convert to base64 for processing
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Extract timestamp from filename for consistent ID
            import re
            timestamp_match = re.search(r'openglass_image_(\d+)', file.filename)
            if timestamp_match:
                consistent_id = f"openglass_{timestamp_match.group(1)}"
                print(f"🔍 Using consistent ID from filename: {consistent_id}")
            else:
                consistent_id = f"openglass_{int(time.time() * 1000)}"
                print(f"⚠️ Fallback ID generated: {consistent_id}")
            
            # Save image to temporary file for cloud upload
            import tempfile
            temp_image_path = Path(f"/tmp/{uuid.uuid4()}_{file.filename}")
            with open(temp_image_path, 'wb') as temp_file:
                temp_file.write(image_data)
            
            # Upload to cloud storage
            signed_url = upload_image_to_bucket(image_data, uid)
            print(f"☁️ Uploaded to cloud: {signed_url[:100]}...")
            
            # Upload thumbnail
            thumbnail_url = upload_thumbnail(temp_image_path, uid)
            print(f"🖼️ Uploaded thumbnail: {thumbnail_url[:100]}...")
            
            # Get AI description
            print(f"🤖 Getting AI description for {consistent_id}...")
            description = get_openai_image_description(base64_image)
            print(f"✅ OpenAI description received: {description[:100]}...")
            
            # Determine if interesting for summaries
            is_interesting = is_image_interesting_for_summary(description)
            print(f"🎯 Interesting for summaries: {is_interesting}")
            
            # Clean up temp file
            temp_image_path.unlink()
            
            result = {
                'id': consistent_id,
                'name': file.filename,
                'thumbnail': thumbnail_url,
                'url': signed_url,
                'description': description,
                'is_interesting': is_interesting,
                'mime_type': file.content_type or 'application/octet-stream',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'deleted': False,
                'thumb_name': '',
                'openai_file_id': ''
            }
            
            print(f"✅ Successfully processed OpenGlass image {consistent_id} with description")
            return result
            
        except Exception as e:
            print(f"❌ Error processing OpenGlass image {file.filename}: {e}")
            return None

    # Process all images concurrently with timeout
    files_chat = []
    
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all tasks
            future_to_file = {executor.submit(process_single_image, file): file for file in files}
            
            # Collect results with timeout
            for future in concurrent.futures.as_completed(future_to_file, timeout=60):
                try:
                    result = future.result(timeout=30)
                    if result:
                        files_chat.append(result)
                except concurrent.futures.TimeoutError:
                    file = future_to_file[future]
                    print(f"⏰ Timeout processing {file.filename}")
                except Exception as e:
                    file = future_to_file[future]
                    print(f"❌ Error in future result for {file.filename}: {e}")
    except concurrent.futures.TimeoutError:
        print(f"⏰ Overall timeout processing OpenGlass images")
    except Exception as e:
        print(f"❌ Error in concurrent processing: {e}")
    
    print(f"✅ Successfully processed {len(files_chat)} OpenGlass images")
    
    # **NEW: Link processed images to recent conversation**
    if files_chat:
        try:
            linked_conversation_id = _link_images_to_recent_conversation(uid, files_chat)
        except Exception as e:
            print(f"⚠️ Error linking images to conversation: {e}")
    
    # If no images were successfully processed, log details but still return valid response
    if not files_chat:
        print(f"⚠️ No OpenGlass images could be processed successfully out of {len(files)} uploaded")
        # Return empty array rather than raising exception for now
        # This allows the frontend to handle partial failures gracefully
    
    return files_chat


def _link_images_to_recent_conversation(uid: str, processed_images: List[dict]) -> Optional[str]:
    """
    Link processed images to the most recent conversation within 10 minutes.
    
    Args:
        uid: User ID
        processed_images: List of processed image dictionaries
        
    Returns:
        str: Conversation ID if photos were linked, None otherwise
    """
    try:
        print(f"🔗 Attempting to link {len(processed_images)} images to recent conversation for user {uid}")
        
        # Get recent conversations (last 5, sorted by most recent first)
        recent_conversations = conversations_db.get_recent_conversations(uid, limit=5)
        
        if not recent_conversations:
            print(f"🔍 No recent conversations found for user {uid}")
            return None
            
        print(f"🔍 Found {len(recent_conversations)} recent conversations for user {uid}")
        for i, conv in enumerate(recent_conversations):
            conv_id = conv.get('id', 'unknown')
            conv_created = conv.get('created_at', 'unknown')
            print(f"   {i+1}. {conv_id} - created: {conv_created}")
            
        # Find the most recent conversation (within last 10 minutes)
        now = datetime.now(timezone.utc)
        target_conversation = None
        
        for conv in recent_conversations:
            # Handle both timestamp (integer), ISO string, and datetime object formats for created_at
            created_at_value = conv['created_at']
            
            if isinstance(created_at_value, datetime):
                # Already a datetime object (from our get_recent_conversations fix)
                conv_created = created_at_value
            elif isinstance(created_at_value, (int, float)):
                # Convert timestamp to datetime
                conv_created = datetime.fromtimestamp(created_at_value, tz=timezone.utc)
            else:
                # Parse ISO string format
                conv_created = datetime.fromisoformat(created_at_value.replace('Z', '+00:00'))
            
            time_diff = now - conv_created
            
            print(f"🔍 Checking conversation {conv.get('id', 'unknown')}: created {conv_created}, diff {time_diff}")
            
            if time_diff <= timedelta(minutes=10):
                target_conversation = conv
                break
        
        if not target_conversation:
            print(f"🔍 No recent conversation found within 10 minutes for user {uid}")
            return None
        
        conversation_id = target_conversation['id']
        print(f"✅ Found target conversation within 10 minutes: {conversation_id}")
        
        # **NEW: Check for duplicate images before linking**
        existing_photos = conversations_db.get_conversation_photos(uid, conversation_id)
        
        # Filter out duplicate images based on description similarity
        unique_images = []
        for image_data in processed_images:
            new_description = image_data.get('description', '').lower().strip()
            
            # Check against existing photos
            is_duplicate = False
            for existing_photo in existing_photos:
                existing_description = existing_photo.get('description', '').lower().strip()
                
                # Calculate similarity (simple approach: check if descriptions are very similar)
                if _descriptions_are_similar(new_description, existing_description):
                    print(f"🚫 Skipping duplicate image {image_data.get('id', 'unknown')}: similar to existing photo")
                    is_duplicate = True
                    break
            
            # Check against other images in this batch
            if not is_duplicate:
                for other_image in unique_images:
                    other_description = other_image.get('description', '').lower().strip()
                    if _descriptions_are_similar(new_description, other_description):
                        print(f"🚫 Skipping duplicate image {image_data.get('id', 'unknown')}: similar to other image in batch")
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique_images.append(image_data)
                print(f"✅ Image {image_data.get('id', 'unknown')} is unique, will be linked")
        
        if not unique_images:
            print(f"🚫 All images were duplicates, nothing to link")
            return conversation_id  # Still return the conversation ID even if no new photos added
        
        print(f"📸 Linking {len(unique_images)} unique images (filtered from {len(processed_images)} total)")
        
        # Create ConversationPhoto objects for linking
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
            print(f"📸 Prepared photo {conversation_photo.id} for conversation {conversation_id}")
        
        if conversation_photos:
            # Add photos to existing conversation using the correct database method
            print(f"🔗 About to link {len(conversation_photos)} unique photos to conversation {conversation_id}")
            for photo in conversation_photos:
                print(f"   📸 Photo ID: {photo.id} - {photo.description[:50]}...")
            
            conversations_db.add_photos_to_conversation(uid, conversation_id, conversation_photos)
            print(f"✅ Successfully linked {len(conversation_photos)} unique images to conversation {conversation_id}")
            
            # Return the conversation ID that received the photos
            return conversation_id
        else:
            print(f"⚠️ No unique photos to link after duplicate filtering")
            return conversation_id
          
    except Exception as e:
        print(f"❌ Error linking images to recent conversation: {e}")
        import traceback
        traceback.print_exc()
        return None


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
    
    if is_similar:
        print(f"🔍 Similarity check: '{desc1[:30]}...' vs '{desc2[:30]}...' = {similarity:.2f} (subset: {subset_ratio:.2f})")
    
    return is_similar

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
    chat_session = chat_db.get_chat_session(uid, plugin_id=app_id)
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


@router.post('/v2/initial-message', tags=['chat'], response_model=Message)
def create_initial_message(app_id: Optional[str], uid: str = Depends(auth.get_current_user_uid)):
    return initial_message_util(uid, app_id)


@router.get('/v2/messages', response_model=List[Message], tags=['chat'])
def get_messages(plugin_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    if plugin_id in ['null', '']:
        plugin_id = None

    chat_session = chat_db.get_chat_session(uid, plugin_id=plugin_id)
    chat_session_id = chat_session['id'] if chat_session else None

    messages = chat_db.get_messages(uid, limit=100, include_conversations=True, plugin_id=plugin_id,
                                    chat_session_id=chat_session_id)
    print('get_messages', len(messages), plugin_id)
    if not messages:
        return [initial_message_util(uid, plugin_id)]
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
    
    print(f"🔍 DEBUG: Processing {len(files)} files for user {uid}")
    
    for file in files:
        print(f"🔍 DEBUG: Checking file - filename: '{file.filename}', content_type: '{file.content_type}'")
        
        # Check if this is an OpenGlass image by filename (definitive)
        is_openglass = file.filename and 'openglass_image' in file.filename.lower()
        
        if is_openglass:
            print(f"✅ DEBUG: Detected as OpenGlass image: {file.filename}")
            openglass_images.append(file)
        else:
            print(f"❌ DEBUG: NOT detected as OpenGlass image: {file.filename}")
            regular_files.append(file)
    
    print(f"🔍 DEBUG: Found {len(openglass_images)} OpenGlass images, {len(regular_files)} regular files")
    
    # Handle OpenGlass images with immediate description processing
    if openglass_images:
        print(f"🎯 DEBUG: Processing {len(openglass_images)} OpenGlass images through simplified processing")
        
        complete_images = _handle_openglass_images(openglass_images, uid)
        
        # Link images to recent conversation for better organization
        linked_conversation_id = _link_images_to_recent_conversation(uid, complete_images)
        
        print(f"🔄 Returning {len(complete_images)} OpenGlass images with complete data")
        
        # Return complete image data directly (with descriptions included)
        # This bypasses FileChat conversion to preserve all our custom fields
        # Add linked conversation info to each image if photos were linked
        if linked_conversation_id:
            for image in complete_images:
                image['linked_conversation_id'] = linked_conversation_id
        
        return complete_images
    
    # Handle regular files (existing logic)
    if regular_files:
        return fc.upload_files(regular_files, uid)
    
    # No files to process
    raise HTTPException(status_code=400, detail="No valid files to process")


def get_openai_image_description(base64_image: str) -> str:
    """Get AI description for an image using OpenAI GPT-4o Vision"""
    from openai import OpenAI
    import os
    
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
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
    
    return response.choices[0].message.content or "Image captured by OpenGlass"

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

def upload_image_to_bucket(image_data: bytes, uid: str) -> str:
    """Upload image to cloud storage and return signed URL"""
    import tempfile
    import os
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
        temp_file.write(image_data)
        temp_file_path = temp_file.name
    
    try:
        # Upload using existing storage function
        result = storage.upload_multi_chat_files([temp_file_path], uid)
        signed_url = result.get(temp_file_path, "")
        
        # Clean up temp file
        os.unlink(temp_file_path)
        
        return signed_url
    except Exception as e:
        print(f"Error uploading image: {e}")
        # Clean up temp file even on error
        try:
            os.unlink(temp_file_path)
        except:
            pass
        return ""

def upload_thumbnail(temp_image_path: Path, uid: str) -> str:
    """Generate and upload thumbnail"""
    try:
        from PIL import Image
        with Image.open(temp_image_path) as img:
            img.thumbnail((128, 128))
            thumbnail_path = temp_image_path.with_suffix('.thumb.jpg')
            img.save(thumbnail_path, format='JPEG')
            
            # Upload using existing storage function
            thumbnail_url = storage.upload_chat_file_thumbnail(str(thumbnail_path), uid)
            
            # Clean up local thumbnail
            thumbnail_path.unlink()
            
            return thumbnail_url
            
    except Exception as e:
        print(f"❌ Error generating thumbnail: {e}")
        return ""
