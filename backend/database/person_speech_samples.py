"""Atomic sample append and transcript alignment for owner-scoped People."""

from datetime import datetime, timezone

from google.cloud.firestore_v1 import transactional

from database.people_generation import bump_people_generation


@transactional
def add_sample_transaction(transaction, person_ref, sample_path, transcript, max_samples):
    """Transaction to atomically add sample and transcript."""
    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False

    person_data = snapshot.to_dict()
    samples = person_data.get('speech_samples', [])

    if len(samples) >= max_samples:
        return False

    samples.append(sample_path)
    update_data = {
        'speech_samples': samples,
        'updated_at': datetime.now(timezone.utc),
    }

    if transcript is not None:
        transcripts = person_data.get('speech_sample_transcripts', [])
        # Ensure transcript array alignment with samples:
        # If we're adding a transcript but existing samples don't have transcripts,
        # pad with empty strings for the existing samples first (Dart expects non-null)
        existing_sample_count = len(samples) - 1  # samples already has new one appended
        if len(transcripts) < existing_sample_count:
            # Pad with empty strings for each existing sample without a transcript
            transcripts.extend([''] * (existing_sample_count - len(transcripts)))
        transcripts.append(transcript)
        update_data['speech_sample_transcripts'] = transcripts
        update_data['speech_samples_version'] = 3

    transaction.update(person_ref, update_data)
    bump_people_generation(transaction, person_ref)
    return True
