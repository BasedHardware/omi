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
from collections.abc import Sequence
import json
import logging
import math
import os
import struct
import time
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

import config.speaker_match_scores as match_scores

import httpx
import numpy as np

import database.conversations as conversations_db
import database.users as users_db
from config.audio_timeline import live_speaker_span_resolution_enabled
from database.audio_timeline import COVERAGE_TOLERANCE_SECONDS, chunk_span_bounds
from models.conversation import Conversation, ConversationSpeakers
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from utils.conversations.audio_placement import (
    AudioPlacement,
    PreparedAudioCoverage,
    locate,
    prepare_audio_coverage,
    saved_sync_window,
)
from utils.manual_speaker_assignments import apply_manual_assignments, manual_rejected_speakers
from utils.metrics import (
    OMI_AUDIO_PLACEMENT_TOTAL,
    OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL,
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL,
    OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES,
)
from utils.observability.fallback import record_fallback
from utils.other.audio_chunks import (
    AudioChunkReadSession,
    chunk_end_upper_bound,
    iter_audio_chunk_pcm,
)
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
    unit_voice_vector,
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
CACHE_FORMAT_VERSION = 1
MATCH_SOURCE = 'conversation_voice'
# Participants are only counted once voice evidence placed this much of the speech.
MIN_RESOLVED_COVERAGE = 0.9
CAPTURE_SPAN_KEY_PREFIX = 'capture-span:'
MAX_ADVISORY_PLACEMENTS = 1500
MAX_PLACEMENT_SPANS = 10000
ADVISORY_PLACEMENT_SECONDS = 0.25


def resolution_enabled() -> bool:
    return os.getenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'true').strip().lower() != 'false'


def _budget_seconds() -> float:
    return float(os.getenv('CONVERSATION_SPEAKER_RESOLUTION_BUDGET_SECONDS', '45'))


def _max_new_embeddings() -> int:
    return int(os.getenv('CONVERSATION_SPEAKER_RESOLUTION_MAX_EMBEDDINGS', '1500'))


# --- embedding cache ---------------------------------------------------------

CacheEntries = Dict[str, Tuple[float, np.ndarray]]


def encode_cache(entries: CacheEntries, evidence_seconds: Optional[Mapping[str, float]] = None) -> bytes:
    ids = list(entries)
    optional_header = {}
    try:
        if evidence_seconds is not None:
            optional_header = {
                'evidence_seconds': {k: round(v, 3) for k, v in evidence_seconds.items() if k in entries}
            }
    except Exception:
        match_scores.record_failure(logger, reason='malformed_doc')
    header = json.dumps(
        {
            'v': CACHE_FORMAT_VERSION,
            **optional_header,
            'ids': ids,
            'durations': [round(entries[i][0], 3) for i in ids],
            'dim': int(entries[ids[0]][1].size) if ids else 0,
        }
    ).encode()
    matrix = np.vstack([entries[i][1].reshape(1, -1) for i in ids]).astype('<f2').tobytes() if ids else b''
    return struct.pack('>I', len(header)) + header + matrix


def decode_cache(data: Optional[bytes], evidence_seconds: Optional[Dict[str, float]] = None) -> CacheEntries:
    if not data or len(data) < 4:
        return {}
    try:
        (length,) = struct.unpack('>I', data[:4])
        header = json.loads(data[4 : 4 + length])
        if header.get('v') != CACHE_FORMAT_VERSION or not header.get('ids'):
            return {}
        if evidence_seconds is not None:
            try:
                evidence_seconds.update(header.get('evidence_seconds') or {})
            except Exception:
                match_scores.record_failure(logger, reason='malformed_doc')
        dim = int(header['dim'])
        matrix = np.frombuffer(data[4 + length :], dtype='<f2').astype(np.float32).reshape(len(header['ids']), dim)
        return {sid: (float(d), matrix[i]) for i, (sid, d) in enumerate(zip(header['ids'], header['durations']))}
    except (json.JSONDecodeError, ValueError, struct.error, KeyError, TypeError):
        return {}


# --- inputs ------------------------------------------------------------------


def _started_at(conversation: Conversation) -> Optional[float]:
    moment = conversation.started_at or conversation.created_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _duration(segment: TranscriptSegment) -> float:
    return max(0.0, float(segment.end) - float(segment.start))


def _manifest_span_load(audio_file: Any) -> int:
    count = 0
    for key in ('chunk_spans', 'chunk_timestamps'):
        value = audio_file.get(key) if isinstance(audio_file, Mapping) else getattr(audio_file, key, None)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            count = max(count, len(value))
    return count


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


@dataclass
class EmbeddingDiagnostics:
    clip_skips: int = 0
    clip_too_short: int = 0
    chunk_boundary: int = 0
    embed_failures: int = 0
    clips: int = 0
    attempted: int = 0


