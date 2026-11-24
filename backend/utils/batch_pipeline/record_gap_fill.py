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
- The fill holds the record_pending job's drain lease while it writes, so
  drain admission cannot list retained audio mid-fill; a post-write recheck
  under the same lease reports ``raced`` if admission moved the job anyway.
- Logs and metrics carry only hashed keys and closed vocabularies.
"""

import asyncio
import hashlib
import io
import logging
import math
import time
import wave
from datetime import datetime

from google.api_core.exceptions import PreconditionFailed
from google.cloud.storage.retry import DEFAULT_RETRY
from prometheus_client import Counter

from config import audio_archive

from config.record_audio import record_identity, require_record_audio_barrier
from config.record_gap_fill import (
    CLOSED_MIN_SECONDS,
    FILL_LEASE_SECONDS,
    FINISH_SLACK_SECONDS,
    LEASE_MARGIN_SECONDS,
    MARKER_SECONDS,
    MAX_FILL_SECONDS,
    PIECE_SECONDS,
    gap_fill_enabled,
    retained_ack_enabled,
)
from database import users as users_db
from database.conversations import document_data_with_revision
from database.audio_timeline import span_blob_metadata
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.sync_record_wait_cache import claim_gap_fill_marker
from utils import encryption
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline import record_retained_ack
from utils.batch_pipeline.live import retained_record_units
from utils.observability.reasons import ReasonFamily, RecordGapFillOutcome, reason_label
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
        'skipped_busy',
        'raced',
        'failed',
    }
)
# Fill outcomes after which every gate passed, the lease settled cleanly and
# every create this request made succeeded; only these may be acked.
ACKABLE = frozenset({'written', 'skipped_no_gap', 'skipped_no_audio', 'skipped_marker'})
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


class LeaseLapsing(Exception):
    """The write deadline passed before a piece could start uploading."""


def create_gap_fill_chunk(
    pcm: bytes,
    uid: str,
    conversation_id: str,
    timestamp: float,
    protection_level: str,
    metadata: dict,
    *,
    bucket,
    deadline: float | None = None,
) -> str | None:
    """Create-only write of one gap-fill PCM16 object; None if the key exists.

    Unlike ``upload_audio_chunk`` there is no overwrite fallback: an existing
    object at the key always wins and this write is skipped. Raises
    ``LeaseLapsing`` if the write deadline passed while waiting on the gate.
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
        # The gate's own authority reads have no deadline: re-check right
        # before the upload, whose time is then bounded inside the margin.
        if deadline is not None and time.monotonic() >= deadline:
            raise LeaseLapsing()
        try:
            # Bounded so a piece started before the write deadline lands before
            # the drain lease lapses: per request and across retries. Every
            # write is create-only (generation 0), so a retry is always safe.
            blob.upload_from_string(
                payload,
                content_type='application/octet-stream',
                if_generation_match=0,
                timeout=LEASE_MARGIN_SECONDS / 3,
                retry=DEFAULT_RETRY.with_timeout(LEASE_MARGIN_SECONDS / 2),
            )
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


def wav_pcm(wav: bytes) -> bytes:
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


def source_units(paths):
    """Decode each WAL file on its own, in capture order.

    ``decode_units`` joins files up to 30 s apart with zero PCM. Here that
    silence would hide a real hole from the contiguity check, so the fill
    sees every source-file gap.
    """
    for path in sorted(paths, key=lambda value: (get_timestamp_from_path(value), value)):
        yield from decode_units([path])


def _decoded(paths):
    return list(source_units(paths))


