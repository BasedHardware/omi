import io
import os
import re
import struct
import threading
import time
import wave
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from opuslib import Decoder
from pydub import AudioSegment
import requests

from database import conversations as conversations_db
from database import users as users_db
from database.conversations import get_closest_conversation_to_timestamps, update_conversation_segments
from models.conversation import CreateConversation, ConversationSource, Conversation
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation
from utils.other import endpoints as auth
from utils.other.storage import (
    get_syncing_file_temporal_signed_url,
    delete_syncing_temporal_file,
    download_audio_chunks_and_merge,
)
from utils import encryption
from utils.stt.vad import vad_is_empty
from deepgram import DeepgramClient, PrerecordedOptions

router = APIRouter()

_deepgram_client = None


def _get_deepgram_client():
    """Lazily initialize and return Deepgram client."""
    global _deepgram_client
    if _deepgram_client is None:
        api_key = os.getenv('DEEPGRAM_API_KEY')
        if not api_key:
            raise ValueError('DEEPGRAM_API_KEY environment variable not set')
        _deepgram_client = DeepgramClient(api_key=api_key)
    return _deepgram_client


def _transcribe_with_deepgram(audio_data: bytes, language: str = 'en'):
    """Transcribe audio using Deepgram API."""
    client = _get_deepgram_client()
    
    options = PrerecordedOptions(
        model='nova-2',
        language=language,
        smart_format=True,
        filler_words=False,
        punctuation=True,
    )
    
    response = client.listen.prerecorded.transcribe_content(audio_data, options)
    
    words = []
    detected_language = language
    
    if response and hasattr(response, 'results'):
        if hasattr(response.results, 'channels') and response.results.channels:
            for channel in response.results.channels:
                if hasattr(channel, 'alternatives') and channel.alternatives:
                    for alternative in channel.alternatives:
                        if hasattr(alternative, 'words') and alternative.words:
                            for word_obj in alternative.words:
                                words.append({
                                    'word': word_obj.word,
                                    'start': word_obj.start,
                                    'end': word_obj.end,
                                    'confidence': word_obj.confidence,
                                })
        
        if hasattr(response.results, 'detected_language'):
            detected_language = response.results.detected_language
    
    return words, detected_language


def _convert_deepgram_words_to_segments(words: list) -> List[TranscriptSegment]:
    """Convert Deepgram word-level output to TranscriptSegment format."""
    if not words:
        return []
    
    segments = []
    current_segment_text = []
    current_segment_start = None
    current_segment_confidence = []
    
    for word_obj in words:
        if isinstance(word_obj, dict):
            word = word_obj.get('word', '')
            start = word_obj.get('start', 0)
            end = word_obj.get('end', 0)
            confidence = word_obj.get('confidence', 0)
        else:
            word = getattr(word_obj, 'word', '')
            start = getattr(word_obj, 'start', 0)
            end = getattr(word_obj, 'end', 0)
            confidence = getattr(word_obj, 'confidence', 0)
        
        if current_segment_start is None:
            current_segment_start = start
        
        current_segment_text.append(word)
        current_segment_confidence.append(confidence)
        
        if len(current_segment_text) >= 10 or (word.endswith(('.', '?', '!')) and len(current_segment_text) > 2):
            avg_confidence = sum(current_segment_confidence) / len(current_segment_confidence) if current_segment_confidence else 0
            segment = TranscriptSegment(
                start=current_segment_start,
                end=end,
                text=' '.join(current_segment_text),
                confidence=avg_confidence,
                speaker=None,
            )
            segments.append(segment)
            current_segment_text = []
            current_segment_start = None
            current_segment_confidence = []
    
    if current_segment_text:
        avg_confidence = sum(current_segment_confidence) / len(current_segment_confidence) if current_segment_confidence else 0
        last_end = words[-1].get('end', 0) if isinstance(words[-1], dict) else getattr(words[-1], 'end', 0)
        segment = TranscriptSegment(
            start=current_segment_start,
            end=last_end,
            text=' '.join(current_segment_text),
            confidence=avg_confidence,
            speaker=None,
        )
        segments.append(segment)
    
    return segments


# **********************************************
# ******** AUDIO FORMAT CONVERSION *************
# **********************************************


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Convert PCM16 data to WAV format."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit audio
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


# **********************************************
# ********** AUDIO DOWNLOAD ENDPOINT ***********
# **********************************************


