"""Exact original WAL custody before any decoder or negative coverage memo."""

import hashlib
import math
from pathlib import Path

from config.batch_pipeline_record_wal_handoff import handoff_enabled
from database import record_wal_handoff as receipts
from database.record_wal_capacity import CapacityExceeded
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.other.raw_audio import filename_provenance, wal_packets
from utils.other.audio_opus import opus_packet_samples
from utils.other.storage import archive_record_wal_bytes, delete_record_wal_original
from utils.batch_pipeline import record_wal_metrics as metrics

MAX_FILES = 20
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_BYTES = 160 * 1024 * 1024
MAX_FRAMES = 200000


def inspect_files(paths):
    if not 0 < len(paths) <= MAX_FILES:
        raise ValueError('bounded nonempty WAL bundle required')
    files = []
    total = 0
    for path in paths:
        name = Path(path).name
        if len(name.encode()) > 255 or name in {'.', '..'}:
            raise ValueError('invalid WAL name')
        size = Path(path).stat().st_size
        total += size
        if not 0 < size <= MAX_FILE_BYTES or total > MAX_BUNDLE_BYTES:
            raise ValueError('WAL byte budget exceeded')
        raw = Path(path).read_bytes()
        info = filename_provenance(path)
        codec, rate, channels = info.get('codec'), info.get('sample_rate'), info.get('channels')
        if (
            codec not in {'opus', 'pcm16', 'pcm8'}
            or rate not in {8000, 12000, 16000, 24000, 48000}
            or channels != 1
            or info.get('frame_size') not in {80, 160, 320, 480, 640, 960}
            or not math.isfinite(info.get('capture_start', float('nan')))
            or info['capture_start'] <= 0
        ):
            raise ValueError('unsupported WAL header')
        frames = 0
        samples = 0
        for packet in wal_packets(raw):
            frames += 1
            if frames > MAX_FRAMES:
                raise ValueError('WAL frame budget exceeded')
            if codec == 'opus':
                count = opus_packet_samples(packet, rate)
                if not 0 < count <= rate * 120 // 1000 or count != info['frame_size']:
                    raise ValueError('invalid Opus packet header')
            else:
                width = 2 if codec == 'pcm16' else 1
                if len(packet) % width or len(packet) > info['frame_size'] * width:
                    raise ValueError('invalid PCM frame')
                count = len(packet) // width
            samples += count
        if not frames or len(raw) != size:
            raise ValueError('empty or changed WAL')
        files.append(
            {
                'name': name,
                'sha256': hashlib.sha256(raw).hexdigest(),
                'size': size,
                'codec': codec,
                'sample_rate': rate,
                'channels': channels,
                'frame_size': info['frame_size'],
                'capture_start': info['capture_start'],
                'frame_count': frames,
                'sample_count': samples,
            }
        )
    if len({entry['name'] for entry in files}) != len(files):
        raise ValueError('duplicate WAL names')
    return sorted(files, key=lambda entry: entry['name'])


def retain_original(uid, cid, entry, path, protection, client, namespace, fence):
    raw = Path(path).read_bytes()
    if len(raw) != entry['size'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('WAL changed after inspection')
    receipt = archive_record_wal_bytes(uid, cid, raw, entry, protection)
    try:
        # This check runs in the storage leaf even if the awaiting request is
        # cancelled. A privacy purge racing a late object write cannot miss it.
        receipts.check_fence(client, namespace, fence)
    except BatchPrivacyBlocked:
        delete_record_wal_original(uid, receipt)
        raise
    return receipt


async def handoff(*, store, uid, cid, paths, source, device):
    # Even rollback must discover accepted receipts. Identity is server-derived
    # from every basename and original byte, never a caller-supplied content id.
    files = await run_blocking(sync_executor, inspect_files, paths)
    job_id = await run_blocking(sync_executor, receipts.bundle_id, uid, cid, files)
    old = await run_blocking(db_executor, receipts.read_status, store.client, store.namespace, uid, job_id)
    if old is not None:
        metrics.answers.labels('replayed').inc()
        return old
    if not handoff_enabled():
        return None
    try:
        fence = await run_blocking(
            db_executor, receipts.begin, store.client, store.namespace, uid, cid, files, source, device
        )
    except CapacityExceeded as error:
        metrics.capacity_refusals.labels(error.scope).inc()
        raise
    if fence['state'] == 'accepted':
        metrics.answers.labels('replayed').inc()
        return await run_blocking(db_executor, receipts.status, fence)
    by_name = {Path(path).name: path for path in paths}
    stored = []
    try:
        for entry in fence['files']:
            await run_blocking(db_executor, receipts.check_fence, store.client, store.namespace, fence)
            stored.append(
                entry.get('receipt')
                or await run_blocking(
                    storage_executor,
                    retain_original,
                    uid,
                    cid,
                    entry,
                    by_name[entry['name']],
                    fence['data_protection_level'],
                    store.client,
                    store.namespace,
                    fence,
                )
            )
        accepted = await run_blocking(db_executor, receipts.commit, store.client, store.namespace, fence, stored)
    except BatchPrivacyBlocked:
        for receipt in stored:
            await run_blocking(storage_executor, delete_record_wal_original, uid, receipt)
        raise
    metrics.answers.labels('accepted').inc()
    return await run_blocking(db_executor, receipts.status, accepted)
