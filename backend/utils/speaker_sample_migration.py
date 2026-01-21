"""
Centralized speaker sample migration utility.

Provides functions for:
- Verifying and transcribing speech samples
- Migrating v1 samples to v2 (with transcripts)
- Downloading and deleting samples from storage
"""

import asyncio
from typing import Optional, Tuple

from google.cloud import storage
from google.cloud.exceptions import NotFound

from database import users as users_db
from utils.other.storage import speech_profiles_bucket, storage_client
from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes
from utils.stt.speaker_embedding import extract_embedding_from_bytes
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
    bucket = storage_client.bucket(speech_profiles_bucket)
    blob = bucket.blob(sample_path)
    return blob.download_as_bytes()


def delete_sample_from_storage(sample_path: str) -> bool:
    """
    Delete speech sample from GCS.

    Args:
        sample_path: GCS path to the sample

    Returns:
        True if deleted, False if not found
    """
    bucket = storage_client.bucket(speech_profiles_bucket)
    blob = bucket.blob(sample_path)
    try:
        blob.delete()
        return True
    except NotFound:
        return False


async def migrate_person_samples_v1_to_v2(uid: str, person: dict) -> dict:
    """
    Migrate person's speech samples from v1 to v2.

    v1: Only speech_samples (paths), no transcripts
    v2: speech_samples + speech_sample_transcripts (parallel arrays)

    Samples that fail quality checks are DROPPED along with speaker_embedding.

    Args:
        uid: User ID
        person: Person dict with 'id', 'speech_samples', 'speech_samples_version', etc.

    Returns:
        Updated person dict with migrated fields
    """
    version = person.get('speech_samples_version', 1)
    if version >= 2:
        return person

    samples = person.get('speech_samples', [])
    if not samples:
        users_db.update_person_speech_samples_version(uid, person['id'], 2)
        person['speech_samples_version'] = 2
        person['speech_sample_transcripts'] = []
        return person

    person_id = person['id']
    valid_samples = []
    valid_transcripts = []

    for sample_path in samples:
        try:
            audio_bytes = await asyncio.to_thread(download_sample_audio, sample_path)
        except NotFound:
            print(f"Sample not found in storage, skipping: {sample_path}", uid, person_id)
            continue
        except Exception as e:
            print(f"Error downloading sample {sample_path}: {e}", uid, person_id)
            continue

        transcript, is_valid, reason = await verify_and_transcribe_sample(audio_bytes, 16000)

        if is_valid:
            valid_samples.append(sample_path)
            valid_transcripts.append(transcript)
        else:
            print(f"Dropping sample {sample_path}: {reason}", uid, person_id)
            await asyncio.to_thread(delete_sample_from_storage, sample_path)

    new_embedding = None
    if valid_samples:
        try:
            first_sample_audio = await asyncio.to_thread(download_sample_audio, valid_samples[0])
            embedding = await asyncio.to_thread(extract_embedding_from_bytes, first_sample_audio, "sample.wav")
            new_embedding = embedding.flatten().tolist()
        except Exception as e:
            print(f"Error extracting speaker embedding: {e}", uid, person_id)

    users_db.update_person_speech_samples_after_migration(
        uid,
        person_id,
        samples=valid_samples,
        transcripts=valid_transcripts,
        version=2,
        speaker_embedding=new_embedding,
    )

    person['speech_samples'] = valid_samples
    person['speech_sample_transcripts'] = valid_transcripts
    person['speech_samples_version'] = 2
    if new_embedding is not None:
        person['speaker_embedding'] = new_embedding
    elif not valid_samples:
        person['speaker_embedding'] = None

    return person
