import io
import os
import shutil
import subprocess
import threading
from datetime import datetime
from typing import List

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from pydub import AudioSegment

from database import conversations as conversations_db
from models.conversation import CreateConversation
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation
from utils.other import endpoints as auth
from utils.other.storage import get_syncing_file_temporal_signed_url
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.stt.vad import vad_is_empty

router = APIRouter()


def convert_pocket_mp3_to_wav(mp3_path: str, wav_path: str) -> bool:
    """
    Convert Pocket MP3 file to WAV using ffmpeg.
    Pocket MP3 format: 144-byte frames with marker 0xFF 0xF3 0x48 0xC4
    
    Args:
        mp3_path: Path to input MP3 file
        wav_path: Path to output WAV file
        
    Returns:
        True if conversion successful, False otherwise
    """
    try:
        print(f"Converting Pocket MP3 to WAV: {mp3_path} -> {wav_path}")
        
        # Use ffmpeg to convert MP3 to WAV (16kHz, mono, 16-bit PCM)
        result = subprocess.run([
            'ffmpeg',
            '-i', mp3_path,
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',      # Mono
            '-sample_fmt', 's16',  # 16-bit signed PCM
            '-y',            # Overwrite output file
            wav_path
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg conversion failed: {result.stderr}")
            return False
            
        # Verify WAV file was created and has content
        if not os.path.exists(wav_path):
            print(f"WAV file not created: {wav_path}")
            return False
            
        file_size = os.path.getsize(wav_path)
        if file_size == 0:
            print(f"WAV file is empty: {wav_path}")
            return False
            
        print(f"Successfully converted MP3 to WAV: {file_size} bytes")
        return True
        
    except Exception as e:
        print(f"Error converting MP3 to WAV: {e}")
        return False


def retrieve_vad_segments(wav_path: str, segmented_paths: set):
    """
    Split audio into segments using VAD (Voice Activity Detection).
    Reuses existing logic from sync.py
    """
    try:
        audio = AudioSegment.from_wav(wav_path)
        duration_ms = len(audio)
        print(f"Audio duration: {duration_ms}ms ({duration_ms/1000:.1f}s)")
        
        # Split into 60-second chunks
        chunk_duration_ms = 60 * 1000
        segments = []
        
        for i in range(0, duration_ms, chunk_duration_ms):
            chunk = audio[i:i + chunk_duration_ms]
            chunk_path = wav_path.replace('.wav', f'_segment_{i // 1000}.wav')
            chunk.export(chunk_path, format='wav')
            print(f"Created chunk: {chunk_path} ({len(chunk)}ms)")
            
            # Check if segment has voice activity
            is_empty = vad_is_empty(chunk_path)
            print(f"VAD check for {chunk_path}: {'EMPTY' if is_empty else 'HAS SPEECH'}")
            
            if not is_empty:
                segments.append(chunk_path)
                segmented_paths.add(chunk_path)
            else:
                # Remove empty segments
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
                    
        print(f"VAD segmentation complete: {len(segments)} segments with voice activity out of {(duration_ms // chunk_duration_ms) + 1} total chunks")
        
    except Exception as e:
        print(f"Error in VAD segmentation: {e}")


def process_segment(segment_path: str, uid: str, response: dict):
    """
    Process a single audio segment: transcribe and create/update conversation.
    Reuses existing logic from sync.py
    """
    try:
        print(f"Processing segment: {segment_path}")
        
        # Upload to cloud storage and get URL
        try:
            url = get_syncing_file_temporal_signed_url(segment_path)
            print(f"Uploaded segment to cloud storage: {url}")
        except Exception as upload_error:
            print(f"Cloud storage upload error: {type(upload_error).__name__}: {upload_error}")
            import traceback
            traceback.print_exc()
            raise
        
        # Transcribe using Whisper
        segments = fal_whisperx(url, 2)
        
        if not segments:
            print(f"No transcription segments found for {segment_path}")
            return
            
        # Get audio duration for post-processing
        from pydub import AudioSegment as AS
        audio = AS.from_wav(segment_path)
        duration_seconds = len(audio) // 1000
        
        # Post-process segments
        segments = fal_postprocessing(segments, duration_seconds)
        
        # Extract timestamp from filename
        # Format: audio_{deviceid}_pocket_mp3_{timestamp}_segment_{offset}.wav
        filename = os.path.basename(segment_path)
        parts = filename.split('_')
        
        # Find timestamp (Unix timestamp in seconds)
        timestamp = None
        for i, part in enumerate(parts):
            if part == 'mp3' and i + 1 < len(parts):
                try:
                    timestamp = int(parts[i + 1])
                    break
                except ValueError:
                    continue
                    
        if not timestamp:
            # Fallback: use current time if timestamp cannot be extracted
            print(f"Could not extract timestamp from filename: {filename}, using current time")
            timestamp = int(datetime.now().timestamp())
            
        # Create conversation
        conversation_data = CreateConversation(
            started_at=datetime.fromtimestamp(timestamp),
            finished_at=datetime.fromtimestamp(timestamp + duration_seconds),
            transcript_segments=segments,  # Already TranscriptSegment objects
            source='pocket', 
        )
        
        # Process conversation (creates memory, runs plugins, etc.)
        conversation = process_conversation(uid, 'en', conversation_data)
        
        if conversation:
            # Conversation is a Conversation object, not a dict
            response['new_memories'].add(conversation.id)
            print(f"Processed segment: {segment_path} -> conversation {conversation.id}")
        
    except Exception as e:
        print(f"Error processing segment {segment_path}: {e}")
    finally:
        # Cleanup segment file
        if os.path.exists(segment_path):
            os.remove(segment_path)


@router.post("/v1/pocket/upload-mp3")
async def upload_pocket_mp3(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Upload Pocket MP3 recordings for backend conversion and processing.
    
    Flow:
    1. Save uploaded MP3 files
    2. Convert MP3 -> WAV using ffmpeg
    3. Split WAV into segments using VAD
    4. Transcribe segments
    5. Create/update conversations
    """
    print(f"Received {len(files)} Pocket MP3 file(s) from user {uid}")
    
    # Create user directory
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    
    mp3_paths = []
    
    # Save uploaded MP3 files
    for file in files:
        filename = file.filename
        
        # Validate MP3 file
        if not filename.endswith('.mp3'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, expected .mp3")
            
        path = f"{directory}{filename}"
        try:
            with open(path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            mp3_paths.append(path)
            print(f"Saved MP3 file: {path} ({os.path.getsize(path)} bytes)")
        except Exception as e:
            if os.path.exists(path):
                os.remove(path)
            raise HTTPException(status_code=500, detail=f"Failed to write file {filename}: {str(e)}")
    
    # Convert MP3 files to WAV
    wav_paths = []
    for mp3_path in mp3_paths:
        wav_path = mp3_path.replace('.mp3', '.wav')
        success = convert_pocket_mp3_to_wav(mp3_path, wav_path)
        
        if success:
            wav_paths.append(wav_path)
        else:
            print(f"Failed to convert {mp3_path}, skipping")
            
        # Cleanup MP3 file
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
    
    if not wav_paths:
        raise HTTPException(status_code=500, detail="Failed to convert any MP3 files to WAV")
    
    # VAD segmentation
    def chunk_threads(threads):
        chunk_size = 5
        for i in range(0, len(threads), chunk_size):
            [t.start() for t in threads[i : i + chunk_size]]
            [t.join() for t in threads[i : i + chunk_size]]
    
    segmented_paths = set()
    threads = [threading.Thread(target=retrieve_vad_segments, args=(path, segmented_paths)) for path in wav_paths]
    chunk_threads(threads)
    
    print(f'Pocket MP3 upload: {len(segmented_paths)} segments after VAD')
    
    # Cleanup WAV files
    for wav_path in wav_paths:
        if os.path.exists(wav_path):
            os.remove(wav_path)
    
    # Process segments
    response = {'updated_memories': set(), 'new_memories': set()}
    threads = [
        threading.Thread(
            target=process_segment,
            args=(path, uid, response),
        )
        for path in segmented_paths
    ]
    chunk_threads(threads)
    
    # Convert sets to lists for JSON serialization
    return {
        'updated_memories': list(response['updated_memories']),
        'new_memories': list(response['new_memories'])
    }
