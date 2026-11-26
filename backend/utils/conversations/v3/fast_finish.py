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
- Long recordings: ``CONVERSATIONS_V3_FAST_FINISH_CHUNKED`` (default on) splits every unit into chunks
  of at most five minutes and sends them to the provider concurrently, up to two hours a recording.
  ``off`` restores one serial provider request per unit and the 20-minute cap.
"""

import functools
import logging
import os
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, wait
from typing import Any, NamedTuple

from prometheus_client import Counter, Histogram

from config.refactor_modes import default_on
from config.rollout_cohorts import in_rollout_cohort
from utils.executors import get_fast_finish_chunk_executor

logger = logging.getLogger(__name__)

# Kill-switch path (CONVERSATIONS_V3_FAST_FINISH_CHUNKED=off): one provider request and one in-memory
# PCM buffer per unit, sent one after another: 20 min of 16 kHz mono is 38 MB.
MAX_SECONDS = 1200.0
# Units split at an audio gap over 30 s (and at one hour).
MAX_UNITS = 8
# Chunked path (default). The memory bound no longer depends on length: a pass holds at most
# PASS_CHUNK_WINDOW chunk buffers (4 x 5 min = 38 MB, the same as the 20-minute cap allowed) plus
# one decoded source pack. The ceiling bounds one pass's provider spend and how long it holds one of
# the two pass slots (25 chunks, about seven rounds of four); longer finishes keep the batch transcript.
CHUNKED_MAX_SECONDS = 7200.0
CHUNK_SECONDS = 300.0
# A fixed cut repeats this much audio in both chunks; each word is kept once, by the chunk that
# owns its midpoint, so any word shorter than the overlap is heard whole by its owner.
CHUNK_OVERLAP_SECONDS = 3.0
# A retained-audio gap at least this long, in the second half of a chunk, is preferred as the cut.
MIN_SILENCE_SECONDS = 1.0
# Chunk requests one pass keeps in flight. The pool behind them (utils.executors) caps provider
# requests across both pass slots of the process.
PASS_CHUNK_WINDOW = 4
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
# Chunked path only. Fixed buckets, no labels: never a uid, a conversation id or any content.
CHUNKS = Histogram(
    'omi_conversations_v3_fast_finish_chunks',
    'Provider chunks per chunked fast first transcript',
    buckets=(1, 2, 3, 4, 6, 8, 12, 16, 24),
)
PROVIDER_CHUNK_SECONDS = Histogram(
    'omi_conversations_v3_fast_finish_chunk_seconds',
    'One chunk provider request, successful or not',
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60, 120),
)
WALL_SECONDS = Histogram(
    'omi_conversations_v3_fast_finish_wall_seconds',
    'A written fast first transcript, from the start of the pass to its write and cut',
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600),
)
for _outcome in (
    'written',
    'empty',
    'not_enabled',
    'ineligible',
    'too_long',
    'superseded',
    'not_funded',
    'privacy_blocked',
    'busy',
    'audio_error',
    'provider_error',
    'write_error',
    'cut_error',
    'error',
):
    OUTCOMES.labels(_outcome)

# Why a manual finish admitted for batch never started a pass. Fixed reasons only: never a uid,
# a conversation id or any content.
SKIPPED = Counter(
    'omi_conversations_v3_fast_finish_skipped_total',
    'Manual finishes that never started a fast first transcript, by the first reason',
    ['reason'],
)
# Stored statuses other than these two collapse into ``status_other`` so the label set stays fixed.
_STATUS_REASONS = {'in_progress': 'status_in_progress', 'processing': 'status_processing'}
_FLAG_REASONS = (
    ('deleted', 'deleted'),
    ('discarded', 'discarded'),
    ('is_locked', 'locked'),
    ('uses_custom_stt', 'custom_stt'),
)
SKIP_REASONS = (
    'mode_off',
    'already_started',
    'not_recording',
    'no_manual_end',
    *_STATUS_REASONS.values(),
    'status_other',
    'no_private_cloud_sync',
    'protection_level',
    'projection_revision',
    'audio_partial',
    *(reason for _, reason in _FLAG_REASONS),
)
for _reason in SKIP_REASONS:
    SKIPPED.labels(_reason)


COHORT = 'v3-fast-finish'


def mode() -> str:
    return os.getenv('CONVERSATIONS_V3_FAST_FINISH', 'cohort').strip().lower()


def enabled(uid: str) -> bool:
    """``cohort`` (default) admits members of the runtime rollout cohort; ``on`` every owner; ``off`` nobody."""
    current = mode()
    if current == 'on':
        return True
    return current == 'cohort' and in_rollout_cohort(uid, COHORT)


def chunked_enabled() -> bool:
    """Kill switch for the chunked, concurrent provider path; off restores serial units and the 20-minute cap."""
    return default_on('CONVERSATIONS_V3_FAST_FINISH_CHUNKED')


def candidate_rejection(row: dict) -> str | None:
    """The first ``candidate`` predicate ``row`` fails, as a fixed reason; None when it is a candidate.

    Safe on a raw Firestore row: it reads only fields that are stored in the clear.
    """
    if row.get('recording') is not True:
        return 'not_recording'
    if not (row.get('v3_manual_end_requested') is True or row.get('v3_manual_end') is True):
        return 'no_manual_end'
    status = row.get('status')
    if status != 'completed':
        return _STATUS_REASONS.get(status, 'status_other') if isinstance(status, str) else 'status_other'
    if not row.get('private_cloud_sync_enabled'):
        return 'no_private_cloud_sync'
    if row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        return 'protection_level'
    if row.get('record_projection_revision'):
        return 'projection_revision'
    if row.get('record_audio_partial'):
        return 'audio_partial'
    for key, reason in _FLAG_REASONS:
        if row.get(key):
            return reason
    return None


def candidate(row: dict) -> bool:
    """A sealed, manually ended v3 recording, judged from fields that are stored in the clear.

    Safe on a raw Firestore row. It says nothing about the transcript: stored segments are
    compressed (and may be encrypted) even when empty, so only ``eligible`` on a decoded row can
    tell whether the recording already has one. Defined by ``candidate_rejection`` so the two
    cannot drift.
    """
    return candidate_rejection(row) is None


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


class Chunk(NamedTuple):
    """A provider request's frame window [lo, hi) inside its unit, and the frames whose words it keeps.

    ``own_lo``/``own_hi`` bound the word midpoints this chunk owns; None is unbounded (the unit's
    first and last chunk). Neighbouring chunks share one boundary, so every word has one owner.
    """

    lo: int
    hi: int
    own_lo: int | None
    own_hi: int | None


def silences(references: list[dict]) -> list[tuple[int, int]]:
    """Frame runs inside a unit that no retained reference covers: they are laid down as silence."""
    gaps, covered = [], None
    for start, end in sorted((ref['start_frame'], ref['start_frame'] + ref['frames']) for ref in references):
        if covered is not None and start > covered:
            gaps.append((covered, start))
        covered = end if covered is None else max(covered, end)
    return gaps


def chunk_plan(frames: int, gaps=()) -> list[Chunk]:
    """Windows of at most CHUNK_SECONDS covering ``frames``, in order.

    The rest of the unit is shared evenly between the chunks it still needs, so no chunk is a
    sliver. A cut is the middle of the silence of at least MIN_SILENCE_SECONDS nearest that even
    length, from half of it up to CHUNK_SECONDS; with none, the window is cut at the even length and
    the next one starts CHUNK_OVERLAP_SECONDS earlier, the two owning the words on either side of the
    overlap's middle.
    """
    if frames <= 0:
        return []
    size = int(CHUNK_SECONDS * SAMPLE_RATE)
    overlap = int(CHUNK_OVERLAP_SECONDS * SAMPLE_RATE)
    shortest = int(MIN_SILENCE_SECONDS * SAMPLE_RATE)
    plan: list[Chunk] = []
    lo, own_lo = 0, None
    while frames - lo > size:
        rest = frames - lo
        # Chunks this rest still needs if every later cut is a fixed one, and their even length.
        needed = 1 + -(-(rest - size) // (size - overlap))
        span = -(-(rest + (needed - 1) * overlap) // needed)
        limit = lo + span
        cuts = [
            (start + end) // 2
            for start, end in gaps
            if end - start >= shortest and lo + span // 2 <= (start + end) // 2 <= lo + size
        ]
        if cuts:
            cut = min(cuts, key=lambda frame: (abs(frame - limit), frame))
            plan.append(Chunk(lo, cut, own_lo, cut))
            lo, own_lo = cut, cut
        else:
            boundary = limit - overlap // 2
            plan.append(Chunk(lo, limit, own_lo, boundary))
            lo, own_lo = limit - overlap, boundary
    plan.append(Chunk(lo, frames, own_lo, None))
    return plan


def window_pcm(references: list[dict], read, lo: int, hi: int, cache: dict) -> bytes:
    """``unit_pcm`` for frames [lo, hi) only. ``cache`` keeps one decoded pack across calls."""
    pcm = bytearray((hi - lo) * 2)
    for ref in references:
        start = ref['start_frame']
        first, last = max(start, lo), min(start + ref['frames'], hi)
        if first >= last:
            continue
        source = (ref['bucket'], ref['path'], ref['generation'])
        if source not in cache:
            cache.clear()
            cache[source] = read(ref)
        offset = ref['offset_frame'] + first - start
        audio = cache[source][offset * 2 : (offset + last - first) * 2]
        if len(audio) != (last - first) * 2:
            raise ValueError('retained reference shorter than its frame span')
        pcm[(first - lo) * 2 : (last - lo) * 2] = audio
    return bytes(pcm)


def owned_words(words: list[dict], chunk: Chunk) -> list[dict]:
    """The words ``chunk`` owns, on its unit's clock. A word without a start time cannot be placed."""
    shift = chunk.lo / SAMPLE_RATE
    kept = []
    for word in words:
        timing = word.get('timestamp') or ()
        if not timing or timing[0] is None:
            continue
        start = float(timing[0]) + shift
        end = None if len(timing) < 2 or timing[1] is None else float(timing[1]) + shift
        middle = (start + (start if end is None else end)) / 2
        if chunk.own_lo is not None and middle < chunk.own_lo / SAMPLE_RATE:
            continue
        if chunk.own_hi is not None and middle >= chunk.own_hi / SAMPLE_RATE:
            continue
        kept.append({**word, 'timestamp': [start, end]})
    return kept


