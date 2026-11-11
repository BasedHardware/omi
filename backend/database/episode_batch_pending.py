"""Stamp a batch member's deadline in the membership transaction, once only."""

from datetime import datetime, timedelta, timezone

from config.batch_timeliness import SLA_SECONDS


def matches_closed_audio(row, start, end):
    """Compare the same microsecond-normalized archive clock used at admission."""
    if (
        not row
        or row.get('server_batch_audio_closed') is not True
        or any(type(row.get(key)) not in (int, float) for key in ('server_batch_audio_start', 'server_batch_audio_end'))
    ):
        return False
    try:
        return (
            datetime.fromtimestamp(row['server_batch_audio_start'], timezone.utc) == start
            and datetime.fromtimestamp(row['server_batch_audio_end'], timezone.utc) == end
        )
    except (OverflowError, OSError, ValueError):
        return False


def read_patch(transaction, client, uid, cid, pending_at, deadline_floor=None):
    if pending_at is None:
        return {}
    ref = client.collection('users').document(uid).collection('conversations').document(cid)
    snapshot = ref.get(transaction=transaction)
    row = snapshot.to_dict() or {}
    if not snapshot.exists or row.get('episode_transcription_deadline_at'):
        return {}
    deadline = pending_at + timedelta(seconds=SLA_SECONDS)
    # Admission starts the clock before the capture ends. A capture may run for
    # MAX_EPISODE_SECONDS, so the delivery SLA must not expire while it records.
    if deadline_floor is not None and deadline_floor > deadline:
        deadline = deadline_floor
    return {
        'episode_transcription_pending_at': pending_at,
        'episode_transcription_deadline_at': deadline,
    }
