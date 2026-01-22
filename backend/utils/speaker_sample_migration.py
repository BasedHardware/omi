"""
Speaker sample migration utility.

Provides functions for migrating v1 samples to v2 (with transcripts).
Uses in-process locking to prevent concurrent migrations.
"""

import asyncio

from google.cloud.exceptions import NotFound

from database import users as users_db
from utils.speaker_sample import (
    delete_sample_from_storage,
    download_sample_audio,
    verify_and_transcribe_sample,
)
from utils.stt.speaker_embedding import extract_embedding_from_bytes

# In-process locks to prevent concurrent migration for same person
_migration_locks: dict[tuple[str, str], asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


async def _get_migration_lock(uid: str, person_id: str) -> asyncio.Lock:
    """Get or create a lock for the given uid/person_id pair."""
    key = (uid, person_id)
    async with _locks_lock:
        if key not in _migration_locks:
            _migration_locks[key] = asyncio.Lock()
        return _migration_locks[key]


async def migrate_person_samples_v1_to_v2(uid: str, person: dict) -> dict:
    """
    Migrate person's speech samples from v1 to v2.

    v1: Only speech_samples (paths), no transcripts
    v2: speech_samples + speech_sample_transcripts (parallel arrays)

    Samples that fail quality checks are DROPPED along with speaker_embedding.

    Uses in-process lock to prevent concurrent migration for same person.

    Args:
        uid: User ID
        person: Person dict with 'id', 'speech_samples', 'speech_samples_version', etc.

    Returns:
        Updated person dict with migrated fields
    """
    version = person.get('speech_samples_version', 1)
    if version >= 2:
        return person

    person_id = person['id']
    lock = await _get_migration_lock(uid, person_id)

    async with lock:
        # Re-check version inside lock (another call may have migrated)
        fresh_person = users_db.get_person(uid, person_id)
        if fresh_person and fresh_person.get('speech_samples_version', 1) >= 2:
            return fresh_person

        samples = person.get('speech_samples', [])
        if not samples:
            users_db.update_person_speech_samples_version(uid, person_id, 2)
            person['speech_samples_version'] = 2
            person['speech_sample_transcripts'] = []
            return person

        valid_samples = []
        valid_transcripts = []
        samples_to_delete = []
        has_transient_failures = False

        for sample_path in samples:
            try:
                audio_bytes = await asyncio.to_thread(download_sample_audio, sample_path)
            except NotFound:
                print(f"Sample not found in storage, skipping: {sample_path}", uid, person_id)
                # Mark for removal from Firestore (blob already gone)
                samples_to_delete.append(sample_path)
                continue
            except Exception as e:
                print(f"Error downloading sample {sample_path}: {e}", uid, person_id)
                # Transient download failure - keep sample, skip migration for now
                has_transient_failures = True
                continue

            transcript, is_valid, reason = await verify_and_transcribe_sample(audio_bytes, 16000)

            if is_valid:
                valid_samples.append(sample_path)
                valid_transcripts.append(transcript)
            elif reason.startswith("transcription_failed"):
                # Transient API failure - keep sample, don't migrate yet
                print(f"Transcription failed for {sample_path}, keeping sample: {reason}", uid, person_id)
                has_transient_failures = True
            else:
                # Quality issue - mark for deletion (defer actual delete)
                print(f"Marking sample for deletion {sample_path}: {reason}", uid, person_id)
                samples_to_delete.append(sample_path)

        # Don't commit changes if there were transient failures - retry next time
        if has_transient_failures:
            print(f"Migration incomplete due to transient failures, will retry later", uid, person_id)
            return person

        # Now safe to delete blobs - no transient failures
        for sample_path in samples_to_delete:
            try:
                await asyncio.to_thread(delete_sample_from_storage, sample_path)
            except Exception as e:
                print(f"Failed to delete sample {sample_path}: {e}", uid, person_id)

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
