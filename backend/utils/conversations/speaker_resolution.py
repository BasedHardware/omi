"""Resolve a conversation's speakers from its stored audio before processing reads them.

Processing (summary, memories, owner attribution, speaker prompts) and every
client read ``speaker_id`` as "one voice". Capture cannot promise that: its
numbering restarts per connection, provider, and uploaded chunk. This stage
embeds each segment's audio, re-diarizes the whole conversation
(``utils.stt.conversation_speakers``), and rewrites the in-memory transcript so
the processing write persists one id per voice plus ``speaker_resolution``.

Embeddings are cached beside the audio (encrypted), so a conversation that
grows through dozens of sync updates embeds each segment once. Everything here
fails open: without audio, the diarizer, or time budget, processing continues
on capture's ids and ``speaker_resolution`` says whether those ids can be counted.
"""

from __future__ import annotations

import bisect
import json
import logging
import os
import struct
import time
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx
import numpy as np

import database.conversations as conversations_db
import database.users as users_db
from models.conversation import Conversation, ConversationSpeakers
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from utils.metrics import OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL, OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES
from utils.observability.fallback import record_fallback
from utils.other.storage import (
    download_speaker_embedding_cache,
    iter_audio_chunk_pcm,
    upload_speaker_embedding_cache,
)
from utils.speaker_tag_prompts.clips import pcm_to_wav, trim_pcm16
from utils.stt.conversation_speakers import (
    MIN_EMBED_SECONDS,
    OWNER_IDENTITY,
    RESOLUTION_VERSION,
    Identity,
    resolve_conversation_speakers,
    significant_capture_speaker_ids,
)
from utils.stt.speaker_embedding import extract_embedding_from_bytes, speaker_embedding_configured
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL
from utils.stt.voiceprints import usable_person_voiceprint

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# Long segments often hold more than one voice; the middle is the most representative.
MAX_CLIP_SECONDS = 15.0
EMBED_TIMEOUT_SECONDS = 10.0
# Consecutive embedding failures that mean the diarizer is down, not one bad clip.
MAX_CONSECUTIVE_EMBED_FAILURES = 3
CACHE_FORMAT_VERSION = 1
MATCH_SOURCE = 'conversation_voice'
# Participants are only counted once voice evidence placed this much of the speech.
MIN_RESOLVED_COVERAGE = 0.9


def resolution_enabled() -> bool:
    return os.getenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'true').strip().lower() != 'false'


def _budget_seconds() -> float:
    return float(os.getenv('CONVERSATION_SPEAKER_RESOLUTION_BUDGET_SECONDS', '45'))


def _max_new_embeddings() -> int:
    return int(os.getenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '1500'))


# --- embedding cache ---------------------------------------------------------

CacheEntries = Dict[str, Tuple[float, np.ndarray]]


def encode_cache(entries: CacheEntries) -> bytes:
    ids = list(entries)
    header = json.dumps(
        {
            'v': CACHE_FORMAT_VERSION,
            'ids': ids,
            'durations': [round(entries[i][0], 3) for i in ids],
            'dim': int(entries[ids[0]][1].size) if ids else 0,
        }
    ).encode()
    matrix = np.vstack([entries[i][1].reshape(1, -1) for i in ids]).astype('<f2').tobytes() if ids else b''
    return struct.pack('>I', len(header)) + header + matrix


def decode_cache(data: Optional[bytes]) -> CacheEntries:
    if not data or len(data) < 4:
        return {}
    (length,) = struct.unpack('>I', data[:4])
    header = json.loads(data[4 : 4 + length])
    if header.get('v') != CACHE_FORMAT_VERSION or not header.get('ids'):
        return {}
    dim = int(header['dim'])
    matrix = np.frombuffer(data[4 + length :], dtype='<f2').astype(np.float32).reshape(len(header['ids']), dim)
    return {sid: (float(d), matrix[i]) for i, (sid, d) in enumerate(zip(header['ids'], header['durations']))}


# --- inputs ------------------------------------------------------------------


def _started_at(conversation: Conversation) -> Optional[float]:
    moment: Optional[datetime] = conversation.started_at or conversation.created_at
    return moment.timestamp() if moment else None


def _duration(segment: TranscriptSegment) -> float:
    return max(0.0, float(segment.end) - float(segment.start))


def _load_voiceprints(uid: str) -> Dict[str, np.ndarray]:
    prints: Dict[str, np.ndarray] = {}
    owner = users_db.get_user_speaker_embedding(uid)
    if owner:
        prints[OWNER_IDENTITY] = np.asarray(owner, dtype=np.float32)
    for person in users_db.get_people(uid) or []:
        embedding = usable_person_voiceprint(person)
        if embedding and person.get('id'):
            prints[person['id']] = np.asarray(embedding, dtype=np.float32)
    return prints