@router.get("/v1/sync/audio/{conversation_id}/{audio_file_id}", tags=['v1'])
def download_audio_file_endpoint(
    conversation_id: str,
    audio_file_id: str,
    format: str = Query(default="wav", regex="^(wav|pcm)$"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Download audio file from private cloud sync in the specified format.
    Merges chunks on-demand.

    Args:
        conversation_id: ID of the conversation
        audio_file_id: ID of the audio file within the conversation
        format: Output format - 'wav' or 'pcm' (raw) (default: wav)
        uid: User ID (from authentication)

    Returns:
        StreamingResponse with the audio file in the requested format
    """
    # Verify user owns the conversation
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Find the audio file in the conversation
    audio_files = conversation.get('audio_files', [])
    audio_file = None
    for af in audio_files:
        if af.get('id') == audio_file_id:
            audio_file = af
            break

    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found in conversation")

    # Get PCM data by merging chunks on-demand
    try:
        if not audio_file.get('chunk_timestamps'):
            raise HTTPException(status_code=500, detail="Audio file has no chunk timestamps")

        pcm_data = download_audio_chunks_and_merge(uid, conversation_id, audio_file['chunk_timestamps'])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio chunks not found in storage")
    except Exception as e:
        print(f"Error downloading audio file: {e}")
        raise HTTPException(status_code=500, detail="Failed to download audio file")

    # Convert to requested format
    if format == "wav":
        audio_data = pcm_to_wav(pcm_data)
        content_type = "audio/wav"
        extension = "wav"
    else:  # pcm (raw)
        audio_data = pcm_data
        content_type = "application/octet-stream"
        extension = "pcm"

    # Create descriptive filename
    filename = f"conversation_{conversation_id}_audio_{audio_file_id}.{extension}"

    # Return streaming response
    return StreamingResponse(
        io.BytesIO(audio_data),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# **********************************************
# ************ SYNC LOCAL FILES ****************
# **********************************************


import shutil
import wave


def decode_opus_file_to_wav(opus_file_path, wav_file_path, sample_rate=16000, channels=1, frame_size: int = 160):
    """Decode an Opus file with length-prefixed frames to WAV format."""
    if not os.path.exists(opus_file_path):
        print(f"File not found: {opus_file_path}")
        return False

    decoder = Decoder(sample_rate, channels)
    with open(opus_file_path, 'rb') as f:
        pcm_data = []
        frame_count = 0
        while True:
            length_bytes = f.read(4)
            if not length_bytes:
                print("End of file reached.")
                break
            if len(length_bytes) < 4:
                print("Incomplete length prefix at the end of the file.")
                break

            frame_length = struct.unpack('<I', length_bytes)[0]
            opus_data = f.read(frame_length)
            if len(opus_data) < frame_length:
                print(f"Unexpected end of file at frame {frame_count}.")
                break
            try:
                pcm_frame = decoder.decode(opus_data, frame_size=frame_size)
                pcm_data.append(pcm_frame)
                frame_count += 1
            except Exception as e:
                print(f"Error decoding frame {frame_count}: {e}")
                break
        if pcm_data:
            pcm_bytes = b''.join(pcm_data)
            with wave.open(wav_file_path, 'wb') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 16-bit audio
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_bytes)
            print(f"Decoded audio saved to {wav_file_path}")
            return True
        else:
            print("No PCM data was decoded.")
            return False


def get_timestamp_from_path(path: str):
    timestamp = int(path.split('/')[-1].split('_')[-1].split('.')[0])
    if timestamp > 1e10:
        return int(timestamp / 1000)
    return timestamp


def retrieve_file_paths(files: List[UploadFile], uid: str):
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    paths = []
    for file in files:
        filename = file.filename
        # Validate the file is .bin and contains a _$timestamp.bin, if not, 400 bad request
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}")
        if '_' not in filename:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, missing timestamp")
        try:
            timestamp = get_timestamp_from_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        time = datetime.fromtimestamp(timestamp)
        if time > datetime.now() or time < datetime(2024, 1, 1):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        path = f"{directory}{filename}"
        try:
            with open(path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            paths.append(path)
        except Exception as e:
            if os.path.exists(path):
                os.remove(path)
            raise HTTPException(status_code=500, detail=f"Failed to write file {filename}: {str(e)}")
    return paths


def decode_files_to_wav(files_path: List[str]):
    wav_files = []
    for path in files_path:
        wav_path = path.replace('.bin', '.wav')
        filename = os.path.basename(path)
        frame_size = 160  # Default frame size
        match = re.search(r'_fs(\d+)', filename)
        if match:
            try:
                frame_size = int(match.group(1))
                print(f"Found frame size {frame_size} in filename: {filename}")
            except ValueError:
                print(f"Invalid frame size format in filename: {filename}, using default {frame_size}")

        success = decode_opus_file_to_wav(path, wav_path, frame_size=frame_size)
        if not success:
            continue

        try:
            aseg = AudioSegment.from_wav(wav_path)
        except Exception as e:
            print(e)
            raise HTTPException(status_code=400, detail=f"Invalid file format {path}, {e}")

        if aseg.duration_seconds < 1:
            os.remove(wav_path)
            continue
        wav_files.append(wav_path)
        if os.path.exists(path):
            os.remove(path)
    return wav_files


def retrieve_vad_segments(path: str, segmented_paths: set):
    start_timestamp = get_timestamp_from_path(path)
    voice_segments = vad_is_empty(path, return_segments=True, cache=True)

    segments = []

    for i, segment in enumerate(voice_segments):
        if segments and (segment['start'] - segments[-1]['end']) < 120:
            segments[-1]['end'] = segment['end']
        else:
            segments.append(segment)

    print(path, len(segments))

    aseg = AudioSegment.from_wav(path)
    path_dir = '/'.join(path.split('/')[:-1])
    for i, segment in enumerate(segments):
        if (segment['end'] - segment['start']) < 1:
            continue
        segment_timestamp = start_timestamp + segment['start']
        segment_path = f'{path_dir}/{segment_timestamp}.wav'
        segment_aseg = aseg[segment['start'] * 1000 : segment['end'] * 1000]
        segment_aseg.export(segment_path, format='wav')
        segmented_paths.add(segment_path)


def _reprocess_conversation_after_update(uid: str, conversation_id: str, language: str):
    """
    Reprocess a conversation after new segments have been added.
    This checks if the conversation should still be discarded and regenerates
    the summary/structured data if it now has sufficient content.
    """
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    if not conversation_data:
        print(f'Conversation {conversation_id} not found for reprocessing')
        return

    conversation = Conversation(**conversation_data)

    process_conversation(
        uid=uid,
        language_code=language or 'en',
        conversation=conversation,
        force_process=True,
        is_reprocess=True,
    )

    print(f'Successfully reprocessed conversation {conversation_id}')


def process_segment(path: str, uid: str, response: dict, source: ConversationSource = ConversationSource.omi):
    try:
        with open(path, 'rb') as audio_file:
            audio_data = audio_file.read()
        
        words, language = _transcribe_with_deepgram(audio_data)
        
        transcript_segments: List[TranscriptSegment] = _convert_deepgram_words_to_segments(words) if words else []
        
        if not transcript_segments:
            print(f'Failed to get transcript segments from Deepgram for {path}')
            return

        timestamp = get_timestamp_from_path(path)
        segment_end_timestamp = timestamp + transcript_segments[-1].end
        closest_memory = get_closest_conversation_to_timestamps(uid, timestamp, segment_end_timestamp)

        if not closest_memory:
            started_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            finished_at = datetime.fromtimestamp(segment_end_timestamp, tz=timezone.utc)
            create_memory = CreateConversation(
                started_at=started_at,
                finished_at=finished_at,
                transcript_segments=transcript_segments,
                source=source,
            )
            created = process_conversation(uid, language, create_memory)
            response['new_memories'].add(created.id)
        else:
            transcript_segments = [s.dict() for s in transcript_segments]

            for segment in transcript_segments:
                segment['timestamp'] = timestamp + segment['start']
            for segment in closest_memory['transcript_segments']:
                segment['timestamp'] = closest_memory['started_at'].timestamp() + segment['start']

            segments = closest_memory['transcript_segments'] + transcript_segments
            segments.sort(key=lambda x: x['timestamp'])

            for i, segment in enumerate(segments):
                duration = segment['end'] - segment['start']
                segment['start'] = segment['timestamp'] - closest_memory['started_at'].timestamp()
                segment['end'] = segment['start'] + duration

            last_segment_end = segments[-1]['end'] if segments else 0
            new_finished_at = datetime.fromtimestamp(
                closest_memory['started_at'].timestamp() + last_segment_end, tz=timezone.utc
            )

            if new_finished_at < closest_memory['finished_at']:
                new_finished_at = closest_memory['finished_at']

            for segment in segments:
                segment.pop('timestamp')

            response['updated_memories'].add(closest_memory['id'])
            update_conversation_segments(uid, closest_memory['id'], segments, finished_at=new_finished_at)

            if closest_memory.get('discarded', False):
                print(f'Conversation {closest_memory["id"]} was discarded, checking if it should be reprocessed')
                _reprocess_conversation_after_update(uid, closest_memory['id'], language)
    
    except Exception as e:
        print(f'Error processing segment {path}: {str(e)}')
        raise


@router.post("/v1/sync-local-files")
async def sync_local_files(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    source = ConversationSource.omi
    for f in files:
        if f.filename and 'limitless' in f.filename.lower():
            source = ConversationSource.limitless
            break

    paths = retrieve_file_paths(files, uid)
    wav_paths = decode_files_to_wav(paths)

    def chunk_threads(threads):
        chunk_size = 5
        for i in range(0, len(threads), chunk_size):
            [t.start() for t in threads[i : i + chunk_size]]
            [t.join() for t in threads[i : i + chunk_size]]

    segmented_paths = set()
    threads = [threading.Thread(target=retrieve_vad_segments, args=(path, segmented_paths)) for path in wav_paths]
    chunk_threads(threads)

    print('sync_local_files len(segmented_paths)', len(segmented_paths))

    response = {'updated_memories': set(), 'new_memories': set()}
    threads = [
        threading.Thread(
            target=process_segment,
            args=(
                path,
                uid,
                response,
                source,
            ),
        )
        for path in segmented_paths
    ]
    chunk_threads(threads)

    return response