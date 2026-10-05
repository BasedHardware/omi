"""Bounded, internal snapshots of already-computed voice verification evidence.

No embeddings, text, or IO. Stage-local speaker keys must not be joined across
resolution/reconnects. Each stage retains at most 16 rows, updated in place.
"""

import math
import os
from typing import Any, Mapping

MAX_SPEAKERS_PER_STAGE = 16
STAGES = ('capture', 'sync', 'resolution')
FIELD = 'speaker_match_scores'


def enabled() -> bool:
    default = 'true' if os.getenv('OMI_ENV_STAGE', 'prod') in ('dev', 'local', 'offline') else 'false'
    return os.getenv('SPEAKER_MATCH_SCORES_ENABLED', default).strip().lower() in ('true', '1', 'on', 'yes')


def rounded(value: float | None) -> float | None:
    return round(float(value), 3) if value is not None and math.isfinite(value) else None


def summarize(
    speaker_id: int,
    distances: Mapping[str, float],
    decision: Any,
    evidence_seconds: float | None,
    stage: str,
    *,
    threshold: float,
    margin_threshold: float = 0.10,
    scope: str = '',
    outcome: str | None = None,
    accepted: bool | None = None,
) -> dict:
    people = [(d, pid) for pid, d in distances.items() if pid != 'user' and math.isfinite(d)]
    person_distance, person_id = min(people, default=(float('inf'), None))
    accepted_id = decision.person_id if (decision.accepted if accepted is None else accepted) else None
    status = (
        'ambiguous'
        if decision.owner_contended
        else 'user' if accepted_id == 'user' else 'not_user' if accepted_id is not None else 'no_match'
    )
    return {
        'speaker_id': speaker_id,
        'speaker_id_scope': scope[:128],
        'owner_distance': rounded(distances.get('user', float('inf'))),
        'person_distance': rounded(person_distance),
        'person_id': person_id,
        # The nearest-vs-runner-up gap used by select_speaker_match; null when
        # only one finite candidate exists. Distances above allow owner gap analysis.
        'margin': rounded(decision.runner_up_distance - decision.best_distance),
        'evidence_seconds': rounded(evidence_seconds),
        'status': status,
        'decision': outcome or ('accepted' if accepted_id is not None else status),
        'accepted_person_id': accepted_id,
        'stage': stage,
        'version': 1,
        'threshold': rounded(threshold),
        'margin_threshold': rounded(margin_threshold),
    }


def merge(existing: list | None, updates: list) -> list:
    """Last snapshot wins per stage/scope/speaker; cap independently per stage."""
    rows = {}
    for row in [*(existing or []), *updates]:
        if isinstance(row, dict) and row.get('stage') in STAGES:
            key = (row['stage'], row.get('speaker_id_scope', ''), row['speaker_id'])
            rows[key] = row
    return [
        row for stage in STAGES for row in [r for r in rows.values() if r['stage'] == stage][:MAX_SPEAKERS_PER_STAGE]
    ]


def from_segments(segments: list) -> list:
    return merge(None, [row for segment in segments if (row := segment.get(FIELD))])
