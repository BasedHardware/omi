"""Bind duplicate proof to the precise slices admitted by the native writer."""

from config.record_wal_duplicate import MAX_JOBS
from utils.other.raw_audio import WAL_FORMAT

MAX_SLICES = 128


def attest(bucket, uid, cid, row, barrier, units, items):
    if (
        row.get('record_audio_closed') is not True
        or row.get('record_audio_partial')
        or row.get('record_upload_failed')
        or row.get('record_wal_handoff_present')
        or not 0 < len(units) == len(items) <= MAX_JOBS
        or not 0 < sum(len(refs) for _, _, refs in units) <= MAX_SLICES
    ):
        return None
    prefix = f'raw-live/{uid}/{cid}/'
    slices = []
    for item, (_, _, refs) in zip(items, units):
        for ref in refs:
            path = ref['path']
            metadata = ref.get('metadata') or {}
            if (
                ref['bucket'] != bucket
                or not path.startswith(prefix)
                or len(path) > 512
                or metadata.get('format') != WAL_FORMAT
                or metadata.get('custody_schema') != 'audio_custody_v1'
                or metadata.get('clock_source') != 'server_projected'
                or metadata.get('source_layout') != 'mono'
                or str(metadata.get('sample_rate')) != '16000'
                or type(ref['generation']) is not int
                or ref['generation'] <= 0
            ):
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
