"""Deterministic owner-usefulness judge.

Scores a note for the defects that make David's own summaries unusable:
playback/incidental device commands, filler surviving into the recap,
speaker-cluster leaks, and missing owner threads. Heuristic, not an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FILLER = re.compile(
    r"\b(?:um+|uh+|erm+|you know|i mean|like,? yeah|kind of|sort of)\b",
    re.IGNORECASE,
)
_PLAYBACK = re.compile(
    r"\b(?:pause(?:d|s| the)?|skip(?:ped|s)?(?: (?:this|that|the))? (?:song|track|episode)|"
    r"next song|rewind|volume (?:up|down)|hey google|hey siri|ok google|"
    r"play(?:ed)? (?:the )?(?:music|podcast))\b",
    re.IGNORECASE,
)
_SPEAKER_LEAK = re.compile(
    r"\b(?:speaker\s+\d+|spk[_ ]?\d+|speaker_\d+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JudgeReport:
    usefulness: float
    defects: tuple[str, ...]
    missing_facts: tuple[str, ...]
    filler_hits: int
    playback_hits: int
    speaker_leaks: int

    def as_dict(self) -> dict[str, object]:
        return {
            'usefulness': round(self.usefulness, 3),
            'defects': list(self.defects),
            'missing_facts': list(self.missing_facts),
            'filler_hits': self.filler_hits,
            'playback_hits': self.playback_hits,
            'speaker_leaks': self.speaker_leaks,
        }


def _flatten_note(note: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ('title', 'overview'):
        value = note.get(key)
        if isinstance(value, str):
            parts.append(value)
    sections = note.get('sections')
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = section.get('heading')
            body = section.get('body_markdown') or section.get('body')
            if isinstance(heading, str):
                parts.append(heading)
            if isinstance(body, str):
                parts.append(body)
    items = note.get('action_items')
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                description = item.get('description')
                if isinstance(description, str):
                    parts.append(description)
            elif isinstance(item, str):
                parts.append(item)
    return '\n'.join(parts)


def score_note(
    note: dict[str, object],
    *,
    expected_facts: tuple[str, ...] = (),
    must_not_contain: tuple[str, ...] = (),
) -> JudgeReport:
    text = _flatten_note(note)
    lowered = text.lower()
    defects: list[str] = []
    filler_hits = len(_FILLER.findall(text))
    playback_hits = len(_PLAYBACK.findall(text))
    speaker_leaks = len(_SPEAKER_LEAK.findall(text))
    if filler_hits:
        defects.append(f'filler:{filler_hits}')
    if playback_hits:
        defects.append(f'playback:{playback_hits}')
    if speaker_leaks:
        defects.append(f'speaker-leak:{speaker_leaks}')

    for phrase in must_not_contain:
        if phrase.strip() and phrase.lower() in lowered:
            defects.append(f'forbidden:{phrase}')

    missing = tuple(fact for fact in expected_facts if fact.lower() not in lowered)

    usefulness = 1.0
    usefulness -= min(0.45, 0.15 * filler_hits)
    usefulness -= min(0.50, 0.25 * playback_hits)
    usefulness -= min(0.40, 0.20 * speaker_leaks)
    usefulness -= 0.12 * len([d for d in defects if d.startswith('forbidden:')])
    usefulness -= 0.20 * len(missing)
    usefulness = max(0.0, min(1.0, usefulness))
    return JudgeReport(
        usefulness=usefulness,
        defects=tuple(defects),
        missing_facts=missing,
        filler_hits=filler_hits,
        playback_hits=playback_hits,
        speaker_leaks=speaker_leaks,
    )
