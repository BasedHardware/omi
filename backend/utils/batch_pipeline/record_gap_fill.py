"""Fill a closed record's missing retained tail from its owner's WAL (dark by default).

A closed record whose retained audio under ``chunks/{uid}/{cid}/`` is empty or
stops before ``finished_at`` can never pass ``validate_record_tail``, and its
pending obligation has no TTL. The owner's phone still holds that audio, but its
upload only reaches ``record_jobs_missing`` and keeps the WAL. Neither side
moves. This writes the WAL audio for the missing span as new, tagged,
create-only retained objects, so the drain's next normal admission pass can
admit the record. Admission, the GPU path and projection are unchanged.

Custody rules:
- Only the owning device's upload reaches the caller (owner context checked),
  only for a closed record with no record jobs, and only once its row has been
  settled for ``CLOSED_MIN_SECONDS``.
- Nothing before the retained end (admission's own walk) or after
  ``finished_at + FINISH_SLACK_SECONDS`` is written, so a fill never overlaps
  retained audio and retained audio stays authoritative for every span it has.
- Writes are create-only at keys no other writer produces
  (``gap_fill_chunk_path``); nothing is ever overwritten or deleted.
- Logs and metrics carry only hashed keys and closed vocabularies.
"""

import hashlib
import io
import logging
import math
import time
import wave
from datetime import datetime

from google.api_core.exceptions import PreconditionFailed
from prometheus_client import Counter

from config import audio_archive

from config.record_audio import record_identity, require_record_audio_barrier
from config.record_gap_fill import (
    CLOSED_MIN_SECONDS,
    FINISH_SLACK_SECONDS,
    MARKER_SECONDS,
    MAX_FILL_SECONDS,
    PIECE_SECONDS,
    gap_fill_enabled,
)
from database import users as users_db
from database.audio_timeline import span_blob_metadata
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.sync_record_wait_cache import claim_gap_fill_marker
from utils import encryption
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.live import retained_record_units
from utils.executors import db_executor, run_blocking, storage_executor
from utils.other.local_storage import create_storage_client
from utils.other.storage import list_audio_chunks, owner_storage_write_gate, private_cloud_sync_bucket
from utils.sync.files import get_timestamp_from_path

logger = logging.getLogger(__name__)

RATE = 16000
# validate_record_tail's own slack: a fill continues held audio within this.
TAIL_TOLERANCE_SECONDS = 0.1
RENDITION = 'gap-fill-v1'
OUTCOMES = frozenset(
    {
        'written',
        'skipped_gate',
        'skipped_recent',
        'skipped_marker',
        'skipped_no_pending',
        'skipped_retained',
        'skipped_no_gap',
        'skipped_no_audio',
        'skipped_not_contiguous',
        'skipped_collision',
        'failed',
    }
)
GAP_FILL_TOTAL = Counter(
    'omi_record_gap_fill_total',
    'Closed-record gap fills from the owner WAL by outcome (dark unless RECORD_GAP_FILL is on)',
    ['outcome'],
)


def gap_fill_chunk_path(uid: str, conversation_id: str, timestamp: float, protection_level: str) -> str:
    """Key of a phone-WAL gap-fill object; no other writer can produce it.

    Every other ``chunks/`` writer names objects with a 3-decimal timestamp
    (``{ts:.3f}.opus``/``.enc``/``.bin`` and ``{a:.3f}-{b:.3f}.batch.*``). Six
    decimals can never equal one of those names, so a later pusher or sync
    upload never targets (or overwrites) a gap-fill object, and a gap-fill write
    never targets theirs. The suffix is lossless PCM16 (``.bin``/``.enc``),
    which admission and playback already decode.
    """
    suffix = 'enc' if protection_level == 'enhanced' else 'bin'
    return f'chunks/{uid}/{conversation_id}/{timestamp:.6f}.{suffix}'


def gap_fill_bucket(uid: str, client=None):
    """The bucket ``upload_audio_chunk`` would use; both are listed and admitted."""
    client = client if client is not None else create_storage_client()
    regional = (
        audio_archive.regional_bucket(uid, private_cloud_sync_bucket) if audio_archive.admitted(uid, 'SYNC') else None
    )
    return client.bucket(regional or private_cloud_sync_bucket)


