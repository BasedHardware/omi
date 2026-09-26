"""Pure, fail-closed mapping of transcript annotations across segment boundaries.

Times are seconds relative to each transcript's own origin.  Callers may supply
an offset or let matching text estimate live-to-batch clock drift.  No text is
returned in diagnostics, and no annotation is silently assigned across an
ambiguous overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import median
from typing import Any, Mapping, Sequence


def _tokens(segment: Mapping[str, Any]) -> str:
    return ' '.join(re.findall(r"\w+", str(segment.get('text') or '').casefold()))


def _bounds(segment: Mapping[str, Any]) -> tuple[float, float]:
    start, end = float(segment['start']), float(segment['end'])
    if not 0 <= start < end:
        raise ValueError('invalid segment interval')
    return start, end


def estimate_offset(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> float:
    """Return the shift to add to live times, using distinctive matching text.

    Zero remains the conservative default when there is no convincing anchor.
    The caller sees the chosen shift and can reject a low remap rate.
    """
    candidates: list[float] = []
    for source in old:
        phrase = _tokens(source)
        if len(phrase) < 12:
            continue
        matches = []
        for target in new:
            other = _tokens(target)
            if len(other) < 12:
                continue
            similarity = SequenceMatcher(None, phrase, other, autojunk=False).ratio()
            if similarity >= 0.82:
                matches.append((similarity, target))
        matches.sort(key=lambda pair: pair[0], reverse=True)
        if not matches or (len(matches) > 1 and matches[0][0] - matches[1][0] < 0.08):
            continue
        a, b = _bounds(source)
        c, d = _bounds(matches[0][1])
        shift = (c + d - a - b) / 2
        if abs(shift) <= 600:
            candidates.append(shift)
    return round(median(candidates), 3) if candidates else 0.0


@dataclass(frozen=True)
class RemapPlan:
    offset_seconds: float
    ids: dict[str, tuple[str, ...]]
    unresolved: tuple[str, ...]
    ambiguous: tuple[str, ...]

    @property
    def success_rate(self) -> float:
        total = len(self.ids) + len(self.unresolved) + len(self.ambiguous)
        return len(self.ids) / total if total else 1.0

    @property
    def safe(self) -> bool:
        return not self.unresolved and not self.ambiguous


def plan_segment_remap(
    old: Sequence[Mapping[str, Any]],
    new: Sequence[Mapping[str, Any]],
    *,
    offset_seconds: float | None = None,
) -> RemapPlan:
    shift = estimate_offset(old, new) if offset_seconds is None else offset_seconds
    targets = [(str(s['id']), *_bounds(s), _tokens(s)) for s in new]
    if len({item[0] for item in targets}) != len(targets):
        raise ValueError('duplicate target segment id')
    mapped: dict[str, tuple[str, ...]] = {}
    unresolved: list[str] = []
    ambiguous: list[str] = []
    seen: set[str] = set()
    for source in old:
        sid = str(source['id'])
        if sid in seen:
            raise ValueError('duplicate source segment id')
        seen.add(sid)
        start, end = _bounds(source)
        start += shift
        end += shift
        choices: list[tuple[str, float, float]] = []
        for tid, left, right, phrase in targets:
            overlap = max(0.0, min(end, right) - max(start, left))
            if overlap <= 0:
                continue
            fraction = overlap / min(end - start, right - left)
            similarity = SequenceMatcher(None, _tokens(source), phrase, autojunk=False).ratio()
            if fraction >= 0.5:
                choices.append((tid, fraction, similarity))
        if not choices:
            unresolved.append(sid)
            continue
        # A split or merge can have several real overlaps.  Two target voices
        # occupying the same interval cannot be disambiguated by clock alone.
        if len(choices) > 1:
            ranked = sorted(choices, key=lambda item: (item[1], item[2]), reverse=True)
            tied = abs(ranked[0][1] - ranked[1][1]) < 0.05
            if tied and abs(ranked[0][2] - ranked[1][2]) < 0.15:
                first = next(t for t in targets if t[0] == ranked[0][0])
                second = next(t for t in targets if t[0] == ranked[1][0])
                if min(first[2], second[2]) - max(first[1], second[1]) > 0.25:
                    ambiguous.append(sid)
                    continue
        mapped[sid] = tuple(tid for tid, _, _ in choices)
    return RemapPlan(shift, mapped, tuple(unresolved), tuple(ambiguous))


def remap_receipt(
    receipt: Mapping[str, Any], old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], plan: RemapPlan
) -> dict[str, Any]:
    """Carry explicit segment and speaker receipts; reject conflicting merges.

    Speaker-wide receipts are expanded through the old speaker's segments and
    then attached to target segment ids.  A new diarization's numeric speaker
    ids cannot inherit old numeric ids safely.
    """
    decisions: dict[str, dict[str, Any]] = {}
    old_by_id = {str(s['id']): s for s in old}
    for sid, source in old_by_id.items():
        speaker = (receipt.get('speakers') or {}).get(str(source.get('speaker_id')))
        explicit = (receipt.get('segments') or {}).get(sid)
        selected = max((d for d in (speaker, explicit) if d), key=lambda d: d.get('generation', 0), default=None)
        if selected is None:
            continue
        for tid in plan.ids.get(sid, ()):
            prior = decisions.get(tid)
            if prior and (prior.get('person_id'), prior.get('is_user')) != (
                selected.get('person_id'),
                selected.get('is_user'),
            ):
                raise ValueError('conflicting manual identity on merged segment')
            if prior is None or selected.get('generation', 0) > prior.get('generation', 0):
                decisions[tid] = dict(selected)
        if sid not in plan.ids:
            raise ValueError('manual identity has no safe target')
    result = {k: v for k, v in receipt.items() if k not in {'segments', 'speakers'}}
    if decisions:
        result['segments'] = decisions
    return result


def remap_translations(old: Sequence[Mapping[str, Any]], plan: RemapPlan) -> dict[str, list[dict[str, Any]]]:
    """Preserve translations only across one-to-one intervals.

    A whole translated sentence cannot be split into words or merged with
    another translation by time overlap.  Such a case blocks record promotion.
    """
    output: dict[str, list[dict[str, Any]]] = {}
    for segment in old:
        translations = segment.get('translations') or []
        if not translations:
            continue
        targets = plan.ids.get(str(segment['id']), ())
        if len(targets) != 1 or targets[0] in output:
            raise ValueError('translation segmentation changed')
        output[targets[0]] = [dict(t) for t in translations]
    return output


def remap_source_ids(source_ids: Sequence[str], plan: RemapPlan) -> list[str]:
    result: list[str] = []
    for sid in source_ids:
        targets = plan.ids.get(sid)
        if not targets:
            raise ValueError('summary source has no safe target')
        for tid in targets:
            if tid not in result:
                result.append(tid)
    return result
