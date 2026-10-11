"""Bounded speaker outcomes; user edits are a biased precision proxy, not FAR."""

import logging
from typing import Any, Sequence

from prometheus_client import Counter

logger = logging.getLogger(__name__)
SYNC_SPEAKER_DECISIONS = Counter(
    'omi_sync_speaker_decisions_total', 'Batch voice match attempts, including missing evidence.', ['outcome']
)
SYNC_SPEAKER_REVIEWS = Counter(
    'omi_sync_speaker_reviewed_segments_total',
    'First manual review of a persisted sync embedding label, per segment.',
    ['outcome'],
)


def record_speaker_review(
    uid: str, conversation_id: str, before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]
) -> None:
    """Call only after commit. Clearing provenance in that write prevents repeats.

    Transaction retries emit nothing; HTTP retries see the cleared provenance.
    A crash after commit can lose this best-effort observation. No unedited label
    is evidence of correctness and historical labels have unknown provenance.
    """
    by_id = {segment.get('id'): segment for segment in after}
    for old in before:
        if old.get('speaker_match_source') != 'sync_embedding':
            continue
        new = by_id.get(old.get('id'))
        if new is None or new.get('speaker_match_source') == 'sync_embedding':
            continue
        old_identity = ('user', None) if old.get('is_user') else ('person', old.get('person_id'))
        new_identity = ('user', None) if new.get('is_user') else ('person', new.get('person_id'))
        outcome = 'confirmed' if old_identity == new_identity else 'corrected'
        SYNC_SPEAKER_REVIEWS.labels(outcome=outcome).inc()
        logger.info(
            'speaker_id_review surface=sync uid=%s conversation=%s segment=%s outcome=%s',
            uid,
            conversation_id,
            old.get('id'),
            outcome,
        )
