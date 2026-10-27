"""Pure construction and consumption identities for recovered WAL moments."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from utils.episodes import policy
from utils.episodes.moment import MomentInput


def segment_end(segment: Mapping[str, Any]) -> float:
    try:
        return float(segment.get('end') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def segment_start(segment: Mapping[str, Any]) -> float:
    try:
        return float(segment.get('start') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def receipt_id(segment: Mapping[str, Any]) -> str:
    """A revision/slice receipt, independent of the episode's placed cursor."""
    identity = segment.get('_episode_recovery_key', segment.get('id'))
    return (
        'sync:'
        + sha256(
            json.dumps(
                [
                    identity if identity else [segment_start(segment), segment_end(segment)],
                    str(segment.get('text') or '').strip(),
                ],
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
    )


def segment_batches(segments: Sequence[Mapping[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    """Keep all recovered words inside the moment renderer's 6000-character budget.

    Stable per-segment slices keep receipts independent of batch boundaries.
    Head/tail truncation must never mark unseen middle speech as consumed.
    """
    batch, chars = [], 0
    for segment in segments:
        text = str(segment.get('text') or '').strip()
        part = 0
        while text:
            cut = min(len(text), 1500)
            if cut < len(text):
                cut = text.rfind(' ', 0, cut) if ' ' in text[:cut] else cut
            chunk, text = text[:cut], text[cut:].lstrip()
            if batch and (chars + len(chunk) > 3000 or len(batch) >= 32):
                yield batch
                batch, chars = [], 0
            identity = segment.get('id') or [segment_start(segment), segment_end(segment)]
            # Speaker evidence resolves against the stored segment id. The slice
            # identity is private to consumption, never a replacement prompt id.
            batch.append(
                {
                    **segment,
                    '_episode_recovery_key': json.dumps([identity, part]),
                    '_episode_recovery_last': not text,
                    'text': chunk,
                }
            )
            chars += len(chunk)
            part += 1
    if batch:
        yield batch


def moments(
    conversation_id: str, row: Mapping[str, Any], *, now: datetime, calendar_identity: str | None
) -> Iterator[MomentInput]:
    segments = [s for s in row.get('transcript_segments') or [] if isinstance(s, Mapping)]
    if not segments:
        return
    started = policy.utc(row.get('started_at')) or policy.utc(row.get('created_at')) or now
    ended = policy.utc(row.get('finished_at')) or started + timedelta(
        seconds=max(0.0, max(segment_end(s) for s in segments))
    )
    for batch in segment_batches(segments):
        yield MomentInput(
            conversation_id=conversation_id,
            source=str(row.get('source') or '') or None,
            segments=batch,
            started_at=started,
            ended_at=min(ended, now),
            trigger='sync_recovery',
            calendar_identity=calendar_identity,
            language=row.get('language'),
        )
