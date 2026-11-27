"""Bind duplicate proof to the precise slices admitted by the native writer."""

from prometheus_client import Counter

from config.record_wal_duplicate import MAX_JOBS
from utils.other.raw_audio import WAL_FORMAT

MAX_SLICES = 128
# Fixed vocabulary, first failing check wins. No ids, paths or values.
REFUSAL_REASONS = (
    'not_closed',
    'partial',
    'upload_failed',
    'handoff_present',
    'unit_count',
    'slice_count',
    'bucket',
    'path',
    'format',
    'clock_source',
    'geometry',
    'generation',
)
# The record_wal_handoff_ prefix keeps the series inside the sync scrape
# profile's existing keep rule (backend/deploy/cloud_run_gmp_sync.yaml).
refusals = Counter(
    'omi_record_wal_handoff_source_attest_refusals_total',
    'Native intakes admitted without a duplicate-proof source attestation',
    ['reason'],
)
for _reason in REFUSAL_REASONS:
    refusals.labels(_reason)


def _row_refusal(row, units, items):
    if row.get('record_audio_closed') is not True:
        return 'not_closed'
    if row.get('record_audio_partial'):
        return 'partial'
    if row.get('record_upload_failed'):
        return 'upload_failed'
    if row.get('record_wal_handoff_present'):
        return 'handoff_present'
    if not 0 < len(units) == len(items) <= MAX_JOBS:
        return 'unit_count'
    if not 0 < sum(len(refs) for _, _, refs in units) <= MAX_SLICES:
        return 'slice_count'
    return None


def _ref_refusal(ref, path, bucket, prefix):
    metadata = ref.get('metadata') or {}
    if ref['bucket'] != bucket:
        return 'bucket'
    if not path.startswith(prefix) or len(path) > 512:
        return 'path'
    if metadata.get('format') != WAL_FORMAT or metadata.get('custody_schema') != 'audio_custody_v1':
        return 'format'
    if metadata.get('clock_source') != 'server_projected':
        return 'clock_source'
    if metadata.get('source_layout') != 'mono' or str(metadata.get('sample_rate')) != '16000':
        return 'geometry'
    if type(ref['generation']) is not int or ref['generation'] <= 0:
        return 'generation'
    return None


def attest(bucket, uid, cid, row, barrier, units, items):
    reason = _row_refusal(row, units, items)
    if reason is not None:
        refusals.labels(reason).inc()
        return None
    prefix = f'raw-live/{uid}/{cid}/'
    slices = []
    for item, (_, _, refs) in zip(items, units):
        for ref in refs:
            path = ref['path']
            reason = _ref_refusal(ref, path, bucket, prefix)
            if reason is not None:
                refusals.labels(reason).inc()
                return None
            slices.append(
                {
                    'unit': item.segment_id,
                    'path': path,
                    'generation': ref['generation'],
                    'first': ref['offset_frame'],
                    'count': ref['frames'],
                }
            )
    return {
        'bucket': bucket,
        'revision': barrier['record_upload_revision'],
        'units': [item.segment_id for item in items],
        'slices': slices,
    }
