"""Bounded, internal snapshots of already-computed voice verification evidence.

No embeddings, text, or storage IO. Diagnostics load only when observed. Stage-local speaker keys must not be joined across
resolution/reconnects. Each stage retains at most 16 rows, updated in place.
"""

import math
import os
from typing import Any, Mapping

MAX_SPEAKERS_PER_STAGE = 16
STAGES = ('capture', 'sync', 'resolution')
FIELD = 'speaker_match_scores'
# Includes compression/encryption overhead; the stored field never exceeds 8 KiB.
MAX_STORED_BYTES = 8 * 1024


def enabled() -> bool:
    default = 'true' if os.getenv('OMI_ENV_STAGE', 'prod') in ('dev', 'local', 'offline') else 'false'
    return os.getenv('SPEAKER_MATCH_SCORES_ENABLED', default).strip().lower() in ('true', '1', 'on', 'yes')


def record_failure(log, *, trimmed: bool = False, reason: str = 'other') -> None:
    """Optional instrumentation must not turn its own failure into a content failure."""
    try:
        # Fixture suites install empty utils packages while importing models.
        # Resolve optional telemetry only at the observation boundary.
        import utils.observability.fallback as reporter

        reporter.record_fallback(
            component='conversation_finalization',
            from_mode=FIELD,
            to_mode='scores_trimmed' if trimmed else 'scores_omitted',
            reason=reason,
            outcome='degraded',
            log=log,
        )
    except Exception:
        pass


def merge_processing(current: list, snapshot: list, *, replace_resolution: bool = False) -> list:
    """Current capture/sync wins; an explicit resolution may replace with no rows."""
    current = merge(None, current)
    snapshot = merge(None, snapshot)
    new_resolution = [r for r in snapshot if r['stage'] == 'resolution']
    retained = [r for r in current if not (new_resolution or replace_resolution) or r['stage'] != 'resolution']
    keys = {(r['stage'], r.get('speaker_id_scope', ''), r['speaker_id']) for r in retained}
    retained += [
        r
        for r in snapshot
        if r['stage'] != 'resolution' and (r['stage'], r.get('speaker_id_scope', ''), r['speaker_id']) not in keys
    ]
    return merge(retained, new_resolution)


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


def normalize(value: Any) -> list:
    """Validate decoded shape before a typed conversation can observe it."""
    if not isinstance(value, list):
        raise ValueError('speaker scores must be a list')
    for row in value:
        if not isinstance(row, dict) or row.get('stage') not in STAGES:
            raise ValueError('invalid speaker score row')
        if type(row.get('speaker_id')) is not int or not isinstance(row.get('speaker_id_scope', ''), str):
            raise ValueError('invalid speaker score key')
    return merge(None, [dict(row, speaker_id_scope=row.get('speaker_id_scope', '')[:128]) for row in value])


def aggregate(conversations) -> list | None:
    """Best-effort union of already decoded conversation metadata at merge seams."""
    try:
        rows = []
        for conversation in conversations:
            for row in normalize(conversation.get(FIELD, [])):
                if not row['speaker_id_scope'] and conversation.get('id'):
                    row['speaker_id_scope'] = f"conversation:{conversation['id']}"[:128]
                rows.append(row)
        return merge(None, rows) or None
    except Exception:
        record_failure(None, reason='malformed_doc')
        return None


def from_segments(segments: list) -> list:
    return merge(None, [row for segment in segments if (row := segment.get(FIELD))])


def encode_bounded(rows: list, encode) -> tuple[object, bool]:
    """Trim optional snapshots to the final stored byte budget, including encryption."""
    retained = merge(None, rows)
    trimmed = False
    if not retained:
        # An explicit empty processing snapshot can clear a prior resolution.
        # Absence still means no new evidence, and trimming every row below
        # remains an omission rather than a successful empty replacement.
        encoded = encode([])
        size = len(encoded.encode('utf-8')) if isinstance(encoded, str) else len(encoded)
        return (encoded, False) if size <= MAX_STORED_BYTES else (None, True)
    while retained:
        encoded = encode(retained)
        size = len(encoded.encode('utf-8')) if isinstance(encoded, str) else len(encoded)
        if size <= MAX_STORED_BYTES:
            return encoded, trimmed
        retained.pop()
        trimmed = True
    return None, trimmed
