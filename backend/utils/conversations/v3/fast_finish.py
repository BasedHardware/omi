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
- Rollout: ``CONVERSATIONS_V3_FAST_FINISH`` is ``cohort`` (default: members of the ``v3-fast-finish``
  runtime rollout cohort, empty until someone is added), ``on`` or ``off``.
"""

import logging
import os
import time
import uuid
from typing import Any

from prometheus_client import Counter, Histogram

from config.rollout_cohorts import in_rollout_cohort

logger = logging.getLogger(__name__)

# One provider request and one in-memory PCM buffer per finish: 20 min of 16 kHz mono is 38 MB.
MAX_SECONDS = 1200.0
# One provider request per unit; units split at an audio gap over 30 s.
MAX_UNITS = 8
# How far a unit's first and last provisional line may reach toward that unit's audio bounds.
EDGE_PAD_SECONDS = 2.0
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
    'not_enabled',
    'ineligible',
    'too_long',
    'superseded',
    'not_funded',
    'busy',
    'audio_error',
    'provider_error',
    'write_error',
    'cut_error',
    'error',
):
    OUTCOMES.labels(_outcome)


COHORT = 'v3-fast-finish'


def mode() -> str:
    return os.getenv('CONVERSATIONS_V3_FAST_FINISH', 'cohort').strip().lower()


def enabled(uid: str) -> bool:
    """``cohort`` (default) admits members of the runtime rollout cohort; ``on`` every owner; ``off`` nobody."""
    current = mode()
    if current == 'on':
        return True
    return current == 'cohort' and in_rollout_cohort(uid, COHORT)


def candidate(row: dict) -> bool:
    """A sealed, manually ended v3 recording, judged from fields that are stored in the clear.

    Safe on a raw Firestore row. It says nothing about the transcript: stored segments are
    compressed (and may be encrypted) even when empty, so only ``eligible`` on a decoded row can
    tell whether the recording already has one.
    """
    return bool(
        row.get('recording') is True
        and (row.get('v3_manual_end_requested') is True or row.get('v3_manual_end') is True)
        and row.get('status') == 'completed'
        and row.get('private_cloud_sync_enabled')
        and row.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and not row.get('record_projection_revision')
        and not row.get('record_audio_partial')
        and not any(row.get(key) for key in ('deleted', 'discarded', 'is_locked', 'uses_custom_stt'))
    )


def eligible(row: dict) -> bool:
    """``candidate`` with no transcript of any kind yet. ``row`` must be decoded (``get_conversation``)."""
    return candidate(row) and not row.get('transcript_segments')


def funded(uid: str, seconds: float, language: str | None) -> bool:
    """The shared consent and funding gate that batch and sync transcription pass before provider spend."""
    from utils.observability.stt_cap_dispatch import DispatchPath
    from utils.stt.pre_recorded import get_prerecorded_service
    from utils.stt_cap_dispatch import sync_admission

    provider = get_prerecorded_service(language)[0]
    allowed, _ = sync_admission(uid, seconds, provider, lane='batch', path=DispatchPath.BATCH_PROVIDER)
    return allowed


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


def run(
    uid: str,
    conversation_id: str,
    row: dict,
    units: list,
    read,
    *,
    write=None,
    transcribe=None,
    refresh=None,
    cut=None,
    authorize=None,
) -> str:
    """Transcribe ``units`` and write them as provisional segments. Returns the counted outcome; never raises.

    ``row`` and ``refresh()`` must be decoded rows. ``authorize`` is the consent and funding gate;
    without it nothing is sent to a provider that ordinary batch processing would have held.

    Runs on a worker thread: the cohort read is synchronous there (on the event loop a cold
    membership cache answers False). ``refresh`` re-reads the row before any audio leaves for the
    provider and again just before the write, so a delete, discard, lock, privacy change or
    canonical projection wins. ``cut`` stores the manual end only after the whole-recording
    transcript is written: a cut without it would lock a partial window on a multi-unit recording.
    """
    try:
        outcome = _run(
            uid,
            conversation_id,
            row,
            units,
            read,
            write=write,
            transcribe=transcribe or _transcribe,
            refresh=refresh,
            cut=cut,
            authorize=authorize or funded,
        )
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=error exception_type=%s', type(error).__name__)
        outcome = 'error'
    OUTCOMES.labels(outcome).inc()
    logger.info('event=v3_fast_finish outcome=%s units=%s', outcome, len(units))
    return outcome


def _run(uid, conversation_id, row, units, read, *, write, transcribe, refresh, cut, authorize) -> str:
    if not enabled(uid):
        return 'not_enabled'
    if refresh is not None:
        # Admission read this row before staging. Nothing is sent to the provider on a stale grant.
        row = refresh()
    if not eligible(row):
        return 'ineligible'
    if not units or len(units) > MAX_UNITS or sum(duration for _, duration, _ in units) > MAX_SECONDS:
        return 'too_long'
    if not authorize(uid, sum(duration for _, duration, _ in units), row.get('language')):
        return 'not_funded'
    origin = row['started_at'].timestamp()
    segments: list[dict[str, Any]] = []
    started = time.monotonic()
    try:
        audio = [(start, duration, unit_pcm(references, read)) for start, duration, references in units]
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=audio_error exception_type=%s', type(error).__name__)
        return 'audio_error'
    SECONDS.labels('audio').observe(time.monotonic() - started)
    started = time.monotonic()
    try:
        for start, duration, pcm in audio:
            shift = start - origin
            lines = sorted(transcribe(pcm, row.get('language')), key=lambda line: (line['start'], line['end']))
            for segment in lines:
                segment['start'] += shift
                segment['end'] += shift
                # The batch projection allocates speaker numbers after every stored integer id, covered
                # rows included. Provisional rows keep their label and claim no number.
                segment['speaker_id'] = None
            if lines:
                # A locked window keeps the bounds of the lines it was built from, and the batch
                # transcript's edge lines can sit a little outside them. Pad this unit's outer lines,
                # never past its own audio: the batch projection replaces a line by its midpoint,
                # which must stay inside the unit it came from.
                lines[0]['start'] = max(shift, lines[0]['start'] - EDGE_PAD_SECONDS)
                lines[-1]['end'] = min(shift + duration, lines[-1]['end'] + EDGE_PAD_SECONDS)
            segments.extend(lines)
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=provider_error exception_type=%s', type(error).__name__)
        return 'provider_error'
    SECONDS.labels('provider').observe(time.monotonic() - started)
    if not segments:
        return 'empty'
    segments.sort(key=lambda segment: (segment['start'], segment['end']))
    if refresh is not None and not eligible(refresh()):
        return 'superseded'
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
    if written is False:
        return 'superseded'
    if cut is not None:
        try:
            cut()
        except Exception as error:
            # The transcript is stored; without the cut the window follows the silence and lock timers.
            logger.warning('event=v3_fast_finish outcome=cut_error exception_type=%s', type(error).__name__)
            return 'cut_error'
    return 'written'
