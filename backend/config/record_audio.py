"""Pure upload-barrier snapshot shared by staging and transactional admission."""

PRODUCER_START_MARGIN_SECONDS = 2.0  # Integer boot seconds plus one user clock tick.


def require_record_audio_barrier(row, *, expected=None):
    snapshot = {
        key: row.get(key)
        for key in (
            'record_lane_owner',
            'status',
            'finished_at',
            'record_upload_revision',
        )
    }
    if (
        row.get('status') != 'completed'
        or not row.get('record_audio_closed')
        or row.get('record_upload_failed')
        or row.get('record_upload_sessions')
        or row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}
    ):
        raise ValueError('capture upload/finalization barrier not closed')
    if expected is not None and snapshot != expected:
        raise ValueError('capture upload barrier changed during staging')
    return snapshot
