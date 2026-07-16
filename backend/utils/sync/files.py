import logging
import os
import re
import shutil
import struct
import wave
from typing import Any, List, Optional

from fastapi import HTTPException, UploadFile

from models.conversation_enums import ConversationSource
from utils.log_sanitizer import sanitize
from utils.request_validation import parse_sync_filename_timestamp
from utils.sync import playback as sync_playback

try:
    from opuslib import Decoder
except Exception as e:
    Decoder = None
    _opus_import_error: Optional[BaseException] = e
else:
    _opus_import_error = None

logger = logging.getLogger(__name__)

MAX_SYNC_FRAME_BYTES = 65536


def _get_opus_decoder_class() -> Any:
    if Decoder is None:
        raise RuntimeError(
            'Opus sync decoding requires opuslib and the native libopus library. '
            'Install the OS-level Opus package before processing .opus sync files.'
        ) from _opus_import_error
    return Decoder


def decode_opus_file_to_wav(
    opus_file_path: str, wav_file_path: str, sample_rate: int = 16000, channels: int = 1, frame_size: int = 160
) -> bool:
    """Decode an Opus file with length-prefixed frames to WAV format.

    Writes directly to WAV file to avoid accumulating all PCM data in memory.
    """
    if not os.path.exists(opus_file_path):
        logger.warning(f"File not found: {sanitize(opus_file_path)}")
        return False

    decoder = _get_opus_decoder_class()(sample_rate, channels)
    frame_count = 0
    corrupt_stream = False

    try:
        with open(opus_file_path, 'rb') as f, wave.open(wav_file_path, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            while True:
                length_bytes = f.read(4)
                if not length_bytes:
                    break
                if len(length_bytes) < 4:
                    logger.warning('Opus decode: truncated length prefix')
                    corrupt_stream = True
                    break

                frame_length = struct.unpack('<I', length_bytes)[0]
                if frame_length == 0 or frame_length > MAX_SYNC_FRAME_BYTES:
                    logger.warning('Opus decode: invalid frame length')
                    corrupt_stream = True
                    break
                opus_data = f.read(frame_length)
                if len(opus_data) < frame_length:
                    logger.warning('Opus decode: truncated frame')
                    corrupt_stream = True
                    break
                try:
                    pcm_frame = decoder.decode(opus_data, frame_size=frame_size)
                    wav_file.writeframes(pcm_frame)
                    frame_count += 1
                except Exception as e:
                    logger.warning('Opus decode: frame failed exception_type=%s', type(e).__name__)
                    corrupt_stream = True
                    break

        if frame_count > 0 and not corrupt_stream:
            logger.info(f"Decoded audio saved to {sanitize(wav_file_path)}")
            return True

        logger.info("No PCM data was decoded.")
        if os.path.exists(wav_file_path):
            os.remove(wav_file_path)
        return False
    except Exception as e:
        logger.error(f"Error during decode: {e}")
        if os.path.exists(wav_file_path):
            os.remove(wav_file_path)
        return False


def get_timestamp_from_path(path: str) -> int | float:
    return parse_sync_filename_timestamp(path)


def retrieve_file_paths(files: List[UploadFile], uid: str) -> List[str]:
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    paths: List[str] = []
    for file in files:
        filename = file.filename
        if not filename:
            raise HTTPException(status_code=400, detail='Uploaded file is missing a filename')
        if os.path.basename(filename) != filename or '/' in filename or '\\' in filename:
            raise HTTPException(
                status_code=400, detail=f"Invalid file format {filename}, path separators are not allowed"
            )
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}")
        if '_' not in filename:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, missing timestamp")
        try:
            get_timestamp_from_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        path = os.path.join(directory, filename)
        try:
            with open(path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            paths.append(path)
        except Exception as e:
            if os.path.exists(path):
                os.remove(path)
            raise HTTPException(status_code=500, detail=f"Failed to write file {filename}: {str(e)}")
    return paths


def get_wav_duration(wav_path: str) -> float:
    """Get WAV file duration without loading entire file into memory."""
    try:
        with wave.open(wav_path, 'rb') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)
    except Exception as e:
        logger.error(f"Error reading WAV duration: {e}")
        return 0.0


