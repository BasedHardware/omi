"""Recurring transcript IDs are revocable pointers; opt-out erases stored pointers."""

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from google.api_core.exceptions import DeadlineExceeded
from google.cloud import firestore

from database import _client, recurring_voices, rpc_deadline, transcript_pointer
from database.firestore_retry import FIRESTORE_NO_RETRY
from database.legal_holds import external_write_fence
from utils.observability.fallback import record_fallback

SCRUB_PAGE_SIZE = 100
SCRUB_FIELD = 'speaker_recurring_voice_scrub'
READY_AT = f'{SCRUB_FIELD}.ready_at'
SWEEP_SECONDS = 45
CHECKPOINT_SECONDS = 2
MAX_OWNERS_PER_SWEEP = 20

logger = logging.getLogger(__name__)


def scrub_budget_seconds() -> float:
    value = float(os.getenv('PRIVACY_SCRUB_BUDGET_SECONDS', '15'))
    if not math.isfinite(value) or value < 0:
        raise ValueError('PRIVACY_SCRUB_BUDGET_SECONDS must be finite and nonnegative')
    return min(value, SWEEP_SECONDS - 2 * CHECKPOINT_SECONDS)


def new_scrub(version: int, trace_id: str) -> dict:
    return {
        'version': version,
        'cursor': None,
        'ready_at': datetime.now(timezone.utc),
        'trace_id': trace_id,
    }


def log_phase(phase, started, trace_id, *, pages=0, documents=0, reason='none'):
    logger.info(
        'event=recurring_voice_privacy phase=%s elapsed_ms=%d pages=%d documents=%d trace_id=%s reason=%s',
        phase,
        round((rpc_deadline.now() - started) * 1000),
        pages,
        documents,
        trace_id,
        reason,
    )


@dataclass
class ScrubProgress:
    cursor: str | None = None
    pages: int = 0
    documents: int = 0
    done: bool = False


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


def scrub_transcripts(uid, *, firestore_client, progress=None, expected_job=None, one_page=False):
    """Erase revoked pointers transactionally and advance only past processed documents.

    The scheduled worker visits at most one page per slice. Legacy synchronous
    callers keep walking until done. A replay of a completed document reads no
    revoked pointers and makes no transcript write.
    """
    progress = progress if progress is not None else ScrubProgress()
    client = firestore_client
    user = client.collection('users').document(uid)
    collection = user.collection('conversations')
    query = collection.order_by('__name__').select([]).limit(SCRUB_PAGE_SIZE)
    while True:
        page_query = query
        if progress.cursor is not None:
            page_query = query.start_after({'__name__': collection.document(progress.cursor)})
        stream_options = {'retry': FIRESTORE_NO_RETRY} if rpc_deadline.current() is not None else {}
        page = list(page_query.stream(**stream_options))
        if page:
            progress.pages += 1

        for snapshot in page:
            progress.documents += 1
            if not _scrub_document(client, user, snapshot.reference, expected_job):
                return progress
            progress.cursor = snapshot.id

        progress.done = len(page) < SCRUB_PAGE_SIZE
        if progress.done or one_page:
            return progress


def _scrub_document(client, user, reference, expected_job):
    from database import conversations

    @firestore.transactional
    def scrub(transaction):
        with external_write_fence(user.id, transaction=transaction, firestore_client=client):
            if expected_job is not None:
                owner = user.get(transaction=transaction).to_dict() or {}
                if owner.get(SCRUB_FIELD) != expected_job:
                    return False
            raw = reference.get(transaction=transaction).to_dict()
            if not raw or 'transcript_segments' not in raw:
                return True
            # Decode the stored blob so this edit preserves all other fields.
            try:
                segments = conversations.decode_transcript_segments_blob(
                    user.id,
                    raw['transcript_segments'],
                    bool(raw.get('transcript_segments_compressed')),
                    require_decryption=True,
                )
            except (transcript_pointer.TranscriptBlobAbsent, transcript_pointer.TranscriptShredded):
                return True
            if not any('recurring_voice_id' in s for s in segments):
                return True
            # Re-enrollment may have published new links while cleanup waited.
            # Read authority in this transaction to keep those links intact.
            allowed = recurring_voices.active_ids(transaction, user)
            changed = False
            for segment in segments:
                if 'recurring_voice_id' in segment and segment['recurring_voice_id'] not in allowed:
                    segment.pop('recurring_voice_id')
                    changed = True
            if changed:
                transaction.update(
                    reference,
                    {
                        'transcript_segments': conversations._protect_json_value(  # pyright: ignore[reportPrivateUsage]
                            segments, user.id, raw.get('data_protection_level', 'standard')
                        ),
                        'transcript_segments_compressed': True,
                    },
                )
            return True

    return transcript_pointer.run_preloaded_transactional(client, scrub)


def checkpoint(client, user, job, progress):
    @firestore.transactional
    def save(transaction):
        with external_write_fence(user.id, transaction=transaction, firestore_client=client):
            owner = user.get(transaction=transaction).to_dict() or {}
            if owner.get(SCRUB_FIELD) != job:
                return False
            transaction.update(
                user,
                {
                    SCRUB_FIELD: (
                        firestore.DELETE_FIELD
                        if progress.done
                        else {**job, 'cursor': progress.cursor, 'ready_at': datetime.now(timezone.utc)}
                    )
                },
            )
            return True

    return _client.run_transactional(client, save)


def _resume(client, user, job, deadline):
    started = rpc_deadline.now()
    progress = ScrubProgress(cursor=job['cursor'])
    reason = 'page_limit'
    try:
        with rpc_deadline.rpc_deadline(deadline - CHECKPOINT_SECONDS):
            scrub_transcripts(user.id, firestore_client=client, progress=progress, expected_job=job, one_page=True)
    except (rpc_deadline.RpcDeadlineExceeded, DeadlineExceeded):
        # Persist the last confirmed document, using the reserved time.
        reason = 'deadline'
    except Exception as error:
        # Leave a failed document pending and let other owners take a turn.
        reason = type(error).__name__

    try:
        with rpc_deadline.rpc_deadline(deadline):
            saved = checkpoint(client, user, job, progress)
        if not saved:
            reason = 'superseded'
    except Exception as error:
        saved = False
        reason = type(error).__name__

    done = saved and progress.done
    log_phase(
        'scrub_done' if done else 'scrub_exhausted',
        started,
        job['trace_id'],
        pages=progress.pages,
        documents=progress.documents,
        reason='complete' if done else reason,
    )
    return done


def resume_pending_scrubs(*, firestore_client=None) -> dict:
    budget = scrub_budget_seconds()
    if not budget:
        return {'visited': 0, 'completed': 0}
    client = rpc_deadline.bind_firestore_client(
        firestore_client if firestore_client is not None else _client.get_data_plane_firestore_client()
    )
    deadline = rpc_deadline.now() + SWEEP_SECONDS
    with rpc_deadline.rpc_deadline(deadline - CHECKPOINT_SECONDS):
        query = client.collection('users').order_by(READY_AT).select([SCRUB_FIELD]).limit(MAX_OWNERS_PER_SWEEP)
        page = list(query.stream(retry=FIRESTORE_NO_RETRY))
    visited = completed = 0
    for snapshot in page:
        started = rpc_deadline.now()
        if started + CHECKPOINT_SECONDS >= deadline:
            break
        job = snapshot.to_dict()[SCRUB_FIELD]
        visited += 1
        completed += _resume(client, snapshot.reference, job, min(started + budget + CHECKPOINT_SECONDS, deadline))
    return {'visited': visited, 'completed': completed}