def _manual_speakers(receipt: Mapping[str, Any]) -> Dict[int, Identity]:
    """Receipt speaker entries as identities; a key labeled neither owner nor person stays its own voice."""
    speakers: Dict[int, Identity] = {}
    for key, entry in (receipt.get('speakers') or {}).items():
        try:
            speaker_id = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, Mapping):
            continue
        if entry.get('is_user'):
            speakers[speaker_id] = Identity(is_user=True, person_id=None)
        elif entry.get('person_id'):
            speakers[speaker_id] = Identity(is_user=False, person_id=str(entry['person_id']))
        else:
            speakers[speaker_id] = Identity(is_user=False, person_id=None, anonymous_key=speaker_id)
    return speakers


def _embed_missing(
    uid: str,
    conversation: Conversation,
    pending: List[TranscriptSegment],
    cache: CacheEntries,
    deadline: float,
) -> Tuple[int, str]:
    """Embed ``pending`` segments from stored audio into ``cache``; returns (count, stop reason)."""
    started_at = _started_at(conversation)
    if started_at is None or not pending:
        return 0, 'none'
    # Chunk placement bisects on midpoints, so order by midpoint, not start.
    pending = sorted(pending, key=lambda s: s.start + s.end)
    midpoints = [started_at + (s.start + s.end) / 2.0 for s in pending]
    done: set[str] = set()
    limit = _max_new_embeddings()
    embedded = 0
    failures = 0

    def wanted(start: float, next_start: Optional[float]) -> bool:
        index = bisect.bisect_left(midpoints, start)
        return index < len(midpoints) and (next_start is None or midpoints[index] < next_start)

    with httpx.Client(timeout=EMBED_TIMEOUT_SECONDS) as client:
        for chunk_start, pcm in iter_audio_chunk_pcm(uid, conversation.id, wanted, sample_rate=SAMPLE_RATE):
            chunk_end = chunk_start + len(pcm) / (SAMPLE_RATE * 2)
            first = bisect.bisect_left(midpoints, chunk_start)
            last = bisect.bisect_left(midpoints, chunk_end)
            for segment in pending[first:last]:
                segment_id = segment.id
                if segment_id is None or segment_id in done:
                    continue
                if time.monotonic() > deadline:
                    return embedded, 'budget'
                if embedded >= limit:
                    return embedded, 'max_embeddings'
                begin = max(started_at + segment.start, chunk_start)
                end = min(started_at + segment.end, chunk_end)
                if end - begin > MAX_CLIP_SECONDS:
                    middle = (begin + end) / 2.0
                    begin, end = middle - MAX_CLIP_SECONDS / 2.0, middle + MAX_CLIP_SECONDS / 2.0
                if end - begin < MIN_EMBED_SECONDS:
                    continue
                clip = trim_pcm16(pcm, SAMPLE_RATE, begin - chunk_start, end - chunk_start)
                try:
                    vector = extract_embedding_from_bytes(
                        pcm_to_wav(clip, SAMPLE_RATE), client=client, timeout=EMBED_TIMEOUT_SECONDS
                    )
                except Exception as error:
                    failures += 1
                    logger.warning(
                        'event=conversation_speaker_embed outcome=failed exception_type=%s', type(error).__name__
                    )
                    if failures >= MAX_CONSECUTIVE_EMBED_FAILURES:
                        return embedded, 'diarizer_unavailable'
                    continue
                failures = 0
                cache[segment_id] = (_duration(segment), np.asarray(vector, dtype=np.float32).reshape(-1))
                done.add(segment_id)
                embedded += 1
    return embedded, 'complete'


# --- stage -------------------------------------------------------------------


def _capture_trusted(segments: List[TranscriptSegment]) -> bool:
    """One capture scope means one diarization, so its ids already name voices."""
    scopes = {s.speaker_id_scope for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL}
    return len(scopes) <= 1


def _audio_aligned(conversation: Conversation) -> bool:
    """Whether segment times address the stored audio: every capture scope is a sync chunk.

    Sync segments are timed from the uploaded file that also becomes the stored
    chunk, so they line up exactly. Live ``started_at`` can drift minutes from the
    arrival-stamped chunks until the capture-position clock lands
    (``omi-knowledge-base/projects/audio-timeline``); embedding misplaced audio
    would merge the wrong voices, so live scopes are not resolved yet. A
    ``conversation:`` scope is this stage's own output, written only after an
    aligned resolution.
    """
    own = f'conversation:{conversation.id}'
    return all(
        (s.speaker_id_scope or '').startswith('sync:') or s.speaker_id_scope == own
        for s in conversation.transcript_segments
        if s.speaker_id != OMI_SPEAKER_ID_SENTINEL
    )


def _without_resolution(conversation: Conversation, outcome: str) -> None:
    segments = conversation.transcript_segments
    if _capture_trusted(segments):
        conversation.speaker_resolution = ConversationSpeakers(
            status='capture',
            version=RESOLUTION_VERSION,
            participant_speaker_ids=significant_capture_speaker_ids(segments),
        )
    else:
        conversation.speaker_resolution = ConversationSpeakers(status='unavailable', version=RESOLUTION_VERSION)
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL.labels(outcome=outcome).inc()


