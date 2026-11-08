"""Option A: prove the server holds a byte-exact durable copy of an upload's WAL.

David's custody ruling (2026-11-08): once every sample of an upload's WAL is
held server-side byte for byte, the upload is answered with the existing
covered 200 and the phone may release those WALs, so its drain advances past a
closed record's first 300 s batch. This module is only the proof; the gap-fill
entry decides whether it runs and the caller sends the response.

Proof rules (fail closed on anything else):
- Re-list ``chunks/{uid}/{cid}/`` with the raw archive required; nothing
  in memory from the fill counts.
- Only lossless sources count: single-chunk ``.bin``/``.enc`` objects whose PCM
  is 16 kHz. Opus, batch packs and raw-live captures never count.
- Each counted object lives in the private-cloud-sync or derived audio bucket
  (neither has a delete lifecycle rule on chunks/) and is read pinned to its
  listed generation.
- Every WAL sample, decoded one file at a time (once, before the fill: decoding
  consumes the uploaded files), must equal the sample at the
  same capture time in at least one counted object, and lie inside the record's
  ``[started_at - 1 s, finished_at + 1 s]`` window.
Logs and metrics carry only hashed keys and closed vocabularies.
"""

import io
import logging
import math
import wave

from prometheus_client import Counter

from config.record_gap_fill import FINISH_SLACK_SECONDS, MAX_FILL_SECONDS, PIECE_SECONDS
from utils import encryption
from utils.batch_pipeline.source_audio import read_reference
from utils.observability.reasons import ReasonFamily, RecordRetainedAckOutcome, reason_label
from config.audio_archive import derived_audio_bucket
from utils.other.storage import list_audio_chunks, private_cloud_sync_bucket

logger = logging.getLogger(__name__)

RATE = 16000
# A fill object's 6-decimal key is within 1 us of its sample grid.
GRID_TOLERANCE = 0.01
MAX_LOSSLESS_OBJECTS = 128
RETAINED_ACK_TOTAL = Counter(
    'omi_record_retained_ack_total',
    'Option A byte-exact retained-copy proofs by outcome (dark unless RECORD_RETAINED_ACK is on)',
    ['outcome'],
)


def _pcm(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        return stream.readframes(stream.getnframes())


def lossless_source(chunk: dict) -> bool:
    path = chunk.get('path') or ''
    name = path.rsplit('/', 1)[-1]
    return (
        path.startswith('chunks/')
        and not chunk.get('is_batch')
        and '.opus' not in name
        and '.batch.' not in name
        and (name.endswith('.bin') or name.endswith('.enc'))
        and 'raw_offset_samples' not in chunk
    )


def _wal_units(units):
    for unit in units:
        yield unit.capture_at, _pcm(unit.wav)


def _held(uid, conversation_id, chunks, client, low, high):
    """Counted lossless objects overlapping [low, high): (start, pcm), plus lossy spans."""
    allowed = {private_cloud_sync_bucket, derived_audio_bucket()}
    key = encryption.derive_key(uid)
    held, lossy = [], []
    for chunk in chunks:
        start = float(chunk['timestamp'])
        # A fill piece is at most PIECE_SECONDS long; anything longer that
        # starts earlier is not read, so its samples stay unproven.
        if start >= high or start < low - PIECE_SECONDS - 1:
            continue
        # Only the lifecycle-safe archive buckets count (never batch staging,
        # which expires every object at 30 days).
        if chunk.get('bucket', private_cloud_sync_bucket) not in allowed:
            continue
        if not lossless_source(chunk):
            lossy.append(start)
            continue
        if len(held) >= MAX_LOSSLESS_OBJECTS:
            raise OverflowError('retained ack source budget exceeded')
        ref = {
            'path': chunk['path'],
            'bucket': chunk.get('bucket', private_cloud_sync_bucket),
            'generation': int(chunk['generation']),
        }
        # The listing's span rate is authoritative, exactly as admission reads it.
        if chunk.get('span'):
            ref['sample_rate'] = int(chunk['span'].get('sample_rate', RATE))
        pcm = read_reference(client, ref, uid, conversation_id, allowed, key, source_metadata=True, listed_source=chunk)
        if int(ref.get('sample_rate', RATE)) != RATE or not pcm or len(pcm) % 2:
            lossy.append(start)
            continue
        held.append((start, pcm))
    return held, lossy


def _matching(held, wal) -> int:
    """Leading samples of equal-length ``held`` and ``wal`` that are byte-equal."""
    if held == wal:
        return len(wal) // 2
    low, high = 0, len(wal) // 2  # held[:low] matches; held[:high] does not
    while high - low > 1:
        mid = (low + high) // 2
        if held[: mid * 2] == wal[: mid * 2]:
            low = mid
        else:
            high = mid
    return low


def _covering(held, at):
    """Objects holding the sample at ``at`` on its grid, as (offset_samples, pcm)."""
    for start, pcm in held:
        exact = (at - start) * RATE
        offset = round(exact)
        if abs(exact - offset) <= GRID_TOLERANCE and 0 <= offset < len(pcm) // 2:
            yield offset, pcm


def prove(uid, conversation_id, wal, client, *, finish, started) -> str:
    """Return 'acked' or a closed refusal; read-only. ``wal`` is the decoded upload."""
    units = list(_wal_units(wal))
    if not units:
        return 'skipped_uncovered'
    total = sum(len(pcm) // 2 for _, pcm in units) / RATE
    if total > MAX_FILL_SECONDS:
        return 'skipped_bounds'
    low = started - FINISH_SLACK_SECONDS if started is not None else None
    high = finish + FINISH_SLACK_SECONDS
    wal_low = min(capture for capture, _ in units)
    wal_high = max(capture + len(pcm) / (2 * RATE) for capture, pcm in units)
    if low is None or wal_low < low - 1e-6 or wal_high > high + 1e-6:
        return 'skipped_outside_record'
    chunks = list_audio_chunks(uid, conversation_id, max_count=4096, require_archive=True)
    try:
        held, lossy = _held(uid, conversation_id, chunks, client, wal_low, wal_high)
    except OverflowError:
        return 'skipped_bounds'
    for capture, pcm in units:
        frames = len(pcm) // 2
        cursor = 0
        while cursor < frames:
            at = capture + cursor / RATE
            best, differs = 0, False
            for offset, source in _covering(held, at):
                length = min(frames - cursor, len(source) // 2 - offset)
                matched = _matching(
                    memoryview(source)[offset * 2 : (offset + length) * 2],
                    memoryview(pcm)[cursor * 2 : (cursor + length) * 2],
                )
                # A matching prefix still counts; another object may hold the rest.
                best = max(best, matched)
                differs = differs or matched < length
            if best == 0:
                if differs:
                    return 'skipped_bytes_differ'
                if any(math.isclose(start, at, abs_tol=PIECE_SECONDS) for start in lossy):
                    return 'skipped_lossy_source'
                return 'skipped_uncovered'
            cursor += best
    return 'acked'


def report(outcome: str, record: str) -> str:
    RETAINED_ACK_TOTAL.labels(
        outcome=reason_label(ReasonFamily.RECORD_RETAINED_ACK, outcome, RecordRetainedAckOutcome)
    ).inc()
    logger.info('event=sync_record_retained_ack outcome=%s record=%s', outcome, record[:16])
    return outcome