def _transcribe_words(pcm: bytes, language: str | None) -> list[dict]:
    from utils.stt.pre_recorded import prerecorded_from_bytes

    return (
        prerecorded_from_bytes(
            pcm, sample_rate=SAMPLE_RATE, diarize=True, attempts=1, encoding='linear16', channels=1, language=language
        )
        or []
    )


def _transcribe(pcm: bytes, language: str | None) -> list[dict]:
    return _segments(_transcribe_words(pcm, language))


def _segments(words: list[dict]) -> list[dict]:
    from utils.stt.pre_recorded import postprocess_words
    from utils.sync.word_timing import first_word_offset

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


def _write_fenced(uid: str, conversation_id: str, segments: list[dict[str, Any]], *, fence):
    """The stored row and the account's batch privacy are judged again inside the write transaction.

    A delete, discard, lock or canonical projection committed since the pass's last read still wins,
    and so does an opt-out or privacy generation change made while the provider request was in flight.
    """
    from database.conversations import update_conversation_segments

    return update_conversation_segments(uid, conversation_id, segments, require_row=candidate, guard=fence)


def run(
    uid: str,
    conversation_id: str,
    row: dict,
    units: list,
    read,
    *,
    write=None,
    transcribe=None,
    transcribe_words=None,
    refresh=None,
    cut=None,
    authorize=None,
    privacy=None,
    fence=None,
) -> str:
    """Transcribe ``units`` and write them as provisional segments. Returns the counted outcome; never raises.

    ``row`` and ``refresh()`` must be decoded rows. ``authorize`` is the consent and funding gate;
    without it nothing is sent to a provider that ordinary batch processing would have held.
    ``privacy`` answers whether the account's current sync authorization and privacy generation
    still allow server work on this recording. It is asked before any audio is read and again
    before each provider call (chunked: before each round of chunk requests); a missing check, a
    False answer or an error all stop the pass. ``fence(transaction)`` is the same authority asked
    inside the default writer's transaction; it raises to refuse. The default writer never
    publishes without it.

    ``transcribe(pcm, language)`` returns one unit's lines (the serial kill-switch path);
    ``transcribe_words(pcm, language)`` returns one chunk's provider words (the chunked path).

    Runs on a worker thread: the cohort read is synchronous there (on the event loop a cold
    membership cache answers False). ``refresh`` re-reads the row before any audio leaves for the
    provider and again just before the write, so a delete, discard, lock, privacy change or
    canonical projection wins. ``cut`` stores the manual end only after the whole-recording
    transcript is written: a cut without it would lock a partial window on a multi-unit recording.
    """
    started = time.monotonic()
    try:
        outcome = _run(
            uid,
            conversation_id,
            row,
            units,
            read,
            write=write,
            transcribe=transcribe or _transcribe,
            transcribe_words=transcribe_words or _transcribe_words,
            refresh=refresh,
            cut=cut,
            authorize=authorize or funded,
            privacy=privacy,
            fence=fence,
        )
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=error exception_type=%s', type(error).__name__)
        outcome = 'error'
    OUTCOMES.labels(outcome).inc()
    if outcome == 'written':
        WALL_SECONDS.observe(time.monotonic() - started)
    logger.info('event=v3_fast_finish outcome=%s units=%s', outcome, len(units))
    return outcome


