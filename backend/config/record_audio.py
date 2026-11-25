"""Pure upload-barrier snapshot shared by staging and transactional admission."""

from config import record_partial
import hashlib
import os

BARRIER_NOT_CLOSED = 'capture upload/finalization barrier not closed'

PRODUCER_START_MARGIN_SECONDS = 2.0  # Integer boot seconds plus one user clock tick.


def record_identity(uid: str, conversation_id: str) -> tuple[str, str]:
    content = hashlib.sha256(f'record-v1:{uid}:{conversation_id}'.encode()).hexdigest()
    return content, hashlib.sha256(f'{content}:0'.encode()).hexdigest()


def restore_pending(row: dict, *obligations: dict) -> bool:
    """Registration precedes restore metadata; only that origin fences revival."""
    return bool(row.get('discarded') and any(job.get('registration_origin') == 'restore' for job in obligations))


def barrier_cause_metrics_enabled() -> bool:
    """RECORD_BARRIER_CAUSE_METRICS kill switch: the cause counters only, never admission."""
    return os.getenv('RECORD_BARRIER_CAUSE_METRICS', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


BARRIER_BLOCKERS = (
    'owner_other',
    'status_not_completed',
    'producer_tokens',
    'upload_failed',
    'partial_invalid',
    'audio_not_closed',
)
TOKEN_KINDS = ('none', 'bare', 'podless', 'abandoned', 'pod', 'other')


def _token_kind(sessions) -> str:
    """The least releasable producer token, from the map's shape only."""
    if not isinstance(sessions, dict) or not sessions:
        return 'other' if sessions else 'none'
    kinds = set()
    for value in sessions.values():
        if value is True:
            kinds.add('bare')
        elif not isinstance(value, dict):
            kinds.add('other')
        elif 'abandoned_at' in value:
            kinds.add('abandoned')
        elif value.get('pod') == '':
            kinds.add('podless')
        else:
            kinds.add('pod')
    for kind in ('other', 'bare', 'podless', 'pod', 'abandoned'):
        if kind in kinds:
            return kind
    return 'none'


def barrier_blocker(row) -> tuple[str, str]:
    """Closed-vocabulary first failing clause of the barrier, plus the token kind.

    Content-free: reads only fields the predicate already reads. Used for
    counts; never changes the barrier decision.
    """
    kind = _token_kind(row.get('record_upload_sessions'))
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
        return 'owner_other', kind
    if row.get('status') != 'completed':
        return 'status_not_completed', kind
    if row.get('record_upload_sessions'):
        return 'producer_tokens', kind
    if row.get('record_upload_failed'):
        return 'upload_failed', kind
    if row.get('record_audio_partial'):
        return 'partial_invalid', kind
    return 'audio_not_closed', kind


def require_record_audio_barrier(row, *, expected=None):
    snapshot = {
        key: row.get(key)
        for key in (
            'record_lane_owner',
            'status',
            'finished_at',
            'record_upload_revision',
            'record_audio_partial',
        )
    }
    if (
        row.get('status') != 'completed'
        or not (
            row.get('record_audio_closed')
            and not row.get('record_audio_partial')
            and not row.get('record_upload_failed')
            or record_partial.enabled()
            and record_partial.partial_barrier(row)
        )
        or row.get('record_upload_sessions')
        or row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}
    ):
        error = ValueError(BARRIER_NOT_CLOSED)
        # Same type and message as before; the cause rides as attributes so
        # callers that compare str(error) or log type names are unchanged.
        try:
            blocker, kind = barrier_blocker(row)
            setattr(error, 'barrier_blocker', blocker)
            setattr(error, 'barrier_token_kind', kind)
        except Exception:
            # Malformed rows (e.g. an unhashable owner) must keep the exact
            # refusal; counters report missing attributes as ``unknown``.
            pass
        raise error
    if expected is not None and snapshot != expected:
        raise ValueError('capture upload barrier changed during staging')
    return snapshot