def _inward_sample(bound: float, origin: float, *, exclusive_end: bool) -> int:
    """Cut inward on this chunk's grid, snapping only arithmetic roundoff.

    Subtracting epoch-sized floats loses low bits. Bound that uncertainty by
    the operands' ULPs rather than treating a fractional sample as an integer.
    An end index includes only complete samples before the exclusive end.
    """
    offset = (bound - origin) * SAMPLE_RATE
    uncertainty = (math.ulp(bound) + math.ulp(origin)) * SAMPLE_RATE + math.ulp(offset)
    nearest = round(offset)
    if abs(offset - nearest) <= uncertainty:
        offset = float(nearest)
    return math.floor(offset) if exclusive_end else math.ceil(offset)


def _verified_clip(session: AudioChunkReadSession, start: float, end: float) -> Tuple[Optional[bytes], str]:
    """Assemble at most 15s from the invocation's generation-pinned decoded cache.

    No downloads, padding, or interpolation. Only a tolerance-sized leading or
    trailing edge may be trimmed; an internal missing extent refuses the clip.
    Used only when the exact base midpoint clip cannot embed. Inventory/decoded
    coverage validation has already admitted this session. Cuts are inward and
    the sum of pieces has an integer 240,000-sample budget, even on mixed grids.
    """
    if end - start > MAX_CLIP_SECONDS:
        middle = (start + end) / 2.0
        start, end = middle - MAX_CLIP_SECONDS / 2, middle + MAX_CLIP_SECONDS / 2
    if end - start < MIN_EMBED_SECONDS:
        return None, 'clip_too_short'
    position = start
    pieces = []
    remaining_samples = int(MAX_CLIP_SECONDS * SAMPLE_RATE)
    for chunk in sorted(session.chunks, key=lambda c: c.get('span', {}).get('start', c['timestamp'])):
        chunk_start = chunk.get('span', {}).get('start', chunk['timestamp'])
        pcm, _ = session.cache.get(chunk['path'], (None, 'missing_blob'))
        if pcm is None:
            continue
        chunk_end = chunk_start + len(pcm) / (SAMPLE_RATE * 2)
        if chunk_end <= position or chunk_start >= end:
            continue
        # Between pieces, allow only wall-axis roundoff (well below one sample).
        if chunk_start > position + 1e-6:
            if pieces or chunk_start - position > COVERAGE_TOLERANCE_SECONDS:
                return None, 'chunk_boundary' if pieces else 'no_clip'
            position = chunk_start
        stop = min(end, chunk_end)
        first_sample = max(0, _inward_sample(position, chunk_start, exclusive_end=False))
        last_sample = min(len(pcm) // 2, _inward_sample(stop, chunk_start, exclusive_end=True))
        last_sample = min(last_sample, first_sample + remaining_samples)
        piece = pcm[first_sample * 2 : last_sample * 2]
        pieces.append(piece)
        remaining_samples -= len(piece) // 2
        position = stop
        if position >= end - 1e-6:
            clip = b''.join(pieces)
            return (clip, 'none') if len(clip) >= MIN_EMBED_SECONDS * SAMPLE_RATE * 2 else (None, 'clip_too_short')
    if pieces and end - position <= COVERAGE_TOLERANCE_SECONDS:
        clip = b''.join(pieces)
        return (clip, 'none') if len(clip) >= MIN_EMBED_SECONDS * SAMPLE_RATE * 2 else (None, 'clip_too_short')
    return None, 'chunk_boundary' if pieces else 'no_clip'


def _embed_missing(
    uid: str,
    conversation: Conversation,
    pending: List[TranscriptSegment],
    cache: CacheEntries,
    deadline: float,
    *,
    placements: Optional[Mapping[str, AudioPlacement]] = None,
    keys: Optional[Mapping[str, str]] = None,
    session: Optional[AudioChunkReadSession] = None,
    diagnostics: Optional[EmbeddingDiagnostics] = None,
    evidence_seconds: Optional[Dict[str, float]] = None,
) -> Tuple[int, str]:
    """Embed ``pending`` segments from stored audio into ``cache``; returns (count, stop reason)."""
    diagnostics = diagnostics if diagnostics is not None else EmbeddingDiagnostics()
    started_at = _started_at(conversation)
    if started_at is None or not pending:
        return 0, 'none'
    if placements is None:

        def window_of(segment: TranscriptSegment) -> Tuple[float, float]:
            return (started_at + segment.start, started_at + segment.end)

        # Chunk placement bisects on midpoints, so order by midpoint, not start.
        pending = sorted(pending, key=lambda s: s.start + s.end)
        midpoints = [started_at + (s.start + s.end) / 2.0 for s in pending]
    else:

        def window_of(segment: TranscriptSegment) -> Tuple[float, float]:
            placement = placements.get(segment.id) if segment.id is not None else None
            if placement is None or placement.window is None:
                raise RuntimeError('embeddable segment lacks a trusted placement window')
            return placement.window

        pending = sorted(pending, key=lambda s: sum(window_of(s)))
        midpoints = [(window_of(s)[0] + window_of(s)[1]) / 2.0 for s in pending]
    done: set[str] = set()
    limit = _max_new_embeddings()
    embedded = 0
    failures = 0

    def wanted(start: float, next_start: Optional[float]) -> bool:
        index = bisect.bisect_left(midpoints, start)
        return index < len(midpoints) and (next_start is None or midpoints[index] < next_start)

    def clips():
        base_ids: set[str] = set()
        if session is not None:

            def cached_chunks(read_session: AudioChunkReadSession):
                # Mirror the base iterator's wanted/filter/order semantics, but
                # read only the already generation-verified invocation cache.
                chunks = sorted(read_session.chunks, key=lambda c: c.get('span', {}).get('start', c['timestamp']))
                for index, chunk in enumerate(chunks):
                    if time.monotonic() > deadline or not read_session.in_budget():
                        return
                    chunk_start = chunk.get('span', {}).get('start', chunk['timestamp'])
                    following = chunks[index + 1] if index + 1 < len(chunks) else None
                    next_start = following.get('span', {}).get('start', following['timestamp']) if following else None
                    if wanted(chunk_start, next_start):
                        pcm, _ = read_session.cache.get(chunk['path'], (None, 'missing_blob'))
                        if pcm:
                            yield chunk_start, pcm

            iterator = cached_chunks(session)
        else:
            # Rollback/legacy sync path retains its single-midpoint-chunk policy.
            iterator = iter_audio_chunk_pcm(uid, conversation.id, wanted, sample_rate=SAMPLE_RATE)
        for chunk_start, pcm in iterator:
            chunk_end = chunk_start + len(pcm) / (SAMPLE_RATE * 2)
            first = bisect.bisect_left(midpoints, chunk_start)
            last = bisect.bisect_left(midpoints, chunk_end)
            for segment in pending[first:last]:
                abs_start, abs_end = window_of(segment)
                begin, end = max(abs_start, chunk_start), min(abs_end, chunk_end)
                if end - begin > MAX_CLIP_SECONDS:
                    middle = (begin + end) / 2.0
                    begin, end = middle - MAX_CLIP_SECONDS / 2, middle + MAX_CLIP_SECONDS / 2
                if end - begin < MIN_EMBED_SECONDS:
                    if session is None:
                        diagnostics.clip_skips += 1
                        if abs_end - abs_start >= MIN_EMBED_SECONDS:
                            diagnostics.chunk_boundary += 1
                        else:
                            diagnostics.clip_too_short += 1
                    continue
                clip = trim_pcm16(pcm, SAMPLE_RATE, begin - chunk_start, end - chunk_start)
                if session is not None:
                    if len(clip) < MIN_EMBED_SECONDS * SAMPLE_RATE * 2:
                        continue
                    if segment.id is not None:
                        base_ids.add(segment.id)
                yield segment, clip
        if session is not None:
            for segment in pending:
                if segment.id in base_ids:
                    continue
                if time.monotonic() > deadline or not session.in_budget():
                    return
                clip, reason = _verified_clip(session, *window_of(segment))
                if clip is None:
                    diagnostics.clip_skips += 1
                    if reason == 'clip_too_short':
                        diagnostics.clip_too_short += 1
                    elif reason == 'chunk_boundary':
                        diagnostics.chunk_boundary += 1
                    continue
                yield segment, clip

    with httpx.Client(timeout=EMBED_TIMEOUT_SECONDS) as client:
        if session is not None and time.monotonic() > deadline:
            return embedded, 'budget'
        if session is not None and limit <= 0:
            return embedded, 'max_embeddings'
        for segment, clip in clips():
            segment_id = segment.id
            if segment_id is None or segment_id in done:
                continue
            diagnostics.clips += 1
            if time.monotonic() > deadline:
                return embedded, 'budget'
            if embedded >= limit:
                return embedded, 'max_embeddings'
            diagnostics.attempted += 1
            try:
                vector = extract_embedding_from_bytes(
                    pcm_to_wav(clip, SAMPLE_RATE), client=client, timeout=EMBED_TIMEOUT_SECONDS
                )
            except Exception as error:
                failures += 1
                diagnostics.embed_failures += 1
                logger.warning(
                    'event=conversation_speaker_embed outcome=failed exception_type=%s', type(error).__name__
                )
                if failures >= MAX_CONSECUTIVE_EMBED_FAILURES:
                    return embedded, 'diarizer_unavailable'
                continue
            failures = 0
            cache_key = keys.get(segment_id, segment_id) if keys is not None else segment_id
            if evidence_seconds is not None:
                try:
                    evidence_seconds[cache_key] = len(clip) / (SAMPLE_RATE * 2)
                except Exception:
                    match_scores.record_failure(logger)
            cache[cache_key] = (_duration(segment), np.asarray(vector, dtype=np.float32).reshape(-1))
            done.add(segment_id)
            embedded += 1
    if session is not None and time.monotonic() > deadline:
        return embedded, 'budget'
    return embedded, 'complete'


def _manifest_inventory(audio_files: Any) -> Optional[List[Tuple[float, Optional[Tuple[float, float]]]]]:
    """Expected ``(timestamp, span bounds)`` pairs from the manifest, or None when malformed.

    A file without ``chunk_timestamps`` contributes nothing; a file whose
    ``chunk_spans`` is present must pair one well-formed span per timestamp.
    """
    expected: List[Tuple[float, Optional[Tuple[float, float]]]] = []
    if not isinstance(audio_files, Sequence) or isinstance(audio_files, (str, bytes)):
        return expected
    for audio_file in audio_files:
        if not isinstance(audio_file, Mapping):
            return None
        timestamps: Any = audio_file.get('chunk_timestamps')
        file_spans: Any = audio_file.get('chunk_spans')
        if not isinstance(timestamps, Sequence) or isinstance(timestamps, (str, bytes)):
            continue
        if file_spans is None:
            file_spans = []
        elif (
            not isinstance(file_spans, Sequence)
            or isinstance(file_spans, (str, bytes))
            or len(file_spans) != len(timestamps)
        ):
            return None
        for index, timestamp in enumerate(timestamps):
            try:
                ts = float(timestamp)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(ts):
                return None
            bounds = None
            if file_spans:
                bounds = chunk_span_bounds(file_spans[index])
                if bounds is None:
                    return None
            expected.append((ts, bounds))
    return expected


def _finite_number(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _chunk_actual_bounds(chunk: Mapping[str, Any]) -> Optional[Tuple[float, Optional[float]]]:
    """``(start, end)`` extent of one listed object; ``end=None`` is unbounded."""
    span = chunk.get('span')
    if isinstance(span, Mapping):
        rate = _finite_number(span.get('sample_rate'))
        start = _finite_number(span.get('start'))
        samples = _finite_number(span.get('samples'))
        if rate is None or start is None or samples is None or rate <= 0 or samples <= 0:
            return None
        return start, start + samples / rate
    timestamp = _finite_number(chunk.get('timestamp'))
    if timestamp is None:
        return None
    return timestamp, chunk_end_upper_bound(chunk, SAMPLE_RATE)


def _window_covered(extents: List[Tuple[float, float]], start: float, end: float) -> bool:
    """Whether the union of actual extents covers ``[start, end)``."""
    position = start
    while position < end - COVERAGE_TOLERANCE_SECONDS:
        advanced = [e for s, e in extents if s <= position + COVERAGE_TOLERANCE_SECONDS and e > position]
        if not advanced:
            return False
        position = max(advanced)
    return True


def _verified_read_session(
    uid: str,
    conversation: Conversation,
    audio_files: Any,
    pending: List[TranscriptSegment],
    placements: Mapping[str, AudioPlacement],
    deadline: float,
) -> Optional[AudioChunkReadSession]:
    """One bounded actual blob inventory, proven before any embedding decodes.

    The session's lazy listing is forced once here — after placement, before
    any embedding or cache upload — and frozen for the call. Every listed
    object must carry a positive generation and correspond to a manifest
    timestamp/span pair. All objects are then pre-fetched pinned to their
    listed generation and decoded once into the session cache: the concrete
    extent of each object comes from the decoded PCM (an authoritative span
    must match the decoded duration; a spanless object's end is its decoded
    end), every pair of distinct objects that overlaps beyond tolerance
    refuses, and each pending trusted window must be covered. Any missing,
    malformed, duplicate, raced, or over-budget evidence refuses the read
    before a single embedding is computed or the cache is touched.
    """
    session = AudioChunkReadSession(uid, conversation.id, SAMPLE_RATE)
    session.deadline = min(session.deadline, deadline)
    if not session.in_budget():
        return None
    chunks = session.chunks
    if session.limit_hit or len(chunks) > MAX_ADVISORY_PLACEMENTS:
        return None
    for chunk in chunks:
        generation = chunk.get('generation')
        if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
            return None
        if _finite_number(chunk.get('timestamp')) is None or not isinstance(chunk.get('path'), str):
            return None
        span = chunk.get('span')
        if span is not None and not isinstance(span, Mapping):
            return None
    expected = _manifest_inventory(audio_files)
    if expected is None:
        return None
    manifest_present = (
        isinstance(audio_files, Sequence) and not isinstance(audio_files, (str, bytes)) and len(audio_files) > 0
    )
    if manifest_present:
        if len(expected) != len(chunks):
            return None
        actual = []
        for chunk in chunks:
            ts = cast(float, _finite_number(chunk['timestamp']))
            span = chunk.get('span')
            if span is None:
                actual.append((ts, None))
                continue
            bounds = _chunk_actual_bounds(chunk)
            if bounds is None or bounds[1] is None:
                return None
            actual.append((ts, bounds))
        for (expected_ts, expected_bounds), (actual_ts, actual_bounds) in zip(sorted(expected), sorted(actual)):
            if abs(expected_ts - actual_ts) > COVERAGE_TOLERANCE_SECONDS:
                return None
            if (expected_bounds is None) != (actual_bounds is None):
                return None
            if (
                expected_bounds is not None
                and actual_bounds is not None
                and (
                    abs(expected_bounds[0] - actual_bounds[0]) > COVERAGE_TOLERANCE_SECONDS
                    or abs(expected_bounds[1] - actual_bounds[1]) > COVERAGE_TOLERANCE_SECONDS
                )
            ):
                return None
    decoded: Dict[str, bytes] = {}
    for chunk in chunks:
        pcm = session.fetch(chunk['path'])
        if pcm is None or len(pcm) % 2 or session.limit_hit:
            return None
        decoded[chunk['path']] = pcm
    extents: List[Tuple[float, float]] = []
    for chunk in chunks:
        pcm = decoded[chunk['path']]
        span = chunk.get('span')
        if isinstance(span, Mapping):
            bounds = _chunk_actual_bounds(chunk)
            if bounds is None or bounds[1] is None:
                return None
            declared = bounds[1] - bounds[0]
            decoded_duration = len(pcm) / (SAMPLE_RATE * 2)
            if declared <= 0 or abs(decoded_duration - declared) > 0.002:
                return None
            extents.append((bounds[0], bounds[1]))
        else:
            start = cast(float, _finite_number(chunk['timestamp']))
            extents.append((start, start + len(pcm) / (SAMPLE_RATE * 2)))
    for first in range(len(extents)):
        for second in range(first + 1, len(extents)):
            overlap = min(extents[first][1], extents[second][1]) - max(extents[first][0], extents[second][0])
            if overlap > COVERAGE_TOLERANCE_SECONDS:
                return None
    for segment in pending:
        placement = placements.get(segment.id) if segment.id is not None else None
        window = placement.window if placement is not None else None
        if window is None:
            return None
        if not _window_covered(extents, window[0], window[1]):
            return None
    return session


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
        (s.speaker_id_scope or '').startswith(('sync:', 'legacy-conversation:')) or s.speaker_id_scope == own
        for s in conversation.transcript_segments
        if s.speaker_id != OMI_SPEAKER_ID_SENTINEL
    )


def _without_resolution(
    conversation: Conversation,
    outcome: str,
    *,
    reason: str = 'none',
    force_unavailable: bool = False,
    diagnostics: Optional[Mapping[str, Any]] = None,
) -> None:
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
    if not force_unavailable and _capture_trusted(segments):
        conversation.speaker_resolution = ConversationSpeakers(
            status='capture',
            version=RESOLUTION_VERSION,
            participant_speaker_ids=significant_capture_speaker_ids(segments),
        )
    else:
        conversation.speaker_resolution = ConversationSpeakers(status='unavailable', version=RESOLUTION_VERSION)
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL.labels(outcome=outcome).inc()
    OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL.labels(outcome=outcome, reason=reason).inc()
    # A silent early return made a successful processing run indistinguishable
    # from a completed conversation-wide resolution. Keep this bounded and
    # anonymous: the conversation's captured speaker ids are not identities.
    fields = diagnostics or {}
    logger.info(
        'event=conversation_speaker_resolution outcome=%s status=%s segments=%d reason=%s stop=%s '
        'embeddable=%d pending=%d cache_hits=%d new_embeddings=%d valid_vectors=%d clip_skips=%d '
        'embed_failures=%d eligible=%d short=%d speech_seconds=%.3f excluded_id=%d excluded_speaker=%d '
        'requested=%d successful=%d invalid_vectors=%d missing_vectors=%d stale=%d clips=%d',
        outcome,
        conversation.speaker_resolution.status,
        len(segments),
        reason,
        fields.get('stop', 'none'),
        *(
            fields.get(key, 0)
            for key in (
                'embeddable',
                'pending',
                'cache_hits',
                'new_embeddings',
                'valid_vectors',
                'clip_skips',
                'embed_failures',
                'eligible',
                'short',
                'speech_seconds',
                'excluded_id',
                'excluded_speaker',
                'requested',
                'successful',
                'invalid_vectors',
                'missing_vectors',
                'stale',
                'clips',
            )
        ),
    )


def apply_speaker_resolution(
    conversation: Conversation,
    speaker_ids: Mapping[str, int],
    identities: Mapping[int, Identity],
    identity_statuses: Mapping[int, str],
) -> None:
    scope = f'conversation:{conversation.id}'
    origin = _started_at(conversation)
    for segment in conversation.transcript_segments:
        new_id = speaker_ids.get(segment.id) if segment.id else None
        if new_id is None:
            continue
        segment_scope = segment.speaker_id_scope or ''
        if (
            segment.audio_source is None
            and origin is not None
            and segment_scope.startswith('sync:')
            and len(segment_scope) > len('sync:')
            and segment.audio_alignment != 'unplaced'
            and math.isfinite(segment.start)
            and math.isfinite(segment.end)
            and 0 <= segment.start < segment.end
        ):
            segment.audio_source = {
                'type': 'sync',
                'start': origin + segment.start,
                'end': origin + segment.end,
            }
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
    try:
        if match_scores.enabled():
            updates = [s.speaker_match_scores for s in conversation.transcript_segments if s.speaker_match_scores]
            if updates:
                conversation.speaker_match_scores = match_scores.merge(conversation.speaker_match_scores, updates)
    except Exception:
        match_scores.record_failure(logger, reason='malformed_doc')
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
            'event=conversation_speaker_resolution outcome=failed uid=%s conversation=%s exception_type=%s',
            uid,
            conversation.id,
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


def _resolution_reason(placement_reasons: List[str]) -> str:
    """One bounded reason for a resolved/partial outcome from the placements used."""
    sources = set(placement_reasons)
    if not sources:
        return 'none'
    if len(sources) == 1:
        return sources.pop()
    return 'mixed'


NO_EMBEDDINGS_REASONS = frozenset(
    {
        'all_short',
        'no_eligible',
        'chunk_boundary',
        'clip_too_short',
        'embed_failed',
        'budget',
        'max_embeddings',
        'invalid_vector',
        'missing_vector',
        'no_clip',
    }
)


def _no_embeddings_diagnostics(
    segments: List[TranscriptSegment],
    vectors: Mapping[str, np.ndarray],
    pending: List[TranscriptSegment],
    new_embeddings: int,
    stop: str,
    diagnostics: EmbeddingDiagnostics,
    stale: List[str],
) -> Tuple[str, Dict[str, Any]]:
    non_omi = [s for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL]
    eligible = [s for s in non_omi if s.id and isinstance(s.speaker_id, (int, str)) and str(s.speaker_id).isdigit()]
    long = [s for s in eligible if _duration(s) >= MIN_EMBED_SECONDS]
    pending_ids = {s.id for s in pending}
    available = [vectors[s.id] for s in long if s.id is not None and vectors.get(s.id) is not None]
    valid = sum(unit_voice_vector(v) is not None for v in available)
    invalid = len(available) - valid
    # Population first, then invalid evidence, capacity, operational failure,
    # clip refusal, and residual key/iterator inconsistencies. Mixed counts remain in the log.
    if not eligible:
        reason = 'no_eligible'
    elif not long:
        reason = 'all_short'
    elif invalid:
        reason = 'invalid_vector'
    elif stop in ('budget', 'max_embeddings'):
        reason = stop
    elif diagnostics.embed_failures:
        reason = 'embed_failed'
    elif diagnostics.chunk_boundary:
        reason = 'chunk_boundary'
    elif diagnostics.clip_too_short:
        reason = 'clip_too_short'
    elif new_embeddings or available:
        reason = 'missing_vector'
    else:
        reason = 'no_clip'
    fields = dict(
        stop=stop,
        embeddable=sum(_duration(s) >= MIN_EMBED_SECONDS for s in non_omi),
        pending=len(pending),
        cache_hits=sum(s.id not in pending_ids for s in long),
        new_embeddings=new_embeddings,
        valid_vectors=valid,
        clip_skips=diagnostics.clip_skips,
        embed_failures=diagnostics.embed_failures,
        eligible=len(eligible),
        short=sum(_duration(s) < MIN_EMBED_SECONDS for s in non_omi),
        speech_seconds=sum(_duration(s) for s in non_omi),
        excluded_id=sum(not s.id for s in non_omi),
        excluded_speaker=sum(not str(s.speaker_id).isdigit() for s in non_omi),
        requested=diagnostics.attempted,
        successful=new_embeddings,
        invalid_vectors=invalid,
        missing_vectors=len(long) - len(available),
        stale=len(stale),
        clips=diagnostics.clips,
    )
    return reason, fields


def _resolve(uid: str, conversation: Conversation, *, receipt: Mapping[str, Any], deadline: float) -> None:
    began = time.monotonic()
    segments = conversation.transcript_segments
    input_ids = len({s.speaker_id for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL})
    if not conversation.private_cloud_sync_enabled or not speaker_embedding_configured():
        _without_resolution(conversation, 'no_audio')
        return
    spans_on = live_speaker_span_resolution_enabled()

    embeddable = [s for s in segments if s.speaker_id != OMI_SPEAKER_ID_SENTINEL and _duration(s) >= MIN_EMBED_SECONDS]
    placements: Dict[str, AudioPlacement] = {}
    inventory_files: List[Any] = []
    advisory_began = time.monotonic()
    if embeddable:
        raw_files = conversation.audio_files or []
        audio_timeline = conversation.audio_timeline
        if audio_timeline is not None:
            audio_timeline = audio_timeline.model_dump(mode='python')

        def placement_mapping(audio_files: List[Any]) -> Dict[str, Any]:
            return {
                'id': conversation.id,
                'started_at': _started_at(conversation),
                'audio_timeline': audio_timeline,
                'audio_files': audio_files,
            }

        def place_segment(segment: TranscriptSegment, mapping: Dict[str, Any], index) -> AudioPlacement:
            placement = locate(
                mapping,
                segment.start,
                segment.end,
                segments=[segment.model_dump(mode='python')],
                capture_spans=True,
                coverage=index,
            )
            OMI_AUDIO_PLACEMENT_TOTAL.labels(reason=placement.reason).inc()
            return placement

        if spans_on:
            index = PreparedAudioCoverage(validated=False)
            mapping: Dict[str, Any] = {}
            span_total = 0
            for audio_file in raw_files:
                span_total += 1 + _manifest_span_load(audio_file)
                if span_total > MAX_PLACEMENT_SPANS:
                    break
            if span_total <= MAX_PLACEMENT_SPANS:
                dumped_files = [f.model_dump(mode='python') if hasattr(f, 'model_dump') else f for f in raw_files]
                inventory_files = dumped_files
                mapping = placement_mapping(dumped_files)
                index = prepare_audio_coverage(dumped_files, deadline=deadline, max_spans=MAX_PLACEMENT_SPANS)
            for segment in embeddable:
                if time.monotonic() >= deadline:
                    _without_resolution(conversation, 'unaligned_audio', reason='unplaced', force_unavailable=True)
                    return
                if segment.id is None:
                    continue
                placements[segment.id] = place_segment(segment, mapping, index)
        else:
            span_total = 0
            bounded = True
            for audio_file in raw_files:
                span_total += 1 + _manifest_span_load(audio_file)
                if span_total > MAX_PLACEMENT_SPANS or time.monotonic() - advisory_began >= ADVISORY_PLACEMENT_SECONDS:
                    bounded = False
                    break
            if bounded and time.monotonic() - advisory_began >= ADVISORY_PLACEMENT_SECONDS:
                bounded = False
            if bounded:
                dumped_files = [f.model_dump(mode='python') if hasattr(f, 'model_dump') else f for f in raw_files]
                index = prepare_audio_coverage(
                    dumped_files,
                    deadline=advisory_began + ADVISORY_PLACEMENT_SECONDS,
                    max_spans=MAX_PLACEMENT_SPANS,
                )
                mapping = placement_mapping(dumped_files)
                measured = 0
                for segment in embeddable:
                    if (
                        measured >= MAX_ADVISORY_PLACEMENTS
                        or time.monotonic() - advisory_began >= ADVISORY_PLACEMENT_SECONDS
                    ):
                        break
                    if segment.id is None:
                        continue
                    placements[segment.id] = place_segment(segment, mapping, index)
                    measured += 1
            deadline += time.monotonic() - advisory_began

    if not spans_on:
        if not _audio_aligned(conversation):
            refusal = next(
                (p.reason for p in placements.values() if p.window is None),
                'legacy',
            )
            _without_resolution(conversation, 'unaligned_audio', reason=refusal)
            return

    clip_seconds: Optional[Dict[str, float]] = {} if match_scores.enabled() else None
    cache = decode_cache(download_speaker_embedding_cache(uid, conversation.id), clip_seconds)
    if not spans_on and any(key.startswith(CAPTURE_SPAN_KEY_PREFIX) for key in cache):
        _without_resolution(conversation, 'unaligned_audio', reason='capture_span')
        return

    keys: Optional[Dict[str, str]] = None
    if spans_on:
        keys = {}
        for segment in segments:
            if not segment.id:
                continue
            placement = placements.get(segment.id)
            if placement is not None and placement.reason == 'capture_span' and placement.window is not None:
                scope = segment.speaker_id_scope or ''
                historical = scope == f'conversation:{conversation.id}' or scope.startswith('legacy-conversation:')
                cached = cache.get(segment.id)
                if (
                    historical
                    and cached is not None
                    and abs(cached[0] - _duration(segment)) <= 0.25 * max(_duration(segment), 1e-3)
                ):
                    keys[segment.id] = segment.id
                else:
                    keys[segment.id] = (
                        f'{CAPTURE_SPAN_KEY_PREFIX}{segment.id}:{placement.window[0]!r}:{placement.window[1]!r}'
                    )
            else:
                keys[segment.id] = segment.id
        selected = set(keys.values())
        stale = [sid for sid in cache if sid not in selected]
    else:
        live_ids = {s.id for s in segments}
        stale = [sid for sid in cache if sid not in live_ids]
    for sid in stale:
        del cache[sid]

    def needs_embedding(segment: TranscriptSegment) -> bool:
        if segment.speaker_id == OMI_SPEAKER_ID_SENTINEL or _duration(segment) < MIN_EMBED_SECONDS:
            return False

        def cache_hit(key: str) -> bool:
            return key in cache and abs(cache[key][0] - _duration(segment)) <= 0.25 * max(_duration(segment), 1e-3)

        if keys is None:
            return not (segment.id is not None and cache_hit(segment.id))
        sid = segment.id
        if not sid:
            return True
        placement = placements.get(sid)
        placeable = placement is not None and placement.window is not None
        if placeable:
            return not cache_hit(keys[sid])
        if segment.audio_capture_start is not None or segment.audio_capture_end is not None:
            return True
        scope = segment.speaker_id_scope or ''
        if (
            segment.id
            and (scope == f'conversation:{conversation.id}' or scope.startswith('legacy-conversation:'))
            and cache_hit(segment.id)
        ):
            return False
        return True

    pending = [s for s in segments if needs_embedding(s)]
    if spans_on:
        for segment in pending:
            if segment.id is None:
                _without_resolution(conversation, 'unaligned_audio', reason='unplaced', force_unavailable=True)
                return
            placement = placements.get(segment.id)
            if placement is None or placement.window is None:
                _without_resolution(
                    conversation,
                    'unaligned_audio',
                    reason=placement.reason if placement is not None else 'unplaced',
                    force_unavailable=True,
                )
                return
    else:
        own_scope = f'conversation:{conversation.id}'
        origin = _started_at(conversation)
        for segment in pending:
            if segment.speaker_id_scope == own_scope and (
                segment.audio_capture_start is not None or segment.audio_capture_end is not None
            ):
                placed = (
                    segment.audio_alignment != 'unplaced'
                    and math.isfinite(segment.start)
                    and math.isfinite(segment.end)
                    and 0 <= segment.start < segment.end
                )
                proof = {
                    'start': segment.start,
                    'end': segment.end,
                    'audio_source': segment.audio_source,
                }
                if not placed or origin is None or not saved_sync_window(proof, origin):
                    _without_resolution(conversation, 'unaligned_audio', reason='capture_span')
                    return
    read_session = None
    if spans_on and pending:
        read_session = _verified_read_session(uid, conversation, inventory_files, pending, placements, deadline)
        if read_session is None:
            _without_resolution(conversation, 'unaligned_audio', reason='unverified_inventory', force_unavailable=True)
            return
    diagnostics = EmbeddingDiagnostics()
    if spans_on:
        new_embeddings, stop = _embed_missing(
            uid,
            conversation,
            pending,
            cache,
            deadline,
            placements=placements,
            keys=keys,
            session=read_session,
            diagnostics=diagnostics,
            evidence_seconds=clip_seconds,
        )
        if read_session is not None and read_session.limit_hit:
            _without_resolution(conversation, 'unaligned_audio', reason='unverified_inventory', force_unavailable=True)
            return
    else:
        new_embeddings, stop = _embed_missing(
            uid, conversation, pending, cache, deadline, diagnostics=diagnostics, evidence_seconds=clip_seconds
        )
    if new_embeddings or stale:
        upload_speaker_embedding_cache(uid, conversation.id, encode_cache(cache, clip_seconds))

    if keys is not None:
        vectors = {
            segment.id: cache[keys[segment.id]][1]
            for segment in segments
            if segment.id in keys and keys[segment.id] in cache
        }
    else:
        vectors = {sid: vector for sid, (_, vector) in cache.items()}
    score_durations = None
    try:
        score_durations = (
            {s.id: clip_seconds[keys[s.id]] for s in segments if s.id in keys and keys[s.id] in clip_seconds}
            if spans_on and keys is not None and clip_seconds is not None
            else ({} if spans_on else clip_seconds)
        )
    except Exception:
        match_scores.record_failure(logger, reason='malformed_doc')
    resolution = resolve_conversation_speakers(
        segments,
        vectors,
        manual_speakers=_manual_speakers(receipt),
        voiceprints=load_voiceprints_for_resolution(uid),
        embedding_seconds=score_durations,
    )
    if resolution is None:
        reason, fields = _no_embeddings_diagnostics(
            segments, vectors, pending, new_embeddings, stop, diagnostics, stale
        )
        _without_resolution(conversation, 'no_embeddings', reason=reason, diagnostics=fields)
        return

    try:
        if match_scores.enabled():
            retained = [r for r in (conversation.speaker_match_scores or []) if r['stage'] != 'resolution']
            conversation.speaker_match_scores = match_scores.merge(retained, resolution.match_scores)
    except Exception:
        match_scores.record_failure(logger, reason='malformed_doc')
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
    if spans_on:
        if not pending and embeddable:
            outcome_reason = 'cached'
        else:
            outcome_reason = _resolution_reason([placements[s.id].reason for s in pending if s.id in placements])
    else:
        outcome_reason = 'legacy'
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL.labels(outcome=outcome).inc()
    OMI_CONVERSATION_SPEAKER_RESOLUTION_REASONS_TOTAL.labels(outcome=outcome, reason=outcome_reason).inc()
    OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES.labels(stage='input').observe(input_ids)
    OMI_CONVERSATION_SPEAKER_RESOLUTION_VOICES.labels(stage='resolved').observe(resolution.stats['voices'])
    logger.info(
        'event=conversation_speaker_resolution outcome=%s segments=%d input_ids=%d '
        'voices=%d participants=%d embedded=%d new_embeddings=%d voice_identities=%d owner_contended=%d '
        'coverage=%.2f stop=%s seconds=%.1f reason=%s embeddable=%d pending=%d cache_hits=%d '
        'valid_vectors=%d clip_skips=%d embed_failures=%d',
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
        outcome_reason,
        len(embeddable),
        len(pending),
        len(embeddable) - len(pending),
        resolution.embedded_segments,
        diagnostics.clip_skips,
        diagnostics.embed_failures,
    )
