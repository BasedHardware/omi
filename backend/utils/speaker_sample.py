"""
Speaker sample verification and storage utilities.

Provides functions for:
- Verifying and transcribing speech samples
- Downloading samples from GCS
- Deleting samples from GCS
"""

import asyncio
from typing import Optional, Tuple

from utils.other.storage import delete_speech_profile_blob, download_speech_profile_bytes
from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes
from utils.text_utils import compute_text_similarity

MIN_WORDS = 5
MIN_SIMILARITY = 0.6
MIN_DOMINANT_SPEAKER_RATIO = 0.7


async def verify_and_transcribe_sample(
    audio_bytes: bytes,
    sample_rate: int,
    expected_text: Optional[str] = None,
) -> Tuple[Optional[str], bool, str]:
    """
    Transcribe audio and verify quality using PR #4291 rules.

    Checks:
    1. Transcription has at least MIN_WORDS words
    2. Dominant speaker accounts for >= MIN_DOMINANT_SPEAKER_RATIO of words (via diarization)
    3. Transcribed text has >= MIN_SIMILARITY with expected text (if provided)

    Args:
        audio_bytes: WAV format audio bytes
        sample_rate: Audio sample rate in Hz
        expected_text: Expected text from the segment for comparison (optional)

    Returns:
        (transcript, is_valid, reason): Tuple of (str or None, bool, str)
    """
    words = await asyncio.to_thread(deepgram_prerecorded_from_bytes, audio_bytes, sample_rate, True)

    if len(words) < MIN_WORDS:
        return None, False, f"insufficient_words: {len(words)}/{MIN_WORDS}"

    speaker_counts = {}
    for word in words:
        speaker = word.get('speaker', 'SPEAKER_00')
        speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1

    total_words = len(words)
    dominant_count = max(speaker_counts.values()) if speaker_counts else 0
    dominant_ratio = dominant_count / total_words if total_words > 0 else 0

    if dominant_ratio < MIN_DOMINANT_SPEAKER_RATIO:
        return None, False, f"multi_speaker: ratio={dominant_ratio:.2f}"

    transcript = ' '.join(w.get('text', '') for w in words)

    if expected_text:
        similarity = compute_text_similarity(transcript, expected_text)
        if similarity < MIN_SIMILARITY:
            return transcript, False, f"text_mismatch: similarity={similarity:.2f}"

    return transcript, True, "ok"


def download_sample_audio(sample_path: str) -> bytes:
    """
    Download speech sample audio from GCS.

    Args:
        sample_path: GCS path to the sample (e.g., '{uid}/people_profiles/{person_id}/{filename}.wav')

    Returns:
        Audio bytes (WAV format)

    Raises:
        NotFound: If the sample doesn't exist
    """
    return download_speech_profile_bytes(sample_path)


def delete_sample_from_storage(sample_path: str) -> bool:
    """
    Delete speech sample from GCS.

    Args:
        sample_path: GCS path to the sample

    Returns:
        True if deleted, False if not found
    """
    return delete_speech_profile_blob(sample_path)