def _privacy_allows(privacy) -> bool:
    """Fail closed: no check, a refusal or an unavailable authority all mean no."""
    if privacy is None:
        return False
    try:
        return privacy() is True
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=privacy_blocked exception_type=%s', type(error).__name__)
        return False


class _Stopped(Exception):
    """A provider stage ended the pass early with a counted outcome."""

    def __init__(self, outcome: str):
        super().__init__(outcome)
        self.outcome = outcome


def _place(lines: list[dict], shift: float, duration: float) -> list[dict]:
    """One unit's lines on the recording clock, with no speaker number and padded outer edges."""
    lines = sorted(lines, key=lambda line: (line['start'], line['end']))
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
    return lines


def _serial_segments(units, read, language, origin, privacy, transcribe) -> list[dict]:
    """The kill-switch path: every unit's audio read up front, then one provider request per unit."""
    started = time.monotonic()
    try:
        audio = [(start, duration, unit_pcm(references, read)) for start, duration, references in units]
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=audio_error exception_type=%s', type(error).__name__)
        raise _Stopped('audio_error') from error
    SECONDS.labels('audio').observe(time.monotonic() - started)
    started = time.monotonic()
    segments: list[dict[str, Any]] = []
    try:
        for start, duration, pcm in audio:
            # Asked again at the provider boundary, before every unit: reading the audio and each
            # earlier provider request take time, and no unit may leave after the owner opted out.
            if not _privacy_allows(privacy):
                raise _Stopped('privacy_blocked')
            segments.extend(_place(transcribe(pcm, language), start - origin, duration))
    except _Stopped:
        raise
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=provider_error exception_type=%s', type(error).__name__)
        raise _Stopped('provider_error') from error
    SECONDS.labels('provider').observe(time.monotonic() - started)
    return segments