def create_gap_fill_chunk(
    pcm: bytes, uid: str, conversation_id: str, timestamp: float, protection_level: str, metadata: dict, *, bucket
) -> str | None:
    """Create-only write of one gap-fill PCM16 object; None if the key exists.

    Unlike ``upload_audio_chunk`` there is no overwrite fallback: an existing
    object at the key always wins and this write is skipped.
    """
    if not pcm or len(pcm) % 2:
        raise ValueError('gap fill needs aligned PCM16')
    path = gap_fill_chunk_path(uid, conversation_id, timestamp, protection_level)
    payload = encryption.encrypt_audio_chunk(pcm, uid) if protection_level == 'enhanced' else pcm
    with owner_storage_write_gate(uid, bucket):
        blob = bucket.blob(path)
        blob.metadata = {
            **span_blob_metadata({'start': timestamp, 'samples': len(pcm) // 2, 'sample_rate': RATE}),
            **metadata,
            'canonical': 'false',
            'codec': 'pcm16',
            'record_sample_rate': str(RATE),
        }
        try:
            blob.upload_from_string(payload, content_type='application/octet-stream', if_generation_match=0)
        except PreconditionFailed:
            return None
    return path


def _epoch(value) -> float | None:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _seconds_bucket(seconds: float) -> str:
    if seconds < 10:
        return '0-10'
    if seconds < 60:
        return '10-60'
    if seconds < 600:
        return '60-600'
    return '600+'


def _pcm(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        return stream.readframes(stream.getnframes())


def retained_end(uid, conversation_id, chunks, client, key) -> float | None:
    """Admission's own retained walk; the end of its last unit, None with no chunks."""
    if not chunks:
        return None
    units = 0
    end = None
    iterator = retained_record_units(uid, conversation_id, chunks, client, key)
    try:
        for start, duration, _ in iterator:
            units += 1
            if units > 128:
                raise ValueError('retained capture unit budget exceeded')
            end = start + duration
    finally:
        iterator.close()
    return end


def _source_units(paths):
    """Decode each WAL file on its own, in capture order.

    ``decode_units`` joins files up to 30 s apart with zero PCM. Here that
    silence would hide a real hole from the contiguity check, so the fill
    sees every source-file gap.
    """
    for path in sorted(paths, key=lambda value: (get_timestamp_from_path(value), value)):
        yield from decode_units([path])


def _write_window(uid, conversation_id, paths, lower, upper, anchor, tolerance, protection_level, metadata, bucket):
    """Write WAL PCM inside [lower, upper) create-only, contiguous from ``anchor``.

    Returns (written, collisions, seconds, gapped). Admission checks only the
    final end, so a fill that skipped ahead would let a record admit with a
    hole the drain could never fill again. Writing stops at the first WAL
    sample more than ``tolerance`` after the audio already held (the retained
    end or the previous written piece); a later upload continues from there.
    """
    written = collisions = 0
    budget = MAX_FILL_SECONDS * RATE
    expected = anchor
    gapped = False
    for unit in _source_units(paths):
        if budget <= 0:
            break
        pcm = _pcm(unit.wav)
        frames = len(pcm) // 2
        # ``first`` is the first WAL sample at or after the retained end, so a
        # fill object never starts before it under any sample rounding.
        first = 0 if lower is None else max(0, math.ceil((lower - unit.capture_at) * RATE - 1e-6))
        last = min(frames, math.floor((upper - unit.capture_at) * RATE + 1e-6), first + budget)
        if first >= last:
            continue
        if unit.capture_at + first / RATE - expected > tolerance:
            gapped = True
            break
        cursor = first
        while cursor < last:
            count = min(last - cursor, PIECE_SECONDS * RATE)
            timestamp = round(unit.capture_at + cursor / RATE, 6)
            path = create_gap_fill_chunk(
                pcm[cursor * 2 : (cursor + count) * 2],
                uid,
                conversation_id,
                timestamp,
                protection_level,
                metadata,
                bucket=bucket,
            )
            if path is None:
                collisions += 1
            else:
                written += 1
            budget -= count
            cursor += count
        expected = unit.capture_at + last / RATE
        tolerance = TAIL_TOLERANCE_SECONDS
        # An overlapping later WAL unit must start after what this fill wrote,
        # exactly as it must start after retained audio.
        lower = expected if lower is None else max(lower, expected)
        del pcm
    return written, collisions, (MAX_FILL_SECONDS * RATE - budget) / RATE, gapped


def _gates(uid, conversation_id, row, record, segment, wal, store, now):
    """Row, job, privacy and marker gates; Firestore/Redis only, no audio read.

    Returns a refusal outcome, or None to proceed to the storage phase.
    """
    try:
        require_record_audio_barrier(row)
    except ValueError:
        return 'skipped_gate'
    if (
        row.get('record_audio_partial')
        or row.get('deleted')
        or row.get('discarded')
        or not row.get('private_cloud_sync_enabled')
    ):
        return 'skipped_gate'
    finish = _epoch(row.get('finished_at'))
    if finish is None:
        return 'skipped_gate'
    # Settled: the capture finished, and no row write (close, upload session
    # release, finalization) happened, at least CLOSED_MIN_SECONDS ago.
    settled = max(finish, _epoch(row.get('updated_at')) or finish)
    if now - settled < CLOSED_MIN_SECONDS:
        return 'skipped_recent'

    def read(tx):
        # Privacy first: nothing of this record is read past a block.
        tx.check_privacy(uid, (conversation_id,))
        return tx.get('jobs', segment)

    try:
        pending = store.run(read)
    except BatchPrivacyBlocked:
        return 'skipped_gate'
    # Only a registered record_pending obligation is drained into admission.
    # A record that canonical registration refused (for example server-batch
    # only with no server audio) or never registered gains nothing from audio.
    if (
        (pending or {}).get('state') != 'record_pending'
        or pending.get('record_content_id') != record
        or pending.get('owner_id') != uid
        or pending.get('conversation_id') != conversation_id
    ):
        return 'skipped_no_pending'
    if not claim_gap_fill_marker(record, wal, MARKER_SECONDS):
        return 'skipped_marker'
    return None


def _write(uid, conversation_id, row, paths, record, wal, storage_client, bucket, protection_level):
    """Storage phase: admission's retained walk, then the clipped create-only write."""
    finish = _epoch(row.get('finished_at'))
    assert finish is not None
    client = storage_client if storage_client is not None else create_storage_client()
    chunks = list_audio_chunks(uid, conversation_id, max_count=4096, require_archive=True)
    try:
        end = retained_end(uid, conversation_id, chunks, client, encryption.derive_key(uid))
    except ValueError:
        # Admission would refuse this retained set for another reason; adding
        # audio cannot help and must not change which refusal it reports.
        return 'skipped_retained', 0.0
    if end is not None and end + 0.1 >= finish:
        return 'skipped_no_gap', 0.0
    if end is not None:
        lower, anchor, tolerance = end, end, TAIL_TOLERANCE_SECONDS
    else:
        started = _epoch(row.get('started_at'))
        if started is None:
            return 'skipped_gate', 0.0
        # Nothing retained: the fill must begin at the capture's own start.
        lower, anchor, tolerance = started - FINISH_SLACK_SECONDS, started, FINISH_SLACK_SECONDS
    if protection_level is None:
        protection_level = users_db.get_data_protection_level(uid)
    metadata = {'source': 'phone_wal', 'rendition': RENDITION, 'record': record[:16], 'wal': wal[:16]}
    if bucket is None:
        bucket = gap_fill_bucket(uid, client)
    written, collisions, seconds, gapped = _write_window(
        uid,
        conversation_id,
        paths,
        lower,
        finish + FINISH_SLACK_SECONDS,
        anchor,
        tolerance,
        protection_level,
        metadata,
        bucket,
    )
    if written:
        return 'written', seconds
    if collisions:
        return 'skipped_collision', seconds
    return ('skipped_not_contiguous' if gapped else 'skipped_no_audio'), seconds


def _keys(uid, conversation_id, wal_content_id):
    record, segment = record_identity(uid, conversation_id)
    return record, segment, hashlib.sha256(f'gap-fill-wal-v1:{wal_content_id}'.encode()).hexdigest()


def _report(outcome: str, record: str, seconds: float) -> str:
    GAP_FILL_TOTAL.labels(outcome=outcome).inc()
    logger.info(
        'event=sync_record_gap_fill outcome=%s record=%s seconds_bucket=%s',
        outcome,
        record[:16],
        _seconds_bucket(seconds),
    )
    return outcome


async def run_gap_fill(*, uid, conversation_id, row, paths, wal_content_id, store) -> str | None:
    """Serving entry: gates on the database pool, audio work on the storage pool.

    Returns the outcome, or None while the switch is off. Never raises: the
    caller's 503 is the same whatever happens here.
    """
    if not gap_fill_enabled(uid):
        return None
    record, segment, wal = _keys(uid, conversation_id, wal_content_id)
    seconds = 0.0
    try:
        outcome = await run_blocking(
            db_executor, _gates, uid, conversation_id, row, record, segment, wal, store, time.time()
        )
        if outcome is None:
            outcome, seconds = await run_blocking(
                storage_executor, _write, uid, conversation_id, row, paths, record, wal, None, None, None
            )
    except Exception:
        outcome = 'failed'
    return _report(outcome, record, seconds)


def fill_closed_record_gap(
    *,
    uid: str,
    conversation_id: str,
    row: dict,
    paths: list[str],
    wal_content_id: str,
    store,
    now: float | None = None,
    storage_client=None,
    bucket=None,
    protection_level: str | None = None,
) -> str | None:
    """Synchronous composition of the same two phases, with injectable storage."""
    if not gap_fill_enabled(uid):
        return None
    record, segment, wal = _keys(uid, conversation_id, wal_content_id)
    seconds = 0.0
    try:
        outcome = _gates(uid, conversation_id, row, record, segment, wal, store, time.time() if now is None else now)
        if outcome is None:
            outcome, seconds = _write(
                uid, conversation_id, row, paths, record, wal, storage_client, bucket, protection_level
            )
    except Exception:
        outcome = 'failed'
    return _report(outcome, record, seconds)
