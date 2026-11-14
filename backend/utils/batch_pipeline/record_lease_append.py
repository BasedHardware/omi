"""Retain an owner's late WAL holes for the existing partial continuation.

Unlike tail-only gap fill this uses actual retained sample coverage, so a
partial record and interior gaps are supported. Writes remain create-only.
"""

import math
from datetime import datetime

from database._client import run_transactional
from config.record_audio import record_identity
from config.record_partial import MAX_SOURCES
from config.record_gap_fill import MAX_FILL_SECONDS, PIECE_SECONDS, FINISH_SLACK_SECONDS
from database.batch_pipeline_record_lease_recovery import recovery_segment
from utils.batch_pipeline import record_gap_fill as gap
from utils.batch_pipeline.live import retained_record_units
from utils.batch_pipeline.record_partial import unit_coverage
from utils.batch_pipeline.record_partial_audio import missing_units
from utils.executors import db_executor, storage_executor, run_blocking
from utils.other.storage import list_audio_chunks
from utils import encryption
from utils.sync import record_token_lease as custody


def retention_window(row):
    """Only sealed/partial records have a server-clock interval to fill."""
    finish, start = row.get('finished_at'), row.get('started_at')
    if not (row.get('record_audio_closed') or row.get('record_audio_partial')):
        return None
    if (
        not isinstance(start, datetime)
        or not isinstance(finish, datetime)
        or start.tzinfo is None
        or finish.tzinfo is None
    ):
        return None
    try:
        first, last = start.timestamp(), finish.timestamp()
    except (ValueError, OverflowError, OSError):
        return None
    if not math.isfinite(first) or not math.isfinite(last) or first > last:
        return None
    return first - FINISH_SLACK_SECONDS, last + FINISH_SLACK_SECONDS


def retain(uid, cid, row, paths):
    window = retention_window(row)
    if window is None:
        return
    start, finish = window
    client = gap.create_storage_client()
    chunks = list_audio_chunks(uid, cid, max_count=MAX_SOURCES, require_archive=True)
    iterator = retained_record_units(uid, cid, chunks, client, encryption.derive_key(uid), partial=True)
    coverage = []
    try:
        for unit in iterator:
            coverage.extend(unit_coverage([unit]))
    finally:
        iterator.close()
    protection = row.get('data_protection_level') or gap.users_db.get_data_protection_level(uid)
    bucket = gap.gap_fill_bucket(uid, client)
    budget = MAX_FILL_SECONDS * gap.RATE
    for unit in gap.source_units(paths):
        pcm = gap.wav_pcm(unit.wav)
        first = max(0, math.ceil((start - unit.capture_at) * gap.RATE))
        last = min(len(pcm) // 2, math.floor((finish - unit.capture_at) * gap.RATE))
        if first >= last:
            continue
        refs = [{'start_frame': first, 'offset_frame': first, 'frames': last - first}]
        missing, updated_coverage = missing_units([(unit.capture_at, len(pcm) / (2 * gap.RATE), refs)], coverage)
        for timestamp, _, slices in missing:
            for ref in slices:
                count = ref['frames']
                if count > budget:
                    raise ValueError('late custody fill budget exceeded; retain WAL')
                offset = ref['offset_frame']
                for relative in range(0, count, PIECE_SECONDS * gap.RATE):
                    size = min(count - relative, PIECE_SECONDS * gap.RATE)
                    capture = timestamp + (ref['start_frame'] + relative) / gap.RATE
                    created = gap.create_gap_fill_chunk(
                        pcm[(offset + relative) * 2 : (offset + relative + size) * 2],
                        uid,
                        cid,
                        capture,
                        protection,
                        {'source': 'phone_wal', 'rendition': 'record-lease-append-v1'},
                        bucket=bucket,
                    )
                    if created is None:
                        raise ValueError('concurrent custody chunk exists; retain WAL for coverage proof')
                budget -= count
        coverage = updated_coverage


def wake_partial(store, uid, cid, now):
    """No revision bump on a refused request; force a new inventory comparison.

    Changing partial_run also fences an in-flight old-audio CAS. Stored chunks
    remain discoverable even when the HTTP route conservatively keeps the WAL.
    """
    from google.cloud import firestore

    _, original = record_identity(uid, cid)

    @firestore.transactional
    def commit(tx):
        refs = [
            store.client.collection(store.namespace + '_jobs').document(key)
            for key in (original, recovery_segment(uid, cid))
        ]
        jobs = [(ref, ref.get(transaction=tx).to_dict() or {}) for ref in refs]
        for ref, job in jobs:
            if job.get('partial_coordinator') and job.get('state') in {'record_pending', 'partial_retired'}:
                patch = {'state': 'record_pending', 'available_at': now}
                if job.get('partial_run'):
                    run = dict(job['partial_run'])
                    run.pop('retired_at', None)
                    run.update(next_inventory_at=now, inventory_changed_at=now, complete=True, fingerprint='')
                    patch['partial_run'] = run
                tx.update(ref, patch)

    run_transactional(store.client, commit, transient=True)


async def retain_upload(uid, cid, row, paths, store):
    if not custody.owns_upload(uid, cid) or retention_window(row) is None:
        return
    try:
        await run_blocking(storage_executor, retain, uid, cid, row, paths)
    finally:
        # A later object can fail after earlier create-only writes succeeded.
        # Re-arm those durable chunks even while the phone retains its WAL.
        await run_blocking(db_executor, wake_partial, store, uid, cid, gap.time.time())
