"""
Speaker sample migration utility.

Provides functions for migrating speaker samples across versions:
- v1 → v2: Add transcripts to samples
- v2 → v3: Regenerate embeddings using /v2/embedding API
- v1 → v3: Full migration (transcripts + new embeddings)

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


async def migrate_person_samples_v2_to_v3(uid: str, person: dict) -> dict:
    """
    Migrate person's speech samples from v2 to v3.

    v2: speech_samples + transcripts with v1 embeddings
    v3: speech_samples + transcripts with v2 embeddings (regenerated)

    Uses in-process lock to prevent concurrent migration for same person.

    Args:
        uid: User ID
        person: Person dict with 'id', 'speech_samples', 'speech_samples_version', etc.

    Returns:
        Updated person dict with migrated fields
    """
    version = person.get('speech_samples_version', 1)
    if version >= 3:
        return person
    if version < 2:
        # Need v1→v2 first
        return person

    person_id = person['id']
    lock = await _get_migration_lock(uid, person_id)

    async with lock:
        # Re-check version inside lock (another call may have migrated)
        fresh_person = users_db.get_person(uid, person_id)
        if fresh_person and fresh_person.get('speech_samples_version', 1) >= 3:
            return fresh_person

        samples = person.get('speech_samples', [])
        if not samples:
            # No samples, just update version
            users_db.update_person_speech_samples_version(uid, person_id, 3)
            person['speech_samples_version'] = 3
            return person

        # Regenerate embedding from the first (latest) sample using v2/embedding API
        new_embedding = None
        try:
            first_sample_audio = await asyncio.to_thread(download_sample_audio, samples[0])
            embedding = await asyncio.to_thread(extract_embedding_from_bytes, first_sample_audio, "sample.wav")
            new_embedding = embedding.flatten().tolist()
        except NotFound:
            # Sample missing - don't advance to v3 to avoid caching stale v1 embedding
            print(f"First sample not found during v2→v3 migration, skipping: {samples[0]}", uid, person_id)
            return person
        except Exception as e:
            print(f"Error extracting speaker embedding during v2→v3 migration: {e}", uid, person_id)
            # Transient error, don't migrate yet
            return person

        # Update version and embedding
        users_db.update_person_speech_samples_after_migration(
            uid,
            person_id,
            samples=person.get('speech_samples', []),
            transcripts=person.get('speech_sample_transcripts', []),
            version=3,
            speaker_embedding=new_embedding,
        )

        person['speech_samples_version'] = 3
        person['speaker_embedding'] = new_embedding

        return person


async def migrate_person_samples_v1_to_v3(uid: str, person: dict) -> dict:
    """
    Migrate person's speech samples from v1 to v3.

    This is a composite migration: v1 → v2 → v3.

    v1: Only speech_samples (paths), no transcripts, v1 embeddings
    v3: speech_samples + transcripts with v2 embeddings

    Args:
        uid: User ID
        person: Person dict with 'id', 'speech_samples', 'speech_samples_version', etc.

    Returns:
        Updated person dict with migrated fields
    """
    version = person.get('speech_samples_version', 1)
    if version >= 3:
        return person

    # First do v1→v2 if needed
    if version < 2:
        person = await migrate_person_samples_v1_to_v2(uid, person)
        # Check if v1→v2 succeeded
        if person.get('speech_samples_version', 1) < 2:
            return person  # Transient failure, retry later

    # Now do v2→v3
    return await migrate_person_samples_v2_to_v3(uid, person)


async def maybe_migrate_person_samples(uid: str, person: dict) -> dict:
    """
    Migrate person's speech samples to v3 if needed.

    Checks speech_samples_version and triggers appropriate migration:
    - v1 → v3 (composite through v2)
    - v2 → v3

    Args:
        uid: User ID
        person: Person dict

    Returns:
        Updated person dict (may be unchanged if already v3 or migration fails)
    """
    version = person.get('speech_samples_version', 1)
    if version >= 3:
        return person

    if version == 1:
        return await migrate_person_samples_v1_to_v3(uid, person)
    elif version == 2:
        return await migrate_person_samples_v2_to_v3(uid, person)

    return person
