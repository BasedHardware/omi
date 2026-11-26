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
- Chunks: ``CONVERSATIONS_V3_FAST_FINISH_CHUNKED`` (default on) splits every unit into chunks of at
  most five minutes and sends them to the provider concurrently, inside one end-to-end deadline
  (``PASS_DEADLINE_SECONDS`` from admission). A recording whose chunks cannot fit that deadline is
  refused before any spend. ``off`` restores one serial provider request per unit and the 20-minute cap.
- Long recordings (over 20 minutes, the spend that chunking adds) are a canary:
  ``CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT`` of owners by a salted uid bucket, and at most
  ``CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS`` of their audio per process per UTC day.
"""

import functools
import logging
import math
import os
import re
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, wait
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, NamedTuple

from prometheus_client import Counter, Histogram

from config.policy.batch import cohort_bucket
from config.refactor_modes import default_on
from config.rollout_cohorts import in_rollout_cohort
from utils.executors import get_fast_finish_chunk_executor

logger = logging.getLogger(__name__)

# Kill-switch path (CONVERSATIONS_V3_FAST_FINISH_CHUNKED=off): one provider request and one in-memory
# PCM buffer per unit, sent one after another: 20 min of 16 kHz mono is 38 MB.
MAX_SECONDS = 1200.0
# Units split at an audio gap over 30 s (and at one hour).
MAX_UNITS = 8
# Chunked path (default). Memory per pass does not depend on length: at most its window of
# five-minute chunk buffers (9.6 MB each) plus one decoded source pack.
CHUNK_SECONDS = 300.0
# A fixed cut repeats this much audio in both chunks. The earlier chunk owns what starts before the
# middle of the overlap; the later chunk's lines that start before it are trimmed at the seam.
CHUNK_OVERLAP_SECONDS = 3.0
# A retained-audio gap at least this long, near the even chunk length, is preferred as the cut.
MIN_SILENCE_SECONDS = 1.0
# One end-to-end budget, from record admission to the start of the transcript write: slot wait,
# audio reads, chunk queue wait, provider requests and one retry all count. It leaves the rest of the
# 60 s first-card target for the write, the builder and Home. Past it the pass cancels and yields to
# batch with outcome ``deadline``; provider timeouts are capped to it.
PASS_DEADLINE_SECONDS = 45.0
# A short pass (at most this many chunks, about 19.8 minutes) is one round: every chunk in flight at once.
PASS_CHUNK_WINDOW = 4
# A long pass keeps fewer in flight, so the six-worker chunk pool always has three workers for short
# Finishes, and must fit three rounds inside the deadline: at most 9 chunks, about 44.6 minutes.
LONG_PASS_WINDOW = 3
LONG_MAX_CHUNKS = 9
# A failed chunk is sent once more only if this much of the deadline is left.
RETRY_MIN_SECONDS = 10.0
# Tokens compared at a fixed cut's seam.
SEAM_TOKENS = 24
# A stopped pass waits for its running requests at most this long past the deadline, then releases
# its slot; a request still running ends on its own timeouts and its result is dropped.
STOP_GRACE_SECONDS = 2.0
# The language probe is skipped (and the pass stopped) with less than this left.
PROBE_MIN_SECONDS = 2.0
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
# Fixed buckets and fixed labels only: never a uid, a conversation id or any content.
# Chunked path only: chunks, chunk seconds, chunk queue seconds and provider audio seconds.
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
CHUNK_QUEUE_SECONDS = Histogram(
    'omi_conversations_v3_fast_finish_chunk_queue_seconds',
    'From a chunk submission to its start on the fast-finish chunk pool',
    buckets=(0.01, 0.1, 0.5, 1, 2, 5, 10, 20, 45),
)
AUDIO_SECONDS = Counter(
    'omi_conversations_v3_fast_finish_audio_seconds',
    'Provider audio seconds sent by chunked fast first transcripts, retries included, by path',
    ['path'],
)
for _path in ('short', 'long'):
    AUDIO_SECONDS.labels(_path)
# Every written pass, chunked or serial: from record admission (slot wait included) to its write and cut.
WALL_SECONDS = Histogram(
    'omi_conversations_v3_fast_finish_wall_seconds',
    'A written fast first transcript, from record admission to its write and cut',
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600),
)
for _outcome in (
    'written',
    'empty',
    'not_enabled',
    'ineligible',
    'too_long',
    'long_canary',
    'long_cap',
    'deadline',
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


LONG_PERCENT_ENV = 'CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT'
LONG_DAILY_SECONDS_ENV = 'CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS'
LONG_PERCENT_DEFAULT = 25.0
LONG_DAILY_SECONDS_DEFAULT = 7200.0
LONG_SALT = 'v3-fast-finish-long'


def _number(name: str, default: float) -> float:
    """A finite, non-negative env number; anything else fails closed to zero."""
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if math.isfinite(value) and value >= 0 else 0.0


def long_admitted(uid: str) -> bool:
    """The long-recording canary: a salted uid bucket below CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT."""
    percent = min(_number(LONG_PERCENT_ENV, LONG_PERCENT_DEFAULT), 100.0)
    return bool(uid) and percent > 0 and cohort_bucket(uid, LONG_SALT) < percent


class _DailyBudget:
    """Long-recording audio seconds this process may send per UTC day."""

    def __init__(self):
        self._lock = threading.Lock()
        self._day: str | None = None
        self._used = 0.0

    def _roll(self, now: datetime | None) -> None:
        day = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%d')
        if day != self._day:
            self._day, self._used = day, 0.0

    def room(self, seconds: float, *, now: datetime | None = None) -> bool:
        """Whether ``seconds`` more would fit today, without reserving them."""
        with self._lock:
            self._roll(now)
            return self._used + seconds <= _number(LONG_DAILY_SECONDS_ENV, LONG_DAILY_SECONDS_DEFAULT)

    def reserve(self, seconds: float, *, now: datetime | None = None) -> bool:
        with self._lock:
            self._roll(now)
            if self._used + seconds > _number(LONG_DAILY_SECONDS_ENV, LONG_DAILY_SECONDS_DEFAULT):
                return False
            self._used += seconds
            return True

    def settle(self, reserved: float, sent: float, *, now: datetime | None = None) -> None:
        """Replace a pass's reservation with the audio it actually sent: retries, overlaps and probe included."""
        with self._lock:
            self._roll(now)
            self._used = max(self._used + sent - reserved, 0.0)


