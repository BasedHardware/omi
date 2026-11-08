"""Sealed pending-snapshot settlement; never closes an unresolved producer."""

import time

from config import pipeline_attention as policy
from database import conversations, episodes
from utils.conversations import pipeline_attention
from utils.episodes import service


def settle(uid, conversation_id, row, deadline, *, now=None):
    if not pipeline_attention.notes_serving(uid) or policy.seal_snapshot(row) is None:
        return False
    now = time.time() if now is None else now
    episode = episodes.get_episode_for_conversation(uid, conversation_id)
    if not episode:
        return False  # A quiet conversation alone does not prove episode settlement.
    saved = policy.seconds(episode.get('pipeline_dispatch_at'))
    deadline = min(at for at in (saved, deadline) if at is not None) if saved or deadline else None
    if episode.get('pending_boundary'):
        return False  # Only the canonical F-join path may settle this decision.
    if episode.get('status') != 'live':
        return True
    if deadline and saved != deadline:
        try:
            episode = episodes.update_episode(
                uid,
                episode['id'],
                expected_version=int(episode['state_version']),
                updates={'pipeline_dispatch_at': deadline},
            )
        except episodes.EpisodeConflict:
            return False
    fast = pipeline_attention.serving(uid) and (
        pipeline_attention.attention(uid, now=now) == 'watched' or pipeline_attention.promoted(uid)
    )
    if not (deadline is not None and now >= deadline or fast and policy.close_on_seal_enabled()):
        return False
    ids = list(episode.get('conversation_ids') or [])
    if not ids or len(ids) > 64:
        return False
    members = [row if cid == conversation_id else conversations.get_conversation_raw_snapshot(uid, cid) for cid in ids]
    proofs = {}
    for cid, member in zip(ids, members):
        proof = policy.seal_snapshot(member) if member else None
        if proof is None:
            return False
        proofs[cid] = proof
    # The service re-reads membership and activity before its CAS. F-join and
    # provisional-item reconciliation stay on the canonical close path.
    return service.close_pipeline_snapshot(uid, episode, deadline, proofs, now=now) is not None
