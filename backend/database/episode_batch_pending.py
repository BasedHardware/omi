"""Stamp a batch member's deadline in the membership transaction, once only."""

from datetime import timedelta

from config.batch_timeliness import SLA_SECONDS


def read_patch(transaction, client, uid, cid, pending_at):
    if pending_at is None:
        return {}
    ref = client.collection('users').document(uid).collection('conversations').document(cid)
    snapshot = ref.get(transaction=transaction)
    row = snapshot.to_dict() or {}
    if not snapshot.exists or row.get('episode_transcription_deadline_at'):
        return {}
    return {
        'episode_transcription_pending_at': pending_at,
        'episode_transcription_deadline_at': pending_at + timedelta(seconds=SLA_SECONDS),
    }