def _write_window(
    uid, conversation_id, source, lower, upper, anchor, tolerance, protection_level, metadata, bucket, deadline=None
):
    """Write WAL PCM inside [lower, upper) create-only, contiguous from ``anchor``.

    Returns (written, collisions, seconds, gapped); a create collision ends
    the write. Admission checks only the
    final end, so a fill that skipped ahead would let a record admit with a
    hole the drain could never fill again. Writing stops at the first WAL
    sample more than ``tolerance`` after the audio already held (the retained
    end or the previous written piece); a later upload continues from there.
    """
    written = collisions = 0
    budget = MAX_FILL_SECONDS * RATE
    expected = anchor
    gapped = False
    for unit in source:
        if budget <= 0:
            break
        pcm = wav_pcm(unit.wav)
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
            if deadline is not None and time.monotonic() >= deadline:
                # The drain lease is about to lapse: stop on a piece boundary
                # (still contiguous); a later upload continues from here.
                return written, collisions, (MAX_FILL_SECONDS * RATE - budget) / RATE, gapped
            count = min(last - cursor, PIECE_SECONDS * RATE)
            timestamp = round(unit.capture_at + cursor / RATE, 6)
            try:
                path = create_gap_fill_chunk(
                    pcm[cursor * 2 : (cursor + count) * 2],
                    uid,
                    conversation_id,
                    timestamp,
                    protection_level,
                    metadata,
                    bucket=bucket,
                    deadline=deadline,
                )
            except LeaseLapsing:
                return written, collisions, (MAX_FILL_SECONDS * RATE - budget) / RATE, gapped
            if path is None:
                # The key's owner proves only that the key exists, not that it
                # covers this span. Advancing past it could write a later tail
                # over a hole, so stop; a later upload continues from the new
                # retained end.
                collisions += 1
                return written, collisions, (MAX_FILL_SECONDS * RATE - budget) / RATE, gapped
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

    Returns (refusal, lease): refusal None proceeds to the storage phase, and
    a non-None lease must be settled by the caller whatever happens next.
    """
    try:
        require_record_audio_barrier(row)
    except ValueError:
        return 'skipped_gate', None
    if (
        row.get('record_audio_partial')
        or row.get('deleted')
        or row.get('discarded')
        or not row.get('private_cloud_sync_enabled')
    ):
        return 'skipped_gate', None
    finish = _epoch(row.get('finished_at'))
    if finish is None:
        return 'skipped_gate', None
    # Settled: the capture finished, and no row write (close, upload session
    # release, finalization) happened, at least CLOSED_MIN_SECONDS ago.
    settled = max(finish, _epoch(row.get('updated_at')) or finish)
    if now - settled < CLOSED_MIN_SECONDS:
        return 'skipped_recent', None

    def claim(tx):
        # Privacy first: nothing of this record is read past a block.
        tx.check_privacy(uid, (conversation_id,))
        pending = tx.get('jobs', segment)
        # Only a registered record_pending obligation is drained into admission.
        # A record that canonical registration refused (for example server-batch
        # only with no server audio) or never registered gains nothing from audio.
        if (
            (pending or {}).get('state') != 'record_pending'
            or pending.get('record_content_id') != record
            or pending.get('owner_id') != uid
            or pending.get('conversation_id') != conversation_id
        ):
            return 'skipped_no_pending', None
        # A live lease is a drain admission (or another fill) in flight.
        if pending.get('available_at', 0) > now:
            return 'skipped_busy', None
        # Take the drain's own lease: ``due`` and ``claim`` skip the row until
        # it lapses or is released, so no admission lists retained audio mid-fill.
        lease = now + FILL_LEASE_SECONDS
        tx.put('jobs', segment, {**pending, 'available_at': lease})
        return None, lease

    try:
        outcome, lease = store.run(claim)
    except BatchPrivacyBlocked:
        return 'skipped_gate', None
    if outcome is not None:
        return outcome, None
    if not claim_gap_fill_marker(record, wal, MARKER_SECONDS):
        return 'skipped_marker', lease
    return None, lease


def _settle(uid, conversation_id, segment, store, lease) -> bool:
    """Post-write recheck and lease release in one transaction.

    True only if privacy still allows the record and the job is still
    record_pending under this fill's lease, so no admission ran mid-fill. The
    lease is then released (the row is due at once); otherwise it is left to
    whoever moved it.
    """

    def settle(tx):
        tx.check_privacy(uid, (conversation_id,))
        latest = tx.get('jobs', segment)
        if (latest or {}).get('state') != 'record_pending' or latest.get('available_at') != lease:
            return False
        # Back to the claim's own clock: due at once, never later than before.
        tx.put('jobs', segment, {**latest, 'available_at': lease - FILL_LEASE_SECONDS})
        return True

    try:
        return bool(store.run(settle))
    except BatchPrivacyBlocked:
        return False


def _write(
    uid, conversation_id, row, paths, record, wal, storage_client, bucket, protection_level, deadline=None, units=None
):
    """Storage phase: admission's retained walk, then the clipped create-only write.

    ``units`` is the upload already decoded for option A; otherwise the WAL
    files are decoded lazily (decoding consumes them).
    """
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
        source_units(paths) if units is None else units,
        lower,
        finish + FINISH_SLACK_SECONDS,
        anchor,
        tolerance,
        protection_level,
        metadata,
        bucket,
        deadline,
    )
    if collisions:
        # Any create collision ends the fill (pieces before it stay written):
        # never 'written', so never acked.
        return 'skipped_collision', seconds
    if written:
        return 'written', seconds
    return ('skipped_not_contiguous' if gapped else 'skipped_no_audio'), seconds


def _keys(uid, conversation_id, wal_content_id):
    record, segment = record_identity(uid, conversation_id)
    return record, segment, hashlib.sha256(f'gap-fill-wal-v1:{wal_content_id}'.encode()).hexdigest()


def _report(outcome: str, record: str, seconds: float) -> str:
    GAP_FILL_TOTAL.labels(outcome=reason_label(ReasonFamily.RECORD_GAP_FILL, outcome, RecordGapFillOutcome)).inc()
    logger.info(
        'event=sync_record_gap_fill outcome=%s record=%s seconds_bucket=%s',
        outcome,
        record[:16],
        _seconds_bucket(seconds),
    )
    return outcome


def _fresh_row(store, uid, conversation_id):
    """The whole conversation row with its Firestore revision as ``updated_at``.

    The caller's row may be a field-masked provenance read or a raw
    ``to_dict()`` without the revision; the gates need neither gap.
    """
    ref = store.client.collection('users').document(uid).collection('conversations').document(conversation_id)
    return document_data_with_revision(ref.get())


def _ack(uid, conversation_id, row, paths, units, record, store, storage_client) -> bool:
    """Option A proof after a clean fill; privacy is re-checked after the read."""
    outcome = 'failed'
    try:
        client = storage_client if storage_client is not None else create_storage_client()
        outcome = record_retained_ack.prove(
            uid,
            conversation_id,
            _decoded(paths) if units is None else units,
            client,
            finish=_epoch(row.get('finished_at')),
            started=_epoch(row.get('started_at')),
        )
        if outcome == 'acked':
            store.run(lambda tx: tx.check_privacy(uid, (conversation_id,)))
    except BatchPrivacyBlocked:
        outcome = 'skipped_privacy'
    except Exception:
        outcome = 'failed'
    return record_retained_ack.report(outcome, record) == 'acked'


async def run_gap_fill(*, uid, conversation_id, paths, wal_content_id, store) -> tuple[str | None, bool]:
    """Serving entry: gates on the database pool, audio work on the storage pool.

    Returns (fill outcome, acked); (None, False) while the switch is off.
    Never raises. ``acked`` is True only when option A proved a byte-exact
    durable copy of every WAL sample after a clean fill; the caller then
    answers the covered 200, otherwise the same 503 as before.
    """
    if not gap_fill_enabled(uid):
        return None, False
    record, segment, wal = _keys(uid, conversation_id, wal_content_id)
    seconds, lease, row, units = 0.0, None, None, None
    ack = retained_ack_enabled(uid)
    outcome: str | None = 'failed'
    # The lease is taken inside the gates; measure the write deadline from
    # before them so slow Firestore calls only shorten the write window.
    deadline = time.monotonic() + FILL_LEASE_SECONDS - LEASE_MARGIN_SECONDS
    try:
        row = await run_blocking(db_executor, _fresh_row, store, uid, conversation_id)
        outcome = 'skipped_gate' if not row else None
        if outcome is None:
            outcome, lease = await run_blocking(
                db_executor, _gates, uid, conversation_id, row, record, segment, wal, store, time.time()
            )
        if outcome is None:
            if ack:
                # The proof needs every WAL sample, and decoding consumes the files.
                units = await run_blocking(storage_executor, _decoded, paths)
            outcome, seconds = await run_blocking(
                storage_executor,
                _write,
                uid,
                conversation_id,
                row,
                paths,
                record,
                wal,
                None,
                None,
                None,
                deadline,
                units,
            )
    except asyncio.CancelledError:
        # Cancelling the await cannot stop a storage thread still writing, so
        # never release the lease under it: it lapses on its own, after the
        # write deadline. The drain then admits on its normal pass.
        lease = None
        raise
    except Exception:
        outcome = 'failed'
    finally:
        if lease is not None:
            try:
                settled = await run_blocking(db_executor, _settle, uid, conversation_id, segment, store, lease)
            except Exception:
                settled = False
            if not settled and outcome != 'failed':
                outcome = 'raced'
    outcome = outcome or 'failed'
    _report(outcome, record, seconds)
    acked = False
    if outcome in ACKABLE and ack:
        acked = await run_blocking(storage_executor, _ack, uid, conversation_id, row, paths, units, record, store, None)
    return outcome, acked


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
    on_written=None,
) -> str | None:
    """Synchronous composition of the same phases, with injectable storage.

    Returns the fill outcome; with option A on, 'acked' replaces an ackable
    outcome whose proof passed. ``on_written`` (tests) runs after the write
    and before the post-write recheck.
    """
    if not gap_fill_enabled(uid):
        return None
    record, segment, wal = _keys(uid, conversation_id, wal_content_id)
    seconds, lease, units = 0.0, None, None
    ack = retained_ack_enabled(uid)
    outcome: str | None = 'failed'
    deadline = time.monotonic() + FILL_LEASE_SECONDS - LEASE_MARGIN_SECONDS
    try:
        outcome, lease = _gates(
            uid, conversation_id, row, record, segment, wal, store, time.time() if now is None else now
        )
        if outcome is None:
            units = _decoded(paths) if ack else None
            outcome, seconds = _write(
                uid, conversation_id, row, paths, record, wal, storage_client, bucket, protection_level, deadline, units
            )
            if on_written is not None:
                on_written()
    except Exception:
        outcome = 'failed'
    finally:
        if lease is not None:
            try:
                settled = _settle(uid, conversation_id, segment, store, lease)
            except Exception:
                settled = False
            if not settled and outcome != 'failed':
                outcome = 'raced'
    outcome = outcome or 'failed'
    _report(outcome, record, seconds)
    if outcome in ACKABLE and ack:
        if _ack(uid, conversation_id, row, paths, units, record, store, storage_client):
            return 'acked'
    return outcome
