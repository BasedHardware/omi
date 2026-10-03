"""Receipt authority and reversible owner contributions; no storage or embedding clients."""

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from utils.speaker_learning_policy import winning_receipt_decision
from utils.stt.speaker_match import mean_embedding
import numpy as np


def pool_owner_vectors(vectors: Sequence[Sequence[float]]) -> list[float]:
    return mean_embedding([np.asarray(v, dtype=np.float32).reshape(1, -1) for v in vectors]).flatten().tolist()


def authorized_owner_segments(
    conversation: Mapping[str, Any], segment_ids: Sequence[str], *, card_generation: Optional[int] = None
) -> list[str]:
    """A card grants teaching only to its exact decision, never a later opt-out."""
    receipt = conversation.get('manual_speaker_assignments') or {}
    wanted = set(segment_ids)
    allowed = []
    for segment in conversation.get('transcript_segments') or []:
        if segment.get('id') not in wanted or not segment.get('is_user') or segment.get('person_id'):
            continue
        decision = winning_receipt_decision(receipt, segment)
        if not decision or not decision.get('is_user') or decision.get('person_id') or decision.get('rejection'):
            continue
        card_authorized = card_generation is not None and decision.get('generation') == card_generation
        if decision.get('use_for_speech_training', True) is not False or card_authorized:
            allowed.append(segment['id'])
    return allowed


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            # One malformed legacy timestamp must not abort pooling or
            # retraction; treat it as absent, like database.voice_profiles.as_utc.
            return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)) if isinstance(value, datetime) else None


def owner_base(data: Mapping[str, Any]) -> Any:
    """A fresh explicit enrollment supersedes the saved base, not vice versa."""
    pooled = _as_utc(data.get('owner_voice_pooled_at'))
    updated = _as_utc(data.get('speaker_embedding_updated_at'))
    if data.get('speaker_embedding') and (pooled is None or (updated is not None and updated > pooled)):
        return data['speaker_embedding']
    return data.get('speaker_embedding_base')


def retract_owner_contributions(
    data: Mapping[str, Any], conversation_ids: Sequence[str], segment_ids: Sequence[str], now: datetime
) -> dict[str, Any]:
    """Retire intersecting contributions atomically with every explicit edit.

    Legacy confirmations have conversation provenance only: conservatively retire
    the source conversation on correction — including a merged-away donor when the
    edit landed on its redirect target. Other conversations and the explicit
    enrollment base survive. No migration or provider inference is required.
    """
    ids = set(conversation_ids)
    confirmations = list(data.get('owner_voice_confirmations') or [])
    affected = set(segment_ids)
    kept = [
        item
        for item in confirmations
        if item.get('conversation_id') not in ids
        or (item.get('segment_ids') and not affected.intersection(item['segment_ids']))
    ]
    if len(kept) == len(confirmations):
        return {}
    base = owner_base(data)
    vectors = ([base] if base else []) + [item['embedding'] for item in kept]
    return {
        'speaker_embedding': pool_owner_vectors(vectors) if vectors else None,
        'speaker_embedding_base': base,
        'speaker_embedding_updated_at': now,
        'owner_voice_pooled_at': now,
        'owner_voice_confirmations': kept,
    }