def _timed_words(transcribe_words, pcm: bytes, language: str | None) -> list[dict]:
    """One chunk's provider request, on the chunk pool. A leaf: it never waits on another pool."""
    started = time.monotonic()
    try:
        return transcribe_words(pcm, language) or []
    finally:
        PROVIDER_CHUNK_SECONDS.observe(time.monotonic() - started)


def _chunked_segments(units, read, language, origin, privacy, transcribe_words) -> list[dict]:
    """Every unit split into chunks of at most CHUNK_SECONDS, sent concurrently, stitched in order.

    At most PASS_CHUNK_WINDOW chunk buffers are alive at once, read or in flight. Each round reads
    the chunks that fit the window, asks ``privacy``, then submits them; a refusal, an audio error
    or one failed chunk stops the pass. Queued chunks are cancelled and running ones are waited for,
    so a stopped pass releases its slot only after its buffers are gone.
    """
    jobs = []
    for unit, (_, _, references) in enumerate(units):
        frames = max((ref['start_frame'] + ref['frames'] for ref in references), default=0)
        jobs.extend((unit, references, chunk) for chunk in chunk_plan(frames, silences(references)))
    CHUNKS.observe(len(jobs))
    pool = get_fast_finish_chunk_executor()
    words: list[list[dict]] = [[] for _ in jobs]
    in_flight: dict = {}
    cache: dict = {}
    position, reading = 0, 0.0
    started = time.monotonic()
    try:
        while position < len(jobs) or in_flight:
            batch = []
            read_started = time.monotonic()
            try:
                while position + len(batch) < len(jobs) and len(in_flight) + len(batch) < PASS_CHUNK_WINDOW:
                    _, references, chunk = jobs[position + len(batch)]
                    batch.append(window_pcm(references, read, chunk.lo, chunk.hi, cache))
            except Exception as error:
                logger.warning('event=v3_fast_finish outcome=audio_error exception_type=%s', type(error).__name__)
                raise _Stopped('audio_error') from error
            reading += time.monotonic() - read_started
            if batch:
                # Asked again at the provider boundary, before every round: reading the audio and
                # earlier provider requests take time, and no chunk may leave after the owner opted out.
                if not _privacy_allows(privacy):
                    raise _Stopped('privacy_blocked')
                # Popped, not iterated: no local name keeps a submitted buffer alive while the pass waits.
                while batch:
                    in_flight[pool.submit(_timed_words, transcribe_words, batch.pop(0), language)] = position
                    position += 1
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                index = in_flight.pop(future)
                try:
                    words[index] = owned_words(future.result(), jobs[index][2])
                except Exception as error:
                    logger.warning(
                        'event=v3_fast_finish outcome=provider_error exception_type=%s', type(error).__name__
                    )
                    raise _Stopped('provider_error') from error
    finally:
        cache.clear()
        for future in in_flight:
            future.cancel()
        wait(in_flight)
    SECONDS.labels('audio').observe(reading)
    # Chunked: the whole concurrent span, the interleaved audio reads included.
    SECONDS.labels('provider').observe(time.monotonic() - started)
    segments: list[dict[str, Any]] = []
    for unit, (start, duration, _) in enumerate(units):
        lines = [line for index, job in enumerate(jobs) if job[0] == unit for line in _segments(words[index])]
        segments.extend(_place(lines, start - origin, duration))
    return segments