class _Sent:
    """Provider audio seconds one pass has sent, from any thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self.seconds = 0.0

    def add(self, seconds: float) -> None:
        with self._lock:
            self.seconds += seconds


LONG_BUDGET = _DailyBudget()


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


def chunk_entries(words: list[dict], chunk: Chunk) -> list[dict]:
    """One chunk's provider entries on its unit's clock, without those the next chunk owns.

    Entries are words or whole utterances (Parakeet and Modulate return utterances lasting
    seconds, with no word timings). The next chunk owns what starts at or after this chunk's right
    boundary (the middle of a fixed cut's overlap). Nothing is dropped on the left here: ``join``
    decides that against what the previous chunk actually transcribed. A lone entry without timing
    (Parakeet's text-only fallback is stamped [0, 0]) spans the whole chunk.
    """
    shift = chunk.lo / SAMPLE_RATE
    own_hi = None if chunk.own_hi is None else chunk.own_hi / SAMPLE_RATE
    timed = [word for word in words if (word.get('timestamp') or (None,))[0] is not None]
    entries = []
    for word in timed:
        timing = word['timestamp']
        start = float(timing[0])
        end = None if len(timing) < 2 or timing[1] is None else float(timing[1])
        if len(timed) == 1 and start == 0 and not end:
            start, end = 0.0, (chunk.hi - chunk.lo) / SAMPLE_RATE
        start += shift
        end = None if end is None else end + shift
        if own_hi is not None and start >= own_hi:
            continue
        entries.append({**word, 'timestamp': [start, end]})
    return entries


def _end(entry: dict) -> float:
    timing = entry['timestamp']
    return timing[1] if timing[1] is not None else timing[0]


def _norm(token: str) -> str:
    return re.sub(r'\W', '', token.lower())


def _seam_overlap(tail: list[str], head: list[str]) -> tuple[int, int, int] | None:
    """(repeated tokens, head tokens skipped first, tail tokens skipped last), the longest repeat.

    The head repeats the end of the tail. Either side may carry one word clipped by its cut (the
    earlier chunk's last, the later chunk's first), so a match may skip it. A single repeated token
    counts only when it is the whole rest of the head: one common word is not evidence.
    """
    tail, head = [_norm(t) for t in tail], [_norm(t) for t in head]
    best = None
    for skip_tail in (0, 1):
        for skip_head in (0, 1):
            end, rest = tail[: len(tail) - skip_tail], head[skip_head:]
            for k in range(min(len(end), len(rest)), 0, -1):
                if end[len(end) - k :] == rest[:k] and all(rest[:k]) and (k >= 2 or k == len(rest)):
                    if best is None or k > best[0]:
                        best = (k, skip_head, skip_tail)
                    break
    return best


def seam(previous: list[dict], candidates: list[dict]) -> list[dict]:
    """Later-chunk lines that start before the previous chunk's last line ended, less what it holds.

    Both chunks heard that stretch. Where the head of the candidates' text repeats the end of the
    previous chunk's text, that head is dropped, with a clipped first word of the head and a clipped
    last word of the previous chunk. Without such a match, each candidate loses the share of its
    tokens that falls before the previous chunk's last end. ``previous`` may be edited in place.
    """
    if not candidates:
        return []
    candidates = sorted(candidates, key=lambda entry: entry['timestamp'][0])
    covered = max((_end(entry) for entry in previous), default=None)
    if covered is None or covered <= candidates[0]['timestamp'][0]:
        return candidates  # the previous chunk transcribed nothing of this stretch
    tail_tokens = [token for entry in previous for token in str(entry['text']).split()][-SEAM_TOKENS:]
    head = [(index, token) for index, entry in enumerate(candidates) for token in str(entry['text']).split()]
    match = _seam_overlap(tail_tokens, [token for _, token in head])
    drop = {index: 0 for index in range(len(candidates))}
    if match is not None:
        count, skip_head, skip_tail = match
        for index, _ in head[: skip_head + count]:
            drop[index] += 1
        if skip_tail:
            last = previous[-1]
            last['text'] = ' '.join(str(last['text']).split()[:-1])
    else:
        for index, entry in enumerate(candidates):
            start, end = entry['timestamp'][0], entry['timestamp'][1]
            if end is None or end <= start:
                drop[index] = len(str(entry['text']).split()) if start < covered else 0
                continue
            share = min(max((covered - start) / (end - start), 0.0), 1.0)
            drop[index] = round(share * len(str(entry['text']).split()))
    trimmed = []
    for index, entry in enumerate(candidates):
        tokens = str(entry['text']).split()[drop[index] :]
        if not tokens:
            continue
        start, end = entry['timestamp'][0], entry['timestamp'][1]
        if drop[index]:
            start = min(max(start, covered), end) if end is not None else max(start, covered)
        trimmed.append({**entry, 'text': ' '.join(tokens), 'timestamp': [start, end]})
    return trimmed


def _word_level(entries: list[dict]) -> bool:
    """Single words with their own timing: time alone tells which chunk heard them."""
    return all(
        len(str(entry['text']).split()) == 1 and _end(entry) - entry['timestamp'][0] <= CHUNK_OVERLAP_SECONDS / 2
        for entry in entries
    )


def join(previous: list[dict], entries: list[dict]) -> list[dict]:
    """A chunk's entries after the previous chunk of its unit: what both heard is kept once.

    Every entry that starts before the previous chunk's last line ended is compared. Words (one
    token each, with word timing) go by time: one whose middle falls inside what the previous chunk
    covered is its copy. Utterances go by text, in ``seam``.
    """
    covered = max((_end(entry) for entry in previous), default=None)
    if covered is None:
        return entries
    candidates = [entry for entry in entries if entry['timestamp'][0] < covered]
    rest = [entry for entry in entries if entry['timestamp'][0] >= covered]
    if not candidates:
        return entries
    if _word_level(candidates):
        kept = [entry for entry in candidates if (entry['timestamp'][0] + _end(entry)) / 2 >= covered]
        return kept + rest
    return seam(previous, candidates) + rest


def _transcribe_words(pcm: bytes, language: str | None, *, route=None, deadline: float | None = None) -> list[dict]:
    """One provider request. ``route`` reuses a pass's language decision; ``deadline`` caps its timeouts.

    Under ``verification_stt_deadline`` every HTTP timeout is the time left, an expired deadline
    raises before sending, and the provider's own retry and Soniox credit failover stay off: the
    pass owns its one retry and yields to batch, which keeps both.
    """
    from utils.stt.pre_recorded import prerecorded_from_bytes, verification_stt_deadline

    with verification_stt_deadline(deadline) if deadline is not None else nullcontext():
        return (
            prerecorded_from_bytes(
                pcm,
                sample_rate=SAMPLE_RATE,
                diarize=True,
                attempts=1,
                encoding='linear16',
                channels=1,
                language=language,
                # Only a chunked pass carries a route: the serial kill-switch path calls the provider as before.
                **({'route': route} if route is not None else {}),
            )
            or []
        )


def _routed_transcriber(pcm: bytes, language: str | None, deadline: float, privacy, sent: '_Sent'):
    """The pass's provider call, with the language resolved once, on its first chunk's audio.

    Resolving may post up to 30 s of that audio to the vendor (or self-hosted) language probe. The
    privacy authority is asked right before either probe sends, the vendor probe's timeouts share
    what is left of the deadline, and its audio is charged to the pass.
    """
    from utils.stt.batch_language import MAX_PROBE_SECONDS
    from utils.stt.pre_recorded import verification_stt_deadline
    from utils.stt.prerecorded_route import prerecorded_bytes_route

    stopped: list[str] = []

    def allowed(*, vendor: bool) -> bool:
        if deadline - time.monotonic() < PROBE_MIN_SECONDS:
            stopped.append('deadline')
            return False
        if not _privacy_allows(privacy):
            stopped.append('privacy_blocked')
            return False
        if vendor:
            sent.add(min(len(pcm) / 2 / SAMPLE_RATE, MAX_PROBE_SECONDS))
        return True

    with verification_stt_deadline(deadline):
        route = prerecorded_bytes_route(
            pcm,
            language,
            sample_rate=SAMPLE_RATE,
            channels=1,
            encoding='linear16',
            before_probe=lambda: allowed(vendor=True),
            before_self_probe=lambda: allowed(vendor=False),
        )
    if stopped:
        raise _Stopped(stopped[0])
    return functools.partial(_transcribe_words, route=route, deadline=deadline)


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


def plan(units: list) -> list[tuple[int, list[dict], Chunk]]:
    """Every chunk of the recording, in order: (unit index, the unit's references, chunk)."""
    jobs = []
    for unit, (_, _, references) in enumerate(units):
        frames = max((ref['start_frame'] + ref['frames'] for ref in references), default=0)
        jobs.extend((unit, references, chunk) for chunk in chunk_plan(frames, silences(references)))
    return jobs


def long_recording(units: list) -> bool:
    """Over the serial path's 20 minutes: audio only the chunked path sends, and the long canary's."""
    return sum(duration for _, duration, _ in units) > MAX_SECONDS


def planned_seconds(jobs: list) -> float:
    """Provider audio the chunks carry, overlaps included."""
    return sum(chunk.hi - chunk.lo for _, _, chunk in jobs) / SAMPLE_RATE


def pass_class(units: list) -> str:
    """Which pass slot a recording takes: ``serial`` (kill switch), ``short`` or ``long``.

    Long means over 20 minutes of audio, never merely many chunks: a six-minute Finish split into
    six units, or one 19.9-minute unit of five chunks, is short and keeps the short slots.
    """
    if not chunked_enabled():
        return 'serial'
    return 'long' if long_recording(units) else 'short'


def screen(uid: str, units: list) -> str | None:
    """The checks that need only the units, safe before a pass slot is taken; None passes.

    Length (``too_long``), the long canary (``long_canary``) and room under its daily cap
    (``long_cap``), so a Finish that would be refused never holds a slot or reads anything.
    """
    if not units or len(units) > MAX_UNITS:
        return 'too_long'
    if not chunked_enabled():
        return 'too_long' if long_recording(units) else None
    if not long_recording(units):
        return None
    jobs = plan(units)
    # Refused before any spend: more chunks than three long rounds cannot meet the deadline.
    if len(jobs) > LONG_MAX_CHUNKS:
        return 'too_long'
    if not long_admitted(uid):
        return 'long_canary'
    if not LONG_BUDGET.room(planned_seconds(jobs)):
        return 'long_cap'
    return None


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
    deadline: float | None = None,
) -> str:
    """Transcribe ``units`` and write them as provisional segments. Returns the counted outcome; never raises.

    ``row`` and ``refresh()`` must be decoded rows. ``authorize`` is the consent and funding gate;
    without it nothing is sent to a provider that ordinary batch processing would have held.
    ``privacy`` answers whether the account's current sync authorization and privacy generation
    still allow server work on this recording. It is asked before any audio is read and again at
    every provider dispatch (serial: before each unit; chunked: inside each chunk job, just before
    its request and its retry, so a chunk that waited in the pool's queue is asked when it starts);
    a missing check, a False answer or an error all stop the pass. Cancelling a stopped pass stops
    its queued chunks; a request already dispatched may finish, but its result is never written.
    ``fence(transaction)`` is the same authority asked inside the default writer's transaction; it
    raises to refuse. The default writer never publishes without it.

    ``transcribe(pcm, language)`` returns one unit's lines (the serial kill-switch path);
    ``transcribe_words(pcm, language)`` returns one chunk's provider entries (the chunked path).
    ``deadline`` (``time.monotonic()``) is the end-to-end budget set at admission; without one the
    pass starts its own ``PASS_DEADLINE_SECONDS``. The serial path keeps today's behaviour and has none.

    Runs on a worker thread: the cohort read is synchronous there (on the event loop a cold
    membership cache answers False). ``refresh`` re-reads the row before any audio leaves for the
    provider and again just before the write, so a delete, discard, lock, privacy change or
    canonical projection wins. ``cut`` stores the manual end only after the whole-recording
    transcript is written: a cut without it would lock a partial window on a multi-unit recording.
    """
    if deadline is None:
        deadline = time.monotonic() + PASS_DEADLINE_SECONDS
    try:
        outcome = _run(
            uid,
            conversation_id,
            row,
            units,
            read,
            write=write,
            transcribe=transcribe or _transcribe,
            transcribe_words=transcribe_words,
            refresh=refresh,
            cut=cut,
            authorize=authorize or funded,
            privacy=privacy,
            fence=fence,
            deadline=deadline,
        )
    except Exception as error:
        logger.warning('event=v3_fast_finish outcome=error exception_type=%s', type(error).__name__)
        outcome = 'error'
    OUTCOMES.labels(outcome).inc()
    if outcome == 'written':
        WALL_SECONDS.observe(time.monotonic() - (deadline - PASS_DEADLINE_SECONDS))
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


class _Refused(Exception):
    """The privacy authority refused a chunk at its dispatch."""


class _Expired(Exception):
    """The pass deadline passed before a chunk could be sent."""


def _chunk_job(
    call, pcm: bytes, language, privacy, deadline: float, submitted: float, path: str, sent: _Sent
) -> list[dict]:
    """One chunk on the chunk pool: privacy at dispatch, the provider request, at most one retry.

    A leaf: it never waits on another pool. Holds its own buffer until it returns.
    """
    CHUNK_QUEUE_SECONDS.observe(time.monotonic() - submitted)
    seconds = len(pcm) / 2 / SAMPLE_RATE
    for attempt in (1, 2):
        if time.monotonic() >= deadline:
            raise _Expired()
        # At actual dispatch: a chunk can wait in the shared pool's queue, and consent may change
        # meanwhile. The round that submitted it was authorized; this request may still not leave.
        if not _privacy_allows(privacy):
            raise _Refused()
        started = time.monotonic()
        AUDIO_SECONDS.labels(path).inc(seconds)
        sent.add(seconds)
        try:
            return call(pcm, language) or []
        except Exception as error:
            if attempt == 2 or deadline - time.monotonic() < RETRY_MIN_SECONDS:
                raise
            logger.info('event=v3_fast_finish_chunk_retry exception_type=%s', type(error).__name__)
        finally:
            PROVIDER_CHUNK_SECONDS.observe(time.monotonic() - started)
    raise AssertionError('unreachable')


def _chunked_segments(
    jobs, units, read, language, origin, privacy, transcribe_words, deadline, path, sent: _Sent
) -> list[dict]:
    """Every chunk sent concurrently within the deadline, then stitched in order.

    At most the pass's window of chunk buffers is alive at once, read or in flight (PASS_CHUNK_WINDOW
    for a short pass, whatever its chunk count, LONG_PASS_WINDOW for a long one). A refusal at
    dispatch, an audio error, a chunk that fails twice or the deadline stops the pass: queued chunks
    are cancelled, and running ones are waited for only until the deadline plus STOP_GRACE_SECONDS,
    so a stopped pass releases its slot promptly. A request still running then ends on its own
    timeouts, which share what was left of the deadline when it was sent; its result is never written.
    """
    CHUNKS.observe(len(jobs))
    window = LONG_PASS_WINDOW if path == 'long' else PASS_CHUNK_WINDOW
    pool = get_fast_finish_chunk_executor()
    raw: list[list[dict]] = [[] for _ in jobs]
    in_flight: dict = {}
    cache: dict = {}
    call = transcribe_words
    position, reading = 0, 0.0
    started = time.monotonic()
    try:
        while position < len(jobs) or in_flight:
            if time.monotonic() >= deadline:
                raise _Stopped('deadline')
            batch = []
            read_started = time.monotonic()
            try:
                while position + len(batch) < len(jobs) and len(in_flight) + len(batch) < window:
                    if time.monotonic() >= deadline:
                        raise _Stopped('deadline')
                    _, references, chunk = jobs[position + len(batch)]
                    batch.append(window_pcm(references, read, chunk.lo, chunk.hi, cache))
            except _Stopped:
                raise
            except Exception as error:
                logger.warning('event=v3_fast_finish outcome=audio_error exception_type=%s', type(error).__name__)
                raise _Stopped('audio_error') from error
            reading += time.monotonic() - read_started
            if batch and call is None:
                try:
                    call = _routed_transcriber(batch[0], language, deadline, privacy, sent)
                except _Stopped:
                    raise
                except Exception as error:
                    logger.warning(
                        'event=v3_fast_finish outcome=provider_error stage=route exception_type=%s',
                        type(error).__name__,
                    )
                    raise _Stopped('deadline' if time.monotonic() >= deadline else 'provider_error') from error
            # Popped, not iterated: no local name keeps a submitted buffer alive while the pass waits.
            while batch:
                future = pool.submit(
                    _chunk_job, call, batch.pop(0), language, privacy, deadline, time.monotonic(), path, sent
                )
                in_flight[future] = position
                position += 1
            done, _ = wait(in_flight, timeout=max(deadline - time.monotonic(), 0), return_when=FIRST_COMPLETED)
            if not done:
                raise _Stopped('deadline')
            for future in done:
                index = in_flight.pop(future)
                try:
                    raw[index] = future.result()
                except _Refused as error:
                    raise _Stopped('privacy_blocked') from error
                except (_Expired, TimeoutError) as error:
                    logger.warning('event=v3_fast_finish outcome=deadline exception_type=%s', type(error).__name__)
                    raise _Stopped('deadline') from error
                except Exception as error:
                    expired = time.monotonic() >= deadline
                    logger.warning(
                        'event=v3_fast_finish outcome=%s exception_type=%s',
                        'deadline' if expired else 'provider_error',
                        type(error).__name__,
                    )
                    raise _Stopped('deadline' if expired else 'provider_error') from error
    finally:
        cache.clear()
        for future in in_flight:
            future.cancel()
        _, running = wait(in_flight, timeout=max(deadline - time.monotonic(), 0) + STOP_GRACE_SECONDS)
        if running:
            logger.info('event=v3_fast_finish_abandoned requests=%s', len(running))
    SECONDS.labels('audio').observe(reading)
    # Chunked: the whole concurrent span, the interleaved audio reads included.
    SECONDS.labels('provider').observe(time.monotonic() - started)
    return _stitch(jobs, raw, units, origin)


def _stitch(jobs, raw, units, origin) -> list[dict]:
    """Each unit's chunks in order: owned entries, the seam trimmed, then lines on the recording clock."""
    entries: list[list[dict]] = []
    for index, (unit, _, chunk) in enumerate(jobs):
        own = chunk_entries(raw[index], chunk)
        if index and jobs[index - 1][0] == unit:
            own = join(entries[-1], own)
        entries.append(sorted(own, key=lambda entry: entry['timestamp'][0]))
    segments: list[dict[str, Any]] = []
    for unit, (start, duration, _) in enumerate(units):
        lines = [line for index, job in enumerate(jobs) if job[0] == unit for line in _segments(entries[index])]
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
    deadline: float | None = None,
) -> str:
    if deadline is None:
        deadline = time.monotonic() + PASS_DEADLINE_SECONDS
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
    # Length, the long canary and room under its daily cap: admission asked these before taking a
    # slot; they are asked again here for direct callers and a cap that filled meanwhile.
    refused = screen(uid, units)
    if refused is not None:
        return refused
    chunked = chunked_enabled()
    seconds = sum(duration for _, duration, _ in units)
    jobs = plan(units) if chunked else []
    # Audio the serial path never sent: the canary and its daily cap bound this added spend.
    long_audio = chunked and long_recording(units)
    if not authorize(uid, seconds, row.get('language')):
        return 'not_funded'
    # The owner may have turned sync off or changed privacy since this recording was captured and
    # admitted. Nothing is read from storage on a stale grant.
    if not _privacy_allows(privacy):
        return 'privacy_blocked'
    reserved = planned_seconds(jobs) if long_audio else 0.0
    if long_audio and not LONG_BUDGET.reserve(reserved):
        return 'long_cap'
    origin = row['started_at'].timestamp()
    sent = _Sent()
    try:
        if chunked:
            path = 'long' if long_audio else 'short'
            segments = _chunked_segments(
                jobs, units, read, row.get('language'), origin, privacy, transcribe_words, deadline, path, sent
            )
        else:
            segments = _serial_segments(units, read, row.get('language'), origin, privacy, transcribe)
    except _Stopped as stopped:
        return stopped.outcome
    finally:
        if long_audio:
            # Charge what was actually sent (retries and the language probe included, chunks never
            # sent refunded), not the reservation.
            LONG_BUDGET.settle(reserved, sent.seconds)
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
