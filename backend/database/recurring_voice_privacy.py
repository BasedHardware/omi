"""Recurring transcript IDs are revocable pointers; opt-out erases stored pointers."""

from database import transcript_pointer

from google.cloud import firestore

from database import recurring_voices, transcript_pointer
from database.legal_holds import external_write_fence
from utils.observability.fallback import record_fallback

SCRUB_PAGE_SIZE = 100


def filter_processing_write(transaction, user, data):
    """Fence a late processing save against opt-out and profile revocation.

    The owner/profile reads share the transcript write's transaction. Either
    the save wins and the opt-out scrub erases it, or the save observes revoked
    authority (including on retry) and cannot restore a scrubbed pointer.
    """
    from database import conversations

    if 'transcript_segments' not in data:
        return
    segments = conversations.decode_transcript_segments_blob(
        user.id,
        data['transcript_segments'],
        bool(data.get('transcript_segments_compressed')),
        require_decryption=True,
    )
    if not any('recurring_voice_id' in s for s in segments):
        return
    allowed = recurring_voices.active_ids(transaction, user)
    changed = False
    for segment in segments:
        if 'recurring_voice_id' in segment and segment['recurring_voice_id'] not in allowed:
            segment.pop('recurring_voice_id')
            changed = True
    if changed:
        data['transcript_segments'] = conversations._protect_json_value(  # pyright: ignore[reportPrivateUsage]
            segments, user.id, data.get('data_protection_level', 'standard')
        )
        data['transcript_segments_compressed'] = True


def filter_segments(uid, segments, *, firestore_client=None):
    """Read boundary: never expose a stale, expired or rejected recurring link."""
    if not any(isinstance(s, dict) and s.get('recurring_voice_id') for s in segments):
        return
    try:
        allowed = recurring_voices.suggestable_ids(uid, firestore_client=firestore_client)
    except Exception:
        allowed = set()
        record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
    for segment in segments:
        if isinstance(segment, dict) and segment.get('recurring_voice_id') not in allowed:
            segment.pop('recurring_voice_id', None)


def scrub_transcripts(uid, *, firestore_client):
    """Opt-out cleanup: page IDs, then re-read/write one bounded document per transaction.

    Retries start from the beginning and are idempotent. A concurrent edit is
    re-read rather than overwritten; a wipe fences the write. Consent/profile
    readers revoke links immediately, including while this sweep is running.
    Processing saves validate authority in their write transaction, so a save
    after this scan passed its document cannot put the pointer back.
    """
    from database import conversations

    client = firestore_client
    user = client.collection('users').document(uid)
    query = user.collection('conversations').order_by('__name__').select([]).limit(SCRUB_PAGE_SIZE)
    cursor = None
    while True:
        page = list((query.start_after(cursor) if cursor is not None else query).stream())
        if not page:
            return
        for snapshot in page:

            @firestore.transactional
            def scrub(transaction):
                with external_write_fence(uid, transaction=transaction, firestore_client=client):
                    raw = snapshot.reference.get(transaction=transaction).to_dict()
                    if not raw or 'transcript_segments' not in raw:
                        return
                    # Decode the stored blob, without reader filtering or identity
                    # canonicalization: only the recurring pointer is erased.
                    try:
                        segments = conversations.decode_transcript_segments_blob(
                            uid,
                            raw['transcript_segments'],
                            bool(raw.get('transcript_segments_compressed')),
                            require_decryption=True,
                        )
                    except (transcript_pointer.TranscriptBlobAbsent, transcript_pointer.TranscriptShredded):
                        return
                    if not any('recurring_voice_id' in s for s in segments):
                        return
                    for segment in segments:
                        segment.pop('recurring_voice_id', None)
                    transaction.update(
                        snapshot.reference,
                        {
                            'transcript_segments': conversations._protect_json_value(  # pyright: ignore[reportPrivateUsage]
                                segments, uid, raw.get('data_protection_level', 'standard')
                            ),
                            'transcript_segments_compressed': True,
                        },
                    )

            transcript_pointer.run_preloaded_transactional(client, scrub)
        if len(page) < SCRUB_PAGE_SIZE:
            return
        cursor = page[-1]
