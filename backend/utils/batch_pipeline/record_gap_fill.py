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
from utils.other.local_storage import create_storage_client
from utils.other.storage import list_audio_chunks, owner_storage_write_gate, private_cloud_sync_bucket

logger = logging.getLogger(__name__)

RATE = 16000
RENDITION = 'gap-fill-v1'
OUTCOMES = frozenset(
    {
        'written',
        'skipped_gate',
        'skipped_recent',
        'skipped_marker',
        'skipped_retained',
        'skipped_no_gap',
        'skipped_no_audio',
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


def _write_window(uid, conversation_id, paths, lower, upper, protection_level, metadata, bucket):
    """Write WAL PCM inside [lower, upper) create-only; returns (written, collisions, seconds)."""
    written = collisions = 0
    budget = MAX_FILL_SECONDS * RATE
    for unit in decode_units(paths):
        if budget <= 0:
            break
        pcm = _pcm(unit.wav)
        frames = len(pcm) // 2
        # ``first`` is the first WAL sample at or after the retained end, so a
        # fill object never starts before it under any sample rounding.
        first = 0 if lower is None else max(0, math.ceil((lower - unit.capture_at) * RATE - 1e-6))
        last = min(frames, math.floor((upper - unit.capture_at) * RATE + 1e-6), first + budget)
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
        del pcm
    return written, collisions, (MAX_FILL_SECONDS * RATE - budget) / RATE


def _fill(uid, conversation_id, row, paths, record, wal, store, now, storage_client, bucket, protection_level):
    try:
        require_record_audio_barrier(row)
    except ValueError:
        return 'skipped_gate', 0.0
    if (
        row.get('record_audio_partial')
        or row.get('deleted')
        or row.get('discarded')
        or not row.get('private_cloud_sync_enabled')
    ):
        return 'skipped_gate', 0.0
    finish = _epoch(row.get('finished_at'))
    if finish is None:
        return 'skipped_gate', 0.0
    # Settled: the capture finished, and no row write (close, upload session
    # release, finalization) happened, at least CLOSED_MIN_SECONDS ago.
    settled = max(finish, _epoch(row.get('updated_at')) or finish)
    if now - settled < CLOSED_MIN_SECONDS:
        return 'skipped_recent', 0.0
    if not claim_gap_fill_marker(record, wal, MARKER_SECONDS):
        return 'skipped_marker', 0.0
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
    started = _epoch(row.get('started_at'))
    lower = end if end is not None else (started - FINISH_SLACK_SECONDS if started is not None else None)
    try:
        store.run(lambda tx: tx.check_privacy(uid, (conversation_id,)))
    except BatchPrivacyBlocked:
        return 'skipped_gate', 0.0
    if protection_level is None:
        protection_level = users_db.get_data_protection_level(uid)
    metadata = {'source': 'phone_wal', 'rendition': RENDITION, 'record': record[:16], 'wal': wal[:16]}
    if bucket is None:
        bucket = gap_fill_bucket(uid, client)
    written, collisions, seconds = _write_window(
        uid, conversation_id, paths, lower, finish + FINISH_SLACK_SECONDS, protection_level, metadata, bucket
    )
    if written:
        return 'written', seconds
    return ('skipped_collision' if collisions else 'skipped_no_audio'), seconds


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
    """One gap-fill attempt; returns its outcome, or None while the switch is off.

    Never raises: the caller's 503 is the same whatever happens here.
    """
    if not gap_fill_enabled(uid):
        return None
    record = record_identity(uid, conversation_id)[0]
    wal = hashlib.sha256(f'gap-fill-wal-v1:{wal_content_id}'.encode()).hexdigest()
    seconds = 0.0
    try:
        outcome, seconds = _fill(
            uid,
            conversation_id,
            row,
            paths,
            record,
            wal,
            store,
            time.time() if now is None else now,
            storage_client,
            bucket,
            protection_level,
        )
    except Exception:
        outcome = 'failed'
    GAP_FILL_TOTAL.labels(outcome=outcome).inc()
    logger.info(
        'event=sync_record_gap_fill outcome=%s record=%s seconds_bucket=%s',
        outcome,
        record[:16],
        _seconds_bucket(seconds),
    )
    return outcome
