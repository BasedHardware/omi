"""The Jev question and state for folding a conversation into its predecessor.

This is the benchmark's selected configuration: question wording A ("same
real-world occasion", a ``noul`` question) and input variant iv (chain-aware:
clock times and gap, up to four earlier conversations of the same stretch, A's
summary and transcript tail, B's summary and transcript head). Each input
raised dev AUC in the benchmark (0.707 -> 0.768 -> 0.820 -> 0.873), and the
threshold in ``config/conversation_smart_merge.py`` was measured on exactly
this text. Changing any sentence, section order, cap or rendering changes
calibration: bump ``QUESTION_VERSION`` and re-measure together.

A is always one *fragment*: the conversation as it was when it finished, with
its own title and summary. A survivor that already absorbed fragments keeps
their original titles and summaries in its ledger, so later decisions see the
same state shape the benchmark scored; they never read the survivor's
regenerated summary (the benchmark did not test one).

Durations and the gap are the stored wall fields (``finished_at - started_at``
and ``B.started_at - A.finished_at``), deliberately, because the benchmark
measured them that way. They are model input only, never a user-visible or
policy duration (``duration.py`` owns that).

Pure module: no I/O. Only the caller sees plaintext; records keep a hash.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, Mapping, Optional, Sequence

from config.conversation_smart_merge import (
    LEDGER_OVERVIEW_CHARS,
    LEDGER_TITLE_CHARS,
    STRETCH_SUMMARY_CHARS,
    TRANSCRIPT_EXCERPT_CHARS,
)

QUESTION_NAME = 'decision'
QUESTIONS: dict[str, dict[str, Any]] = {
    QUESTION_NAME: {
        'type': 'noul',
        'instructions': (
            'Is B a continuation of the same real-world occasion as A (the same gathering, meal, outing, '
            'meeting, work session, call, or trip resuming after a lull), so the user would want A and B '
            'shown as one conversation?'
        ),
        'criteria': {
            'true': 'The same occasion carries on: the same people, place, or activity continues, even if the topic drifts.',
            'false': (
                'A different occasion that merely follows closely in time: a new call, meeting, visit, or activity, '
                'or unrelated audio, with different people or purpose.'
            ),
        },
    },
}

DEVICE_DESCRIPTIONS = {
    'omi': 'the Omi pendant (a wearable microphone)',
    'desktop': 'the Omi desktop app (microphone and system audio)',
    'phone': 'the Omi phone app',
}

HEADER = (
    'Omi is a personal recorder that splits what it hears into conversations: a conversation ends after about '
    'two minutes without speech, and the next speech starts a new conversation. Below are two consecutive '
    'conversations captured by {device}: A (earlier) and B (the next one). Titles and summaries are AI-generated. '
    'Transcripts are imperfect speech-to-text: speaker labels are unreliable, and the audio can include TV or video, '
    'phone calls, or the owner dictating to AI assistants. The device owner is "the user".'
)

STRETCH_HEADER = (
    'Earlier conversations in the same stretch, oldest first (each began within 30 minutes of the '
    'previous one ending; A continues this stretch):'
)


@dataclass(frozen=True)
class Fragment:
    """One conversation as it finished: identity, wall times, and its own summary."""

    id: str
    started_at: datetime
    finished_at: datetime
    title: str
    overview: str

    def as_ledger_entry(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'title': self.title[:LEDGER_TITLE_CHARS],
            'overview': self.overview[:LEDGER_OVERVIEW_CHARS],
        }

    @classmethod
    def from_ledger_entry(cls, entry: Mapping[str, Any]) -> Optional['Fragment']:
        started, finished = entry.get('started_at'), entry.get('finished_at')
        if not isinstance(started, datetime) or not isinstance(finished, datetime) or not entry.get('id'):
            return None
        return cls(
            id=str(entry['id']),
            started_at=started,
            finished_at=finished,
            title=str(entry.get('title') or '')[:LEDGER_TITLE_CHARS],
            overview=str(entry.get('overview') or '')[:LEDGER_OVERVIEW_CHARS],
        )


def _clock(value: datetime, tz: tzinfo) -> str:
    return value.astimezone(tz).strftime('%a %Y-%m-%d %H:%M')


def _minutes(seconds: float) -> int:
    # Python's round, as the benchmark generator used.
    return round(seconds / 60)


def transcript_lines(segments: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = []
    for segment in segments:
        text = str(segment.get('text') or '').strip()
        who = 'User' if segment.get('is_user') else f'Speaker {segment.get("speaker_id")}'
        lines.append(f'{who}: {text}')
    return lines


def transcript_tail(segments: Sequence[Mapping[str, Any]], limit: int = TRANSCRIPT_EXCERPT_CHARS) -> str:
    """Whole lines from the end; one oversized line is cut from its start."""
    out: list[str] = []
    total = 0
    for line in reversed(transcript_lines(segments)):
        if total + len(line) > limit and out:
            break
        out.insert(0, line)
        total += len(line) + 1
    text = '\n'.join(out)
    return text[-limit:] if len(text) > limit else text


def transcript_head(segments: Sequence[Mapping[str, Any]], limit: int = TRANSCRIPT_EXCERPT_CHARS) -> str:
    """Whole lines from the start; one oversized line is cut at its end."""
    out: list[str] = []
    total = 0
    for line in transcript_lines(segments):
        if total + len(line) > limit and out:
            break
        out.append(line)
        total += len(line) + 1
    return '\n'.join(out)[:limit]


def _summary_block(label: str, fragment: Fragment) -> str:
    return f'Conversation {label}\nTitle: {fragment.title}\nSummary: {fragment.overview}'


def build_state(
    *,
    source: str,
    a: Fragment,
    a_segments: Sequence[Mapping[str, Any]],
    b: Fragment,
    b_segments: Sequence[Mapping[str, Any]],
    stretch: Sequence[Fragment],
    tz: tzinfo,
) -> str:
    """Render benchmark variant iv. ``stretch`` is oldest first and already capped."""
    gap_seconds = (b.started_at - a.finished_at).total_seconds()
    parts = [
        HEADER.format(device=DEVICE_DESCRIPTIONS.get(source, source)),
        (
            f'Timing (local time): A ran {_clock(a.started_at, tz)} to {_clock(a.finished_at, tz)[-5:]} '
            f'({_minutes((a.finished_at - a.started_at).total_seconds())} min). B started {_clock(b.started_at, tz)}, '
            f'{_minutes(gap_seconds)} min after A ended, and ran '
            f'{_minutes((b.finished_at - b.started_at).total_seconds())} min.'
        ),
    ]
    if stretch:
        lines = [STRETCH_HEADER]
        for fragment in stretch:
            lines.append(
                f'- {_clock(fragment.started_at, tz)[-5:]} {fragment.title}: '
                f'{fragment.overview[:STRETCH_SUMMARY_CHARS]}'
            )
        parts.append('\n'.join(lines))
    parts.append(_summary_block('A', a))
    parts.append("End of A's transcript (last part):\n" + transcript_tail(a_segments))
    parts.append(_summary_block('B', b))
    parts.append("Start of B's transcript (first part):\n" + transcript_head(b_segments))
    return '\n\n'.join(parts)


def state_sha256(state: str) -> str:
    """Stored instead of the state: lets a reviewer match a record to a replay without any text."""
    return hashlib.sha256(state.encode('utf-8')).hexdigest()
