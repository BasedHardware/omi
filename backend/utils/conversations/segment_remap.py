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


def _offset_candidates(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> set[float]:
    """Keep repeated phrases as candidates; their timing resolves the repetition."""
    buckets: dict[float, list[float]] = {}
    for source in old:
        phrase = _tokens(source)
        if len(phrase) < 12:
            continue
        for target in new:
            other = _tokens(target)
            if len(other) < 12:
                continue
            similarity = SequenceMatcher(None, phrase, other, autojunk=False).ratio()
            if similarity >= 0.65:
                a, b = _bounds(source)
                c, d = _bounds(target)
                shifts = [(c + d - a - b) / 2]
                if similarity < 0.82:
                    # One transcript may split a longer sentence. Its first or
                    # last edge can still anchor the common text on the clock.
                    shifts.extend((c - a, d - b))
                for candidate in shifts:
                    shift = round(candidate, 3)
                    if abs(shift) <= 600:
                        buckets.setdefault(round(shift, 1), []).append(shift)
    # Repeated speech can produce many placements. Keep the strongest clock
    # clusters, with a fixed bound on the subsequent whole-transcript scoring.
    ranked = sorted(buckets.values(), key=lambda values: (-len(values), abs(median(values))))[:64]
    return {0.0, *(round(median(values), 3) for values in ranked)}


def estimate_offset(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> float:
    """Choose the text-anchored shift with the most unambiguous time mappings.

    A repeated sentence is not a unique anchor. Score every matching placement
    against the whole ordered transcript, rather than taking the median of a
    few locally unique matches.
    """
    candidates = _offset_candidates(old, new)
    scored = []
    for shift in candidates:
        plan = _plan_at_offset(old, new, shift)
        agreement = _text_agreement(old, new, plan)
        scored.append((len(plan.ids), -len(plan.ambiguous), agreement, -len(plan.unresolved), -abs(shift), shift))
    return max(scored)[-1] if scored else 0.0


def _text_agreement(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], plan: 'RemapPlan') -> float:
    targets = {str(item['id']): _tokens(item) for item in new}
    matches = []
    for source in old:
        ids = plan.ids.get(str(source['id']))
        if ids:
            phrase = _tokens(source)
            other = ' '.join(targets[tid] for tid in ids)
            if phrase and other:
                matches.append(SequenceMatcher(None, phrase, other, autojunk=False).ratio())
    return sum(matches) / len(matches) if matches else 0.0


@dataclass(frozen=True)
class RemapPlan:
    offset_seconds: float
    ids: dict[str, tuple[str, ...]]
    unresolved: tuple[str, ...]
    ambiguous: tuple[str, ...]
    offset_verified: bool = True

    @property
    def success_rate(self) -> float:
        total = len(self.ids) + len(self.unresolved) + len(self.ambiguous)
        return len(self.ids) / total if total else 1.0

    @property
    def safe(self) -> bool:
        return self.offset_verified and not self.unresolved and not self.ambiguous


def plan_segment_remap(
    old: Sequence[Mapping[str, Any]],
    new: Sequence[Mapping[str, Any]],
    *,
    offset_seconds: float | None = None,
) -> RemapPlan:
    shift = estimate_offset(old, new) if offset_seconds is None else offset_seconds
    plan = _plan_at_offset(old, new, shift)
    # An inferred shift, including zero, needs independent agreement from
    # the mapped text. Explicit offsets are a caller-supplied clock contract.
    if offset_seconds is None and old and new and _text_agreement(old, new, plan) < 0.65:
        return RemapPlan(shift, plan.ids, plan.unresolved, plan.ambiguous, offset_verified=False)
    return plan


def _plan_at_offset(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], shift: float) -> RemapPlan:
    targets = [(str(s['id']), *_bounds(s)) for s in new]
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
        choices: list[str] = []
        for tid, left, right in targets:
            overlap = max(0.0, min(end, right) - max(start, left))
            if overlap <= 0:
                continue
            fraction = overlap / min(end - start, right - left)
            if fraction >= 0.5:
                choices.append(tid)
        if not choices:
            unresolved.append(sid)
            continue
        # Sequential splits can inherit one source annotation. Concurrent
        # target intervals may be different voices; text similarity does not
        # prove which one owns the source annotation.
        if len(choices) > 1:
            selected = set(choices)
            intervals = sorted((left, right) for tid, left, right in targets if tid in selected)
            if any(next_left < left_right for (_, left_right), (next_left, _) in zip(intervals, intervals[1:])):
                ambiguous.append(sid)
                continue
        mapped[sid] = tuple(choices)
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
