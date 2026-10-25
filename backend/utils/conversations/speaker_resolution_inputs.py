"""Receipt, measured-audio and authoritative-partition inputs for conversation speaker resolution."""

import math
import logging
from datetime import timezone
from typing import Any, Dict, Mapping, Sequence, Optional

from config.batch_conversation_speakers import BATCH_CONVERSATION_SCOPE
from models.transcript_segment import TranscriptSegment
from models.conversation import Conversation
from utils.speakers.provider_partition import provider_key
from utils.observability.fallback import record_fallback
from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.stt.conversation_speakers import Identity
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL


def started_at(conversation: Conversation) -> Optional[float]:
    moment = conversation.started_at or conversation.created_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def manifest_span_load(audio_file: Any) -> int:
    count = 0
    for key in ('chunk_spans', 'chunk_timestamps'):
        value = audio_file.get(key) if isinstance(audio_file, Mapping) else getattr(audio_file, key, None)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            count = max(count, len(value))
    return count


def manual_speakers(receipt: Mapping[str, Any]) -> Dict[int, Identity]:
    """A receipt key labeled neither owner nor person stays its own voice."""
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


def measured_embedding_seconds(segments, vectors, keys, clip_seconds, placements, max_clip_seconds):
    """Old unmeasured cache entries and reused PCM add no owner evidence."""
    durations = {}
    covered_windows = []
    for segment in segments:
        sid = segment.id
        if sid not in vectors:
            continue
        key = keys.get(sid, sid)
        seconds = clip_seconds.get(key, 0.0)
        if not math.isfinite(seconds) or seconds < 0:
            seconds = 0.0
        seconds = min(seconds, max(0.0, float(segment.end) - float(segment.start)), max_clip_seconds)
        window = placements[sid].window if sid in placements else None
        if window is not None:
            low, high = window
            if high - low > max_clip_seconds:
                center = (low + high) / 2
                low, high = center - max_clip_seconds / 2, center + max_clip_seconds / 2
            fresh = [(low, high)]
            for used_low, used_high in covered_windows:
                fresh = [
                    part
                    for a, b in fresh
                    for part in ((a, min(b, used_low)), (max(a, used_high), b))
                    if part[1] > part[0]
                ]
            seconds = min(seconds, sum(b - a for a, b in fresh))
            covered_windows.append((low, high))
        durations[sid] = seconds
    return durations


logger = logging.getLogger(__name__)


def batch_provider_keys(segments: list[TranscriptSegment]) -> dict[str, tuple[str, int]]:
    """Retain a prior conversation partition when optional unit markers disappear.

    Every original must-link stays inside one prior group. Distinct prior groups
    become cannot-links, a conservative strengthening of the original graph.
    Use that snapshot for the entire affected scope, never mix partial unit
    markers with a snapshot that could split one of its already resolved voices.
    """
    snapshots = {
        s.speaker_id_scope
        for s in segments
        if (s.speaker_id_scope or '').startswith(BATCH_CONVERSATION_SCOPE)
        and (
            s.provider_speaker is None
            or ((s.provider_speaker or {}).get('scope') or '').startswith(BATCH_CONVERSATION_SCOPE)
        )
    }
    if snapshots:
        record_fallback(
            component='other',
            from_mode='batch_unit_partition',
            to_mode='persisted_batch_partition',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    keys = {}
    for segment in segments:
        key = provider_key(segment)
        if segment.speaker_id_scope in snapshots:
            # Explicitly contradicted/redistributed text must still abstain.
            if segment.provider_speaker is not None and key is None:
                continue
            if (
                segment.id
                and segment.speaker_id is not None
                and segment.speaker_id >= 0
                and segment.speaker_id != OMI_SPEAKER_ID_SENTINEL
                and not segment._speaker_id_synthesized  # pyright: ignore[reportPrivateUsage]
            ):
                keys[segment.id] = ('batch-prior\0' + (segment.speaker_id_scope or ''), segment.speaker_id)
        elif segment.id and key is not None:
            keys[segment.id] = key
    return keys