def _apply(conversation: Conversation, speaker_ids: Mapping[str, int], identities: Mapping[int, Identity]) -> None:
    scope = f'conversation:{conversation.id}'
    for segment in conversation.transcript_segments:
        new_id = speaker_ids.get(segment.id) if segment.id else None
        if new_id is None:
            continue
        segment.assign_resolved_speaker(new_id, scope)
        identity = identities.get(new_id)
        if identity is not None:
            segment.is_user = identity.is_user
            segment.person_id = identity.person_id
            segment.speaker_identity_status = (
                SpeakerIdentityStatus.user if identity.is_user else SpeakerIdentityStatus.not_user
            )
            segment.speaker_match_source = MATCH_SOURCE
        elif segment.speaker_match_source == MATCH_SOURCE:
            # A previous resolution's voice decision no longer holds.
            segment.is_user = False
            segment.person_id = None
            segment.speaker_identity_status = SpeakerIdentityStatus.unknown
            segment.speaker_match_source = None


def resolve_speakers_for_processing(uid: str, conversation: Any) -> None:
    """Rewrite ``conversation``'s speaker ids to one per voice; never raises."""
    if not resolution_enabled() or not isinstance(conversation, Conversation) or not conversation.transcript_segments:
        return
    began = time.monotonic()
    try:
        _resolve(uid, conversation, deadline=began + _budget_seconds())
    except Exception as error:
        record_fallback(
            component='other',
            from_mode='conversation_speaker_resolution',
            to_mode='capture_speaker_ids',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.warning(
            'event=conversation_speaker_resolution outcome=failed uid=%s conversation=%s exception_type=%s',
            uid,
            conversation.id,
            type(error).__name__,
        )
        _without_resolution(conversation, 'failed')


def _resolve(uid: str, conversation: Conversation, *, deadline: float) -> None:
    began = time.monotonic()
    segments = conversation.transcript_segments
    input_ids = len({s.speaker_id for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL})
    if not conversation.private_cloud_sync_enabled or not speaker_embedding_configured():
        _without_resolution(conversation, 'no_audio')
        return
    if not _audio_aligned(conversation):
        _without_resolution(conversation, 'unaligned_audio')
        return

    cache = decode_cache(download_speaker_embedding_cache(uid, conversation.id))
    live_ids = {s.id for s in segments}
    stale = [sid for sid in cache if sid not in live_ids]
    for sid in stale:
        del cache[sid]
    pending = [
        s
        for s in segments
        if s.speaker_id != OMI_SPEAKER_ID_SENTINEL
        and _duration(s) >= MIN_EMBED_SECONDS
        and (s.id not in cache or abs(cache[s.id][0] - _duration(s)) > 0.25 * max(_duration(s), 1e-3))
    ]
    new_embeddings, stop = _embed_missing(uid, conversation, pending, cache, deadline)
    if new_embeddings or stale:
        upload_speaker_embedding_cache(uid, conversation.id, encode_cache(cache))

    receipt = conversations_db.get_manual_speaker_receipt(uid, conversation.id)
    resolution = resolve_conversation_speakers(
        segments,
        {sid: vector for sid, (_, vector) in cache.items()},
        manual_speakers=_manual_speakers(receipt),
        voiceprints=_load_voiceprints(uid),
    )
    if resolution is None:
        _without_resolution(conversation, 'no_embeddings')
        return

    _apply(conversation, resolution.speaker_ids, resolution.voice_identities)
    if resolution.coverage >= MIN_RESOLVED_COVERAGE:
        conversation.speaker_resolution = ConversationSpeakers(
            status='resolved', version=RESOLUTION_VERSION, participant_speaker_ids=resolution.significant_speaker_ids
        )
    else:
        # Voices found so far are applied, but the rest of the conversation is
        # still capture's numbering; the next processing run resumes from the cache.
        conversation.speaker_resolution = ConversationSpeakers(status='unavailable', version=RESOLUTION_VERSION)
    outcome = 'resolved' if resolution.coverage >= MIN_RESOLVED_COVERAGE else f'partial_{stop}'
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL.labels(outcome=outcome).inc()
    OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES.labels(stage='input').observe(input_ids)
    OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES.labels(stage='resolved').observe(resolution.stats['voices'])
    logger.info(
        'event=conversation_speaker_resolution outcome=%s uid=%s conversation=%s segments=%d input_ids=%d '
        'voices=%d participants=%d embedded=%d new_embeddings=%d voice_identities=%d coverage=%.2f stop=%s seconds=%.1f',
        outcome,
        uid,
        conversation.id,
        len(segments),
        input_ids,
        resolution.stats['voices'],
        len(resolution.significant_speaker_ids),
        resolution.embedded_segments,
        new_embeddings,
        len(resolution.voice_identities),
        resolution.coverage,
        stop,
        time.monotonic() - began,
    )
