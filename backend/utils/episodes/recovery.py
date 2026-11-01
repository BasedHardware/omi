"""Pure construction and consumption identities for recovered WAL moments."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from utils.episodes import policy
from utils.episodes.moment import MomentInput


def receipt_namespace(conversation_id: str) -> str:
    """Separate content revisions from the legacy unplaced-ID receipt window."""
    return f'content-v1:{conversation_id}'


def content_receipts(segments: Sequence[Mapping[str, Any]]) -> set[str]:
    return {receipt_id(segment) for batch in segment_batches(segments) for segment in batch}


def select_segments(
    segments: Sequence[Mapping[str, Any]],
    consumed: set[str],
    consumed_content: set[str],
    applied_until: float,
    *,
    recovered: bool,
) -> tuple[list[Mapping[str, Any]], set[str], set[str]]:
    selected, ids, content = [], set(), set()
    for segment in segments:
        sid = segment.get('id')
        if not str(segment.get('text') or '').strip():
            continue
        if recovered:
            key = receipt_id(segment)
            if key in consumed_content or key in content:
                continue
            # Legacy unplaced IDs are already durable proof of consumption.
            if segment_end(segment) < 0 and sid and sid in consumed:
                continue
            content.add(key)
            if segment_end(segment) < 0 and sid and segment.get('_episode_recovery_last', True):
                ids.add(sid)
        else:
            if sid in consumed or sid in ids:
                continue
            if segment_end(segment) < 0:
                if not sid:
                    continue
                ids.add(sid)
            elif segment_end(segment) <= applied_until:
                continue
        selected.append(segment)
    return selected, ids, content


def segment_end(segment: Mapping[str, Any]) -> float:
    try:
        return float(segment.get('end') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def uncovered_segments(moment: MomentInput, episode: Mapping[str, Any] | None):
    """A parallel device adds later speech without replaying the original capture.

    Attachment persists the overlap span before adding membership; both recovery and
    finalization must honor it. Unplaced speech and crossing segments remain
    eligible because their text cannot safely be split at the overlap boundary.
    """
    span = ((episode or {}).get('parallel_content_spans') or {}).get(moment.conversation_id) or {}
    start, end = policy.utc(span.get('start')), policy.utc(span.get('end'))
    if start is None or end is None:
        return moment.segments
    return [
        segment
        for segment in moment.segments
        if segment_end(segment) < 0
        or moment.started_at + timedelta(seconds=segment_start(segment)) < start
        or moment.started_at + timedelta(seconds=segment_end(segment)) > end
    ]


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
