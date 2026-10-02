"""Resolve a conversation's speakers from its stored audio before processing reads them.

Processing (summary, memories, owner attribution, speaker prompts) and every
client read ``speaker_id`` as "one voice". Capture cannot promise that: its
numbering restarts per connection, provider, and uploaded chunk. This stage
embeds each segment's audio, re-diarizes the whole conversation
(``utils.stt.conversation_speakers``), and rewrites the in-memory transcript so
the processing write persists one id per voice plus ``speaker_resolution``.

Embeddings are cached beside the audio (encrypted) under provenance and model
stamps, so a conversation that grows through dozens of sync updates reuses
unchanged evidence and recomputes only what a changed source clock or model
invalidates. Everything here
fails open: without audio, the diarizer, or time budget, processing continues
on capture's ids and ``speaker_resolution`` says whether those ids can be counted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, cast

import httpx
import numpy as np

import database.conversations as conversations_db
import database.users as users_db
from models.conversation import Conversation, ConversationSpeakers
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from utils.conversations.audio_placement import MAX_PLACEMENT_REQUEST_SECONDS, locate
from utils.manual_speaker_assignments import apply_manual_assignments, manual_rejected_speakers
from utils.metrics import OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL, OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES
from utils.observability.fallback import record_fallback
from utils.other.audio_chunks import iter_audio_chunk_pcm
from utils.other.storage import (
    download_speaker_embedding_cache,
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
from utils.speaker_permissions import named_speaker_prompts_allowed
from utils.stt.voiceprints import usable_person_voiceprint

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# Long segments often hold more than one voice; the middle is the most representative.
MAX_CLIP_SECONDS = 15.0
EMBED_TIMEOUT_SECONDS = 10.0
# Consecutive embedding failures that mean the diarizer is down, not one bad clip.
MAX_CONSECUTIVE_EMBED_FAILURES = 3
CACHE_FORMAT_VERSION = 2
EMBEDDING_MODEL_VERSION = 'pyannote/wespeaker-voxceleb-resnet34-LM:v2:1'
PLACEMENT_CACHE_VERSION = 1
MATCH_SOURCE = 'conversation_voice'
# Participants are only counted once voice evidence placed this much of the speech.
MIN_RESOLVED_COVERAGE = 0.9


def resolution_enabled() -> bool:
    return os.getenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'true').strip().lower() != 'false'


def _budget_seconds() -> float:
    return float(os.getenv('CONVERSATION_SPEAKER_RESOLUTION_BUDGET_SECONDS', '45'))


def _max_new_embeddings() -> int:
    return int(os.getenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '1500'))


def embedding_model_stamp() -> str:
    return hashlib.sha256(
        json.dumps(
            [
                os.getenv('CONVERSATION_SPEAKER_EMBEDDING_MODEL_VERSION', EMBEDDING_MODEL_VERSION),
                os.getenv('HOSTED_SPEAKER_EMBEDDING_API_URL', '').strip(),
                SAMPLE_RATE,
                MAX_CLIP_SECONDS,
            ]
        ).encode()
    ).hexdigest()


def live_resolution_enabled() -> bool:
    return os.getenv('CONVERSATION_LIVE_SPEAKER_RESOLUTION_ENABLED', 'false').strip().lower() == 'true'


# --- embedding cache ---------------------------------------------------------


@dataclass(frozen=True)
class SegmentPlacement:
    window: Tuple[float, float]
    source_scope: Optional[str]
    input_stamp: str
    source_stamp: str


@dataclass(frozen=True)
class CachedEmbedding:
    duration: float
    vector: Optional[np.ndarray]
    placement: SegmentPlacement
    model_stamp: str


CacheEntries = Dict[str, CachedEmbedding]


def encode_cache(entries: CacheEntries) -> bytes:
    ids = list(entries)
    vectors = [entries[i].vector for i in ids]
    has_vectors = [v is not None for v in vectors]
    dim = next((int(v.size) for v in vectors if v is not None), 0)
    header = json.dumps(
        {
            'v': CACHE_FORMAT_VERSION,
            'ids': ids,
            'durations': [round(entries[i].duration, 3) for i in ids],
            'dim': dim,
            'has_vectors': has_vectors,
            'placements': [
                {
                    'window': [entries[i].placement.window[0], entries[i].placement.window[1]],
                    'source_scope': entries[i].placement.source_scope,
                    'input_stamp': entries[i].placement.input_stamp,
                    'source_stamp': entries[i].placement.source_stamp,
                }
                for i in ids
            ],
            'model_stamps': [entries[i].model_stamp for i in ids],
        }
    ).encode()
    matrix = (
        np.vstack([v.reshape(1, -1) if v is not None else np.zeros((1, dim), dtype=np.float32) for v in vectors])
        .astype('<f2')
        .tobytes()
        if dim
        else b''
    )
    return struct.pack('>I', len(header)) + header + matrix


def decode_cache(data: Optional[bytes]) -> CacheEntries:
    if not data or len(data) < 4:
        return {}
    try:
        (length,) = struct.unpack('>I', data[:4])
        header = json.loads(data[4 : 4 + length])
    except (json.JSONDecodeError, struct.error, UnicodeDecodeError, ValueError):
        return {}
    if not isinstance(header, dict) or header.get('v') != CACHE_FORMAT_VERSION:
        return {}
    ids = header.get('ids')
    durations = header.get('durations')
    has_vectors = header.get('has_vectors')
    placements = header.get('placements')
    model_stamps = header.get('model_stamps')
    dim = header.get('dim')
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(sid, str) for sid in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(durations, list)
        or not isinstance(has_vectors, list)
        or not all(isinstance(has, bool) for has in has_vectors)
        or not isinstance(placements, list)
        or not isinstance(model_stamps, list)
        or not (len(ids) == len(durations) == len(has_vectors) == len(placements) == len(model_stamps))
        or not isinstance(dim, int)
        or isinstance(dim, bool)
        or dim < 0
        or (dim == 0 and any(has_vectors))
    ):
        return {}
    body = data[4 + length :]
    if len(body) != len(ids) * dim * 2:
        return {}
    matrix = np.frombuffer(body, dtype='<f2').astype(np.float32).reshape(len(ids), dim) if dim else None
    entries: CacheEntries = {}
    for index, (sid, duration, has_vector, placement, model_stamp) in enumerate(
        zip(ids, durations, has_vectors, placements, model_stamps)
    ):
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(duration)
            or duration <= 0
            or not isinstance(placement, Mapping)
            or not isinstance(model_stamp, str)
        ):
            return {}
        window = placement.get('window')
        source_scope = placement.get('source_scope')
        input_stamp = placement.get('input_stamp')
        source_stamp = placement.get('source_stamp')
        if (
            not isinstance(window, (list, tuple))
            or len(window) != 2
            or not all(
                isinstance(bound, (int, float)) and not isinstance(bound, bool) and math.isfinite(bound)
                for bound in window
            )
            or window[1] <= window[0]
            or not (source_scope is None or isinstance(source_scope, str))
            or not isinstance(input_stamp, str)
            or not isinstance(source_stamp, str)
        ):
            return {}
        vector: Optional[np.ndarray] = None
        if matrix is not None:
            row = matrix[index]
            if has_vector:
                if not np.all(np.isfinite(row)) or not np.any(row):
                    return {}
                vector = row
            elif np.any(row):
                return {}
        elif has_vector:
            return {}
        entries[sid] = CachedEmbedding(
            duration=float(duration),
            vector=vector,
            placement=SegmentPlacement((float(window[0]), float(window[1])), source_scope, input_stamp, source_stamp),
            model_stamp=model_stamp,
        )
    return entries


_TIMESTAMP_KEYS = frozenset({'started_at', 'ended_at'})


def _epoch_seconds(value: Any) -> Optional[float]:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _epoch_seconds(item) if key in _TIMESTAMP_KEYS else _canonical(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, datetime):
        return _epoch_seconds(value)
    return value


def _stamp_payload(conversation: Mapping[str, Any], segment: Mapping[str, Any]) -> Dict[str, Any]:
    origin = _epoch_seconds(conversation.get('started_at'))
    if origin is None:
        origin = _epoch_seconds(conversation.get('created_at'))
    return {
        'v': PLACEMENT_CACHE_VERSION,
        'conversation': conversation.get('id'),
        'origin': origin,
        'audio_timeline': _canonical(conversation.get('audio_timeline')),
        'audio_files': _canonical(conversation.get('audio_files') or []),
        'segment': {
            key: segment.get(key)
            for key in ('id', 'start', 'end', 'audio_alignment', 'audio_capture_run', 'stt_provider')
        },
        'text': hashlib.sha256(str(segment.get('text') or '').encode()).hexdigest(),
    }


def _input_stamp(conversation: Mapping[str, Any], segment: Mapping[str, Any]) -> str:
    payload = _stamp_payload(conversation, segment)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _source_stamp(conversation: Mapping[str, Any], segment: Mapping[str, Any]) -> str:
    payload = _stamp_payload(conversation, segment)
    payload.pop('audio_files')
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def placement_for_segment(
    conversation: Mapping[str, Any], segment: Mapping[str, Any], cached: Optional[CachedEmbedding] = None
) -> Optional[SegmentPlacement]:
    stamp = _input_stamp(conversation, segment)
    source_stamp = _source_stamp(conversation, segment)
    scope = segment.get('speaker_id_scope')
    if (
        scope == f"conversation:{conversation['id']}"
        and cached is not None
        and cached.placement.source_stamp == source_stamp
    ):
        scope = cached.placement.source_scope
    contributor = dict(segment, speaker_id_scope=scope)
    try:
        start, end = float(segment['start']), float(segment['end'])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(start) or not math.isfinite(end):
        return None
    clip = min(MAX_CLIP_SECONDS, MAX_PLACEMENT_REQUEST_SECONDS)
    if end - start > clip:
        middle = (start + end) / 2.0
        start, end = middle - clip / 2.0, middle + clip / 2.0
    placed = locate(conversation, start, end, segments=[contributor])
    if placed.window is None:
        return None
    window = placed.window
    if not (math.isfinite(window[0]) and math.isfinite(window[1])) or window[1] <= window[0]:
        return None
    return SegmentPlacement(window, scope, stamp, source_stamp)


def cached_embedding_valid(
    conversation: Mapping[str, Any], segment: Mapping[str, Any], cached: CachedEmbedding
) -> bool:
    if cached.vector is None:
        return False
    if cached.model_stamp != embedding_model_stamp():
        return False
    if placement_for_segment(conversation, segment, cached) != cached.placement:
        return False
    vector = np.asarray(cached.vector, dtype=np.float64).reshape(-1)
    if vector.size == 0 or not np.all(np.isfinite(vector)) or not np.any(vector):
        return False
    return bool(math.isfinite(cached.duration) and cached.duration > 0)


# --- inputs ------------------------------------------------------------------


def _started_at(conversation: Conversation) -> Optional[float]:
    moment = conversation.started_at or conversation.created_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _duration(segment: TranscriptSegment) -> float:
    return max(0.0, float(segment.end) - float(segment.start))


def load_voiceprints_for_resolution(uid: str) -> Dict[str, np.ndarray]:
    prints: Dict[str, np.ndarray] = {}
    owner = users_db.get_user_speaker_embedding(uid)
    if owner:
        prints[OWNER_IDENTITY] = np.asarray(owner, dtype=np.float32)
    # Owner recognition is plan-independent: an entitlement read failure fails
    # closed for person prints only, never for the owner's own voiceprint.
    try:
        named_allowed = named_speaker_prompts_allowed(uid)
    except Exception as error:
        logger.warning('event=speaker_resolution_entitlement outcome=failed exception_type=%s', type(error).__name__)
        return prints
    if not named_allowed:
        return prints
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
    for speaker_id in manual_rejected_speakers(receipt):
        speakers[speaker_id] = Identity(is_user=False, person_id=None, anonymous_key=speaker_id)
    return speakers


def _embed_missing(
    uid: str,
    conversation: Conversation,
    pending: List[TranscriptSegment],
    cache: CacheEntries,
    deadline: float,
    placements: Mapping[str, SegmentPlacement],
) -> Tuple[int, str]:
    """Embed ``pending`` segments from stored audio into ``cache``; returns (count, stop reason)."""
    pending = [s for s in pending if s.id is not None and s.id in placements]
    if _started_at(conversation) is None or not pending:
        return 0, 'none'
    # Chunk placement consumes exact windows, so order by window start.
    pending = sorted(pending, key=lambda s: placements[cast(str, s.id)].window[0])
    windows: List[Tuple[Tuple[float, float], str]] = [
        (placements[s.id].window, s.id) for s in pending if s.id is not None
    ]
    by_id = {s.id: s for s in pending if s.id is not None}
    done: set[str] = set()
    failed: set[str] = set()
    cursors: Dict[str, float] = {}
    pieces: Dict[str, List[bytes]] = {}
    limit = _max_new_embeddings()
    embedded = 0
    failures = 0

    def wanted(start: float, next_start: Optional[float]) -> bool:
        if time.monotonic() > deadline or embedded >= limit:
            return False
        bound = next_start if next_start is not None else math.inf
        return any(
            window_start < bound and window_end > start
            for (window_start, window_end), segment_id in windows
            if segment_id not in done and segment_id not in failed
        )

    with httpx.Client(timeout=EMBED_TIMEOUT_SECONDS) as client:
        for chunk_start, pcm in iter_audio_chunk_pcm(uid, conversation.id, wanted, sample_rate=SAMPLE_RATE):
            if time.monotonic() > deadline:
                return embedded, 'budget'
            chunk_end = chunk_start + len(pcm) / (SAMPLE_RATE * 2)
            for (window_start, window_end), segment_id in windows:
                if window_start >= chunk_end:
                    break
                if segment_id in done or segment_id in failed or window_end <= chunk_start:
                    continue
                if time.monotonic() > deadline:
                    return embedded, 'budget'
                if embedded >= limit:
                    return embedded, 'max_embeddings'
                cursor = cursors.get(segment_id, window_start)
                if chunk_start > cursor + 1.0 / SAMPLE_RATE:
                    failed.add(segment_id)
                    continue
                begin = max(cursor, chunk_start)
                end = min(window_end, chunk_end)
                if end <= begin:
                    continue
                clip = trim_pcm16(pcm, SAMPLE_RATE, begin - chunk_start, end - chunk_start)
                pieces.setdefault(segment_id, []).append(clip)
                cursors[segment_id] = begin + len(clip) / (SAMPLE_RATE * 2)
                if cursors[segment_id] + 1.0 / SAMPLE_RATE < window_end:
                    continue
                blob = b''.join(pieces.pop(segment_id))
                expected = int(round((window_end - window_start) * SAMPLE_RATE))
                if abs(len(blob) // 2 - expected) > 1:
                    failed.add(segment_id)
                    continue
                try:
                    vector = extract_embedding_from_bytes(
                        pcm_to_wav(blob, SAMPLE_RATE),
                        client=client,
                        timeout=max(0.001, min(EMBED_TIMEOUT_SECONDS, deadline - time.monotonic())),
                    )
                except Exception as error:
                    failures += 1
                    failed.add(segment_id)
                    logger.warning(
                        'event=conversation_speaker_embed outcome=failed exception_type=%s', type(error).__name__
                    )
                    if failures >= MAX_CONSECUTIVE_EMBED_FAILURES:
                        return embedded, 'diarizer_unavailable'
                    continue
                array = np.asarray(vector, dtype=np.float64).reshape(-1)
                norm = float(np.linalg.norm(array))
                if array.size == 0 or not np.all(np.isfinite(array)) or not math.isfinite(norm) or norm <= 0:
                    failures += 1
                    failed.add(segment_id)
                    logger.warning('event=conversation_speaker_embed outcome=failed exception_type=invalid_vector')
                    if failures >= MAX_CONSECUTIVE_EMBED_FAILURES:
                        return embedded, 'diarizer_unavailable'
                    continue
                failures = 0
                cache[segment_id] = CachedEmbedding(
                    duration=_duration(by_id[segment_id]),
                    vector=(array / norm).astype(np.float32),
                    placement=placements[segment_id],
                    model_stamp=embedding_model_stamp(),
                )
                done.add(segment_id)
                embedded += 1
    if embedded >= limit:
        return embedded, 'max_embeddings'
    if time.monotonic() > deadline:
        return embedded, 'budget'
    return embedded, 'complete'


# --- stage -------------------------------------------------------------------


def _capture_trusted(segments: List[TranscriptSegment]) -> bool:
    """One capture scope means one diarization, so its ids already name voices."""
    scopes = {s.speaker_id_scope for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL}
    return len(scopes) <= 1 and not any((scope or '').startswith('conversation:') for scope in scopes)


def _without_resolution(conversation: Conversation, outcome: str) -> None:
    segments = conversation.transcript_segments
    # Independent sync batches can each accept an owner in isolation. Without
    # conversation audio there is no evidence that their capture IDs name the
    # same voice. Withdraw only automatic claims when several scoped voices
    # claim the owner; the transactional manual receipt is reapplied on write.
    sync_owners = {
        (segment.speaker_id_scope, segment.speaker_id)
        for segment in segments
        if segment.is_user and (segment.speaker_id_scope or '').startswith('sync:')
    }
    if len(sync_owners) > 1:
        for segment in segments:
            if segment.is_user and segment.speaker_match_source == 'sync_embedding':
                segment.is_user = False
                segment.person_id = None
                segment.speaker_identity_status = SpeakerIdentityStatus.ambiguous
                segment.speaker_match_source = MATCH_SOURCE
    if _capture_trusted(segments):
        conversation.speaker_resolution = ConversationSpeakers(
            status='capture',
            version=RESOLUTION_VERSION,
            participant_speaker_ids=significant_capture_speaker_ids(segments),
        )
    else:
        conversation.speaker_resolution = ConversationSpeakers(status='unavailable', version=RESOLUTION_VERSION)
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL.labels(outcome=outcome).inc()
    # A silent early return made a successful processing run indistinguishable
    # from a completed conversation-wide resolution. Keep this bounded and
    # anonymous: the conversation's captured speaker ids are not identities.
    logger.info(
        'event=conversation_speaker_resolution outcome=%s status=%s segments=%d',
        outcome,
        conversation.speaker_resolution.status,
        len(segments),
    )


def apply_speaker_resolution(
    conversation: Conversation,
    speaker_ids: Mapping[str, int],
    identities: Mapping[int, Identity],
    identity_statuses: Mapping[int, str],
) -> None:
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
            segment.speaker_label_source = 'auto'
        elif new_id in identity_statuses:
            if (
                identity_statuses[new_id] == SpeakerIdentityStatus.unknown
                and segment.speaker_match_source != MATCH_SOURCE
            ):
                # No new identity evidence (missing prints/short audio) cannot
                # revoke a capture decision that this stage did not make.
                continue
            # Conversation-wide evidence supersedes capture's automatic owner
            # guesses too. Manual voices are absent from this map, and the
            # persistence transaction re-applies the latest manual receipt.
            segment.is_user = False
            segment.person_id = None
            segment.speaker_identity_status = identity_statuses[new_id]
            segment.speaker_match_source = MATCH_SOURCE
            segment.speaker_label_source = None


_IDENTITY_FIELDS = (
    'id',
    'speaker_id',
    'speaker_id_scope',
    'is_user',
    'person_id',
    'speaker_identity_status',
    'speaker_match_source',
    'speaker_label_source',
)


def _apply_receipt_overlay(conversation: Conversation, receipt: Mapping[str, Any]) -> bool:
    """Replay the receipt onto the in-memory transcript; returns whether it bit."""
    current = [
        {field: getattr(segment, field) for field in _IDENTITY_FIELDS} for segment in conversation.transcript_segments
    ]
    speakers = receipt.get('speakers') or {}
    overrides = receipt.get('segments') or {}
    rejected = set(manual_rejected_speakers(receipt))
    matched = any(
        segment['id'] in overrides or str(segment['speaker_id']) in speakers or segment['speaker_id'] in rejected
        for segment in current
    )
    labeled_segments = apply_manual_assignments(current, dict(receipt))
    for segment, labeled in zip(conversation.transcript_segments, labeled_segments):
        segment.is_user = labeled['is_user']
        segment.person_id = labeled['person_id']
        segment.speaker_identity_status = labeled['speaker_identity_status']
        segment.speaker_match_source = labeled['speaker_match_source']
        segment.speaker_label_source = labeled['speaker_label_source']
    return matched


def resolve_speakers_for_processing(uid: str, conversation: Any) -> bool:
    """Resolve voices and return whether the manual receipt was read and applied."""
    if not isinstance(conversation, Conversation) or not conversation.transcript_segments:
        return False
    began = time.monotonic()
    receipt: Mapping[str, Any] = {}
    receipt_read = False
    receipt_applied = False
    try:
        receipt = conversations_db.get_manual_speaker_receipt(uid, conversation.id)
        receipt_read = True
        if receipt.get('speakers') or receipt.get('segments'):
            try:
                _apply_receipt_overlay(conversation, receipt)
            except Exception as error:
                logger.warning(
                    'event=conversation_speaker_resolution outcome=manual_receipt_failed exception_type=%s',
                    type(error).__name__,
                )
        if resolution_enabled():
            _resolve(uid, conversation, receipt=receipt, deadline=began + _budget_seconds())
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
            'event=conversation_speaker_resolution outcome=failed exception_type=%s',
            type(error).__name__,
        )
        if resolution_enabled():
            _without_resolution(conversation, 'failed')
    finally:
        # The persistence transaction reapplies this receipt, but the summary
        # prompt is built first. A resolved voice may include earlier unlabeled
        # fragments; apply the same authority to the in-memory transcript.
        if receipt_read and (receipt.get('speakers') or receipt.get('segments')):
            try:
                receipt_applied = _apply_receipt_overlay(conversation, receipt)
            except Exception as error:
                logger.warning(
                    'event=conversation_speaker_resolution outcome=manual_receipt_failed exception_type=%s',
                    type(error).__name__,
                )
        elif receipt_read:
            receipt_applied = True  # A successful read confirmed there is no manual receipt.
    return receipt_applied


def _resolve(uid: str, conversation: Conversation, *, receipt: Mapping[str, Any], deadline: float) -> None:
    began = time.monotonic()
    segments = conversation.transcript_segments
    input_ids = len({s.speaker_id for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL})
    if not conversation.private_cloud_sync_enabled or not speaker_embedding_configured():
        _without_resolution(conversation, 'no_audio')
        return

    doc = conversation.model_dump(mode='python')
    segment_maps = {
        s.id: dict(m, audio_alignment=s.audio_alignment, audio_capture_run=s.audio_capture_run)
        for s, m in zip(segments, doc.get('transcript_segments') or [])
        if s.id and isinstance(m, Mapping)
    }

    records = decode_cache(download_speaker_embedding_cache(uid, conversation.id))
    live_ids = {s.id for s in segments}
    dirty = False
    for sid in [sid for sid in records if sid not in live_ids]:
        del records[sid]
        dirty = True

    live = live_resolution_enabled()
    placements: Dict[str, SegmentPlacement] = {}
    for segment in segments:
        sid = segment.id
        segment_map = segment_maps.get(sid) if sid else None
        if segment.speaker_id == OMI_SPEAKER_ID_SENTINEL or segment_map is None or sid is None:
            continue
        placement = placement_for_segment(doc, segment_map, records.get(sid))
        if placement is None:
            continue
        if not ((placement.source_scope or '').startswith('sync:') or live):
            continue
        placements[sid] = placement

    for sid in [sid for sid in records if sid not in placements]:
        del records[sid]
        dirty = True

    model_stamp = embedding_model_stamp()
    by_id = {s.id: s for s in segments}
    cache: CacheEntries = {}
    for sid, placement in placements.items():
        entry = records.get(sid)
        if (
            entry is not None
            and entry.placement == placement
            and entry.model_stamp == model_stamp
            and entry.vector is not None
        ):
            cache[sid] = entry
        else:
            record = CachedEmbedding(_duration(by_id[sid]), None, placement, model_stamp)
            if (
                entry is None
                or entry.placement != record.placement
                or entry.model_stamp != record.model_stamp
                or entry.duration != record.duration
                or entry.vector is not None
            ):
                records[sid] = record
                dirty = True

    eligible_ids = {
        s.id
        for s in segments
        if s.id
        and isinstance(s.speaker_id, (int, str))
        and str(s.speaker_id).isdigit()
        and int(s.speaker_id) != OMI_SPEAKER_ID_SENTINEL
    }

    def withdraw_unvectorized() -> None:
        for segment in segments:
            if segment.id in eligible_ids and segment.id not in cache and segment.speaker_match_source == MATCH_SOURCE:
                segment.is_user = False
                segment.person_id = None
                segment.speaker_identity_status = SpeakerIdentityStatus.unknown
                segment.speaker_match_source = None
                segment.speaker_label_source = None

    withdraw_unvectorized()

    if not placements:
        if dirty:
            upload_speaker_embedding_cache(uid, conversation.id, encode_cache(records))
        _without_resolution(conversation, 'no_placements')
        return

    pending = [s for s in segments if s.id in placements and _duration(s) >= MIN_EMBED_SECONDS and s.id not in cache]
    new_embeddings, stop = _embed_missing(uid, conversation, pending, cache, deadline, placements)
    records.update(cache)
    if new_embeddings or dirty:
        upload_speaker_embedding_cache(uid, conversation.id, encode_cache(records))

    abstained: Set[str] = {sid for sid in eligible_ids if sid not in cache}
    withdraw_unvectorized()

    resolution = resolve_conversation_speakers(
        segments,
        {sid: entry.vector for sid, entry in cache.items()},
        manual_speakers=_manual_speakers(receipt),
        voiceprints=load_voiceprints_for_resolution(uid),
        abstained_segment_ids=abstained,
    )
    if resolution is None:
        _without_resolution(conversation, 'no_embeddings')
        return

    apply_speaker_resolution(
        conversation, resolution.speaker_ids, resolution.voice_identities, resolution.voice_identity_statuses
    )
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
        'event=conversation_speaker_resolution outcome=%s segments=%d input_ids=%d '
        'voices=%d participants=%d embedded=%d new_embeddings=%d voice_identities=%d owner_contended=%d '
        'coverage=%.2f stop=%s seconds=%.1f',
        outcome,
        len(segments),
        input_ids,
        resolution.stats['voices'],
        len(resolution.significant_speaker_ids),
        resolution.embedded_segments,
        new_embeddings,
        len(resolution.voice_identities),
        resolution.stats['owner_contended'],
        resolution.coverage,
        stop,
        time.monotonic() - began,
    )
