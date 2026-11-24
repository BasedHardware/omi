"""First transcript for a manually finished v3 recording, ahead of the batch pipeline.

Owns one thing: when the user ends a capture (Finish, End, Wrap Up, a pendant double-tap) and its
audio has sealed, transcribe that recording once through the prerecorded provider for its language
and write the result as a provisional live transcript. The existing transcript writer marks the
recording pending and wakes the v3 builder; the stored ``v3_manual_end`` cuts and locks the window,
so notes are written at once instead of after the batch pipeline's ordered merge and delivery.

Constraints it upholds:
- The batch pipeline stays the owner of the canonical transcript. Its ``replace_record`` replaces
  these provisional segments inside the record span, and ``update_conversation_segments`` refuses
  this write once ``record_projection_revision`` is set, so a late fast pass can never overwrite it.
- Best effort only. Every failure is counted and swallowed; admission never waits on it.
- Rollout: ``CONVERSATIONS_V3_FAST_FINISH`` is ``off`` (default), ``on``, or a list of ``uid:`` members.
"""

import logging
import os
import time
import uuid
from typing import Any

from prometheus_client import Counter, Histogram

from config.rollout_cohorts import parse_cohort, valid_uid

logger = logging.getLogger(__name__)

# One provider request and one in-memory PCM buffer per finish: 20 min of 16 kHz mono is 38 MB.
MAX_SECONDS = 1200.0
SAMPLE_RATE = 16000

OUTCOMES = Counter(
    'omi_conversations_v3_fast_finish_total',
    'Manual-finish first transcripts by outcome',
    ['outcome'],
)
SECONDS = Histogram(
    'omi_conversations_v3_fast_finish_seconds',
    'Fast first transcript: audio read, provider call and write, by stage',
    ['stage'],
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60, 120),
)
for _outcome in (
    'written',
    'empty',
    'ineligible',
    'too_long',
    'superseded',
    'audio_error',
    'provider_error',
    'write_error',
):
    OUTCOMES.labels(_outcome)


def enabled(uid: str) -> bool:
    """``on`` admits every owner; a ``uid:`` list admits only its members; anything else is off."""
    raw = os.getenv('CONVERSATIONS_V3_FAST_FINISH', 'off').strip()
    mode = raw.lower()
    if mode in {'on', 'true', '1'}:
        return True
    if not raw or mode in {'off', 'false', '0', 'no'} or not valid_uid(uid):
        return False
    if not all(token.strip().lower().startswith('uid:') for token in raw.split(',')):
        return False
    parsed = parse_cohort(raw)
    if parsed is None:
        return False
    members, _ = parsed
    return not any(set(member) & set('*?[]') for member in members) and uid in members


def eligible(row: dict) -> bool:
    """A sealed, manually ended v3 recording with no transcript of any kind yet."""
    return bool(
        row.get('recording') is True
        and row.get('v3_manual_end') is True
        and row.get('status') == 'completed'
        and row.get('private_cloud_sync_enabled')
        and row.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and not row.get('transcript_segments')
        and not row.get('record_projection_revision')
        and not row.get('record_audio_partial')
        and not any(row.get(key) for key in ('deleted', 'discarded', 'is_locked', 'uses_custom_stt'))
    )


def unit_pcm(references: list[dict], read) -> bytes:
    """Lay each retained reference at its frame position; uncovered frames stay silent."""
    frames = max((ref['start_frame'] + ref['frames'] for ref in references), default=0)
    pcm = bytearray(frames * 2)
    cache: dict[tuple, bytes] = {}
    for ref in references:
        source = (ref['bucket'], ref['path'], ref['generation'])
        if source not in cache:
            cache = {source: read(ref)}  # references are ordered by source; keep one decoded pack
        audio = cache[source][ref['offset_frame'] * 2 : (ref['offset_frame'] + ref['frames']) * 2]
        if len(audio) != ref['frames'] * 2:
            raise ValueError('retained reference shorter than its frame span')
        pcm[ref['start_frame'] * 2 : ref['start_frame'] * 2 + len(audio)] = audio
    return bytes(pcm)


def _transcribe(pcm: bytes, language: str | None) -> list[dict]:
    from utils.stt.pre_recorded import postprocess_words, prerecorded_from_bytes
    from utils.sync.word_timing import first_word_offset

    words = prerecorded_from_bytes(
        pcm, sample_rate=SAMPLE_RATE, diarize=True, attempts=1, encoding='linear16', channels=1, language=language
    )
    if not words:
        return []
    # postprocess_words starts its clock at the first word; restore the offset into the unit.
    offset = first_word_offset(words)
    segments = []
    for segment in postprocess_words(words, 0):
        row = segment.model_dump()
        row.update(id=str(uuid.uuid4()), start=row['start'] + offset, end=row['end'] + offset)
        segments.append(row)
    return segments


def run(uid: str, conversation_id: str, row: dict, units: list, read, *, write=None, transcribe=None) -> str:
    """Transcribe ``units`` and write them as provisional segments. Returns the counted outcome; never raises."""
    outcome = _run(uid, conversation_id, row, units, read, write=write, transcribe=transcribe or _transcribe)
    OUTCOMES.labels(outcome).inc()
    logger.info('event=v3_fast_finish outcome=%s units=%s', outcome, len(units))
    return outcome


def _run(uid, conversation_id, row, units, read, *, write, transcribe) -> str:
    if not eligible(row):
        return 'ineligible'
    if not units or sum(duration for _, duration, _ in units) > MAX_SECONDS:
        return 'too_long'
    origin = row['started_at'].timestamp()
    segments: list[dict[str, Any]] = []
    started = time.monotonic()
    try:
        audio = [(start, unit_pcm(references, read)) for start, _, references in units]
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=audio_error exception_type=%s', type(error).__name__)
        return 'audio_error'
    SECONDS.labels('audio').observe(time.monotonic() - started)
    started = time.monotonic()
    try:
        for start, pcm in audio:
            shift = start - origin
            for segment in transcribe(pcm, row.get('language')):
                segment['start'] += shift
                segment['end'] += shift
                segments.append(segment)
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=provider_error exception_type=%s', type(error).__name__)
        return 'provider_error'
    SECONDS.labels('provider').observe(time.monotonic() - started)
    if not segments:
        return 'empty'
    segments.sort(key=lambda segment: (segment['start'], segment['end']))
    started = time.monotonic()
    try:
        if write is None:
            from database.conversations import update_conversation_segments as write
        # False: the canonical record already projected (or the row is gone); the batch transcript wins.
        written = write(uid, conversation_id, segments)
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=write_error exception_type=%s', type(error).__name__)
        return 'write_error'
    SECONDS.labels('write').observe(time.monotonic() - started)
    return 'written' if written is not False else 'superseded'