def decode_pcm_file_to_wav(
    pcm_file_path: str, wav_file_path: str, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2
) -> bool:
    """Decode a length-prefixed PCM .bin file to WAV.

    The file format is: [4-byte uint32 frame_length][frame_bytes] repeated.
    Each frame contains raw PCM samples (no encoding).
    sample_width: 2 for pcm16, 1 for pcm8.
    """
    try:
        pcm_data = bytearray()
        corrupt_stream = False
        with open(pcm_file_path, 'rb') as f:
            while True:
                length_bytes = f.read(4)
                if not length_bytes:
                    break
                if len(length_bytes) < 4:
                    corrupt_stream = True
                    break
                frame_length = struct.unpack('<I', length_bytes)[0]
                if frame_length == 0 or frame_length > MAX_SYNC_FRAME_BYTES:
                    logger.warning('PCM decode: invalid frame length')
                    corrupt_stream = True
                    break
                frame_data = f.read(frame_length)
                if len(frame_data) < frame_length:
                    corrupt_stream = True
                    break
                if frame_length % (sample_width * channels) != 0:
                    logger.warning('PCM decode: misaligned frame length')
                    corrupt_stream = True
                    break
                pcm_data.extend(frame_data)

        if not pcm_data or corrupt_stream:
            logger.info('PCM decode: stream is empty or malformed')
            pcm_data.clear()
            if os.path.exists(wav_file_path):
                os.remove(wav_file_path)
            return False

        wav_data = sync_playback.pcm_to_wav(
            bytes(pcm_data), sample_rate=sample_rate, channels=channels, sample_width=sample_width
        )
        with open(wav_file_path, 'wb') as f:
            f.write(wav_data)
        pcm_data.clear()
        return True
    except Exception as e:
        logger.error('PCM decode failed exception_type=%s', type(e).__name__)
        if os.path.exists(wav_file_path):
            os.remove(wav_file_path)
        return False


def _is_pcm_codec(filename: str) -> bool:
    """Check if the filename indicates a PCM codec (pcm8 or pcm16)."""
    return '_pcm16_' in filename or '_pcm8_' in filename


def detect_source_from_filenames(filenames: List[Optional[str]]) -> ConversationSource:
    """Detect the conversation source for a /v2/sync-local-files batch from uploaded filenames.

    Keeps the original first-match-wins loop semantics: the first filename that carries a known
    marker sets the source and stops the scan. limitless is checked before phone so a limitless
    file never loses to phone. 'omibatchphone' also covers the 'omibatchphoneauto' offline
    auto-switch variant; 'phonemic' covers the phone-mic WAL fallback uploads. Defaults to omi.
    """
    for filename in filenames:
        if not filename:
            continue
        name = filename.lower()
        if 'limitless' in name:
            return ConversationSource.limitless
        if 'omibatchphone' in name or 'phonemic' in name:
            return ConversationSource.phone
    return ConversationSource.omi


def decode_files_to_wav(files_path: List[str]) -> List[str]:
    wav_files: List[str] = []
    for path in files_path:
        wav_path = path.replace('.bin', '.wav')
        filename = os.path.basename(path)
        frame_size = 160
        match = re.search(r'_fs(\d+)', filename)
        if match:
            try:
                frame_size = int(match.group(1))
                logger.info(f"Found frame size {frame_size} in filename: {filename}")
            except ValueError:
                logger.error(f"Invalid frame size format in filename: {filename}, using default {frame_size}")

        if _is_pcm_codec(filename):
            sample_rate_match = re.search(r'_pcm(?:8|16)_(\d+)_', filename)
            sample_rate = (
                int(sample_rate_match.group(1)) if sample_rate_match else (16000 if '_pcm16_' in filename else 8000)
            )
            sample_width = 1 if '_pcm8_' in filename else 2
            success = decode_pcm_file_to_wav(path, wav_path, sample_rate=sample_rate, sample_width=sample_width)
        else:
            success = decode_opus_file_to_wav(path, wav_path, frame_size=frame_size)

        if not success:
            for decoded_wav in wav_files:
                if os.path.exists(decoded_wav):
                    os.remove(decoded_wav)
            if os.path.exists(path):
                os.remove(path)
            raise HTTPException(status_code=400, detail='Audio decode failed')

        if os.path.exists(path):
            os.remove(path)

        duration = get_wav_duration(wav_path)
        if duration == 0:
            if os.path.exists(wav_path):
                os.remove(wav_path)
            for decoded_wav in wav_files:
                if os.path.exists(decoded_wav):
                    os.remove(decoded_wav)
            raise HTTPException(status_code=400, detail='Invalid audio input')

        # Short, successfully decoded audio is not proof of silence. Preserve it
        # for the authoritative VAD stage instead of silently acknowledging it.
        wav_files.append(wav_path)
    return wav_files