def _run(
    uid,
    conversation_id,
    row,
    units,
    read,
    *,
    write,
    transcribe,
    refresh,
    cut,
    authorize,
    privacy,
    fence,
    transcribe_words=None,
) -> str:
    if not enabled(uid):
        return 'not_enabled'
    if write is None:
        if fence is None:
            # Fail closed: the default writer never publishes without the in-transaction privacy fence.
            return 'privacy_blocked'
        write = functools.partial(_write_fenced, fence=fence)
    if refresh is not None:
        # Admission read this row before staging. Nothing is sent to the provider on a stale grant.
        row = refresh()
    if not eligible(row):
        return 'ineligible'
    chunked = chunked_enabled()
    seconds = sum(duration for _, duration, _ in units)
    if not units or len(units) > MAX_UNITS or seconds > (CHUNKED_MAX_SECONDS if chunked else MAX_SECONDS):
        return 'too_long'
    if not authorize(uid, seconds, row.get('language')):
        return 'not_funded'
    # The owner may have turned sync off or changed privacy since this recording was captured and
    # admitted. Nothing is read from storage on a stale grant.
    if not _privacy_allows(privacy):
        return 'privacy_blocked'
    origin = row['started_at'].timestamp()
    try:
        if chunked:
            segments = _chunked_segments(
                units, read, row.get('language'), origin, privacy, transcribe_words or _transcribe_words
            )
        else:
            segments = _serial_segments(units, read, row.get('language'), origin, privacy, transcribe)
    except _Stopped as stopped:
        return stopped.outcome
    if not segments:
        return 'empty'
    segments.sort(key=lambda segment: (segment['start'], segment['end']))
    if refresh is not None and not eligible(refresh()):
        return 'superseded'
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    started = time.monotonic()
    try:
        # False: the row no longer qualifies, or the canonical record already projected.
        written = write(uid, conversation_id, segments)
    except BatchPrivacyBlocked:
        # The owner opted out, or the privacy generation moved, while the provider request ran.
        return 'privacy_blocked'
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
