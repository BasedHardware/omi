"""Pure, fail-closed mapping of transcript annotations across segment boundaries.

Times are seconds relative to each transcript's own origin.  Callers may supply
an offset or let matching text estimate live-to-batch clock drift.  No text is
returned in diagnostics, and no annotation is silently assigned across an
ambiguous overlap.
"""

from __future__ import annotations

import re
from collections import Counter
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


def _midpoint(segment: Mapping[str, Any]) -> float:
    start, end = _bounds(segment)
    return (start + end) / 2


def _unique_offset(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> tuple[float, bool]:
    """Only phrases occurring once on each side can verify a shared clock."""
    old_text = [_tokens(item) for item in old]
    new_text = [_tokens(item) for item in new]
    old_counts, new_counts = Counter(old_text), Counter(new_text)
    target_index = {phrase: index for index, phrase in enumerate(new_text) if phrase}
    anchors = [
        (index, target_index[phrase])
        for index, phrase in enumerate(old_text)
        if len(phrase) >= 12 and old_counts[phrase] == new_counts[phrase] == 1
    ]
    if not anchors or any(right[1] <= left[1] for left, right in zip(anchors, anchors[1:])):
        return 0.0, False
    shifts = [_midpoint(new[j]) - _midpoint(old[i]) for i, j in anchors]
    offset = median(shifts)
    return round(offset, 3), abs(offset) <= 600 and all(abs(shift - offset) <= 1.5 for shift in shifts)


def _align(
    old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], offset: float | None
) -> tuple[list[tuple[int, int]], set[str]]:
    """Global monotone alignment; forward/backward scores expose competing placements."""
    n, m = len(old), len(new)
    if n * m > 250_000:
        return [], {str(item['id']) for item in old}
    source_text = [_tokens(item) for item in old]
    target_text = [_tokens(item) for item in new]
    scores: list[list[float | None]] = []
    for i, phrase in enumerate(source_text):
        row = []
        for j, other in enumerate(target_text):
            similarity = SequenceMatcher(None, phrase, other, autojunk=False).ratio() if phrase and other else 0
            if similarity < 0.65:
                row.append(None)
                continue
            duration_a = old[i]['end'] - old[i]['start']
            duration_b = new[j]['end'] - new[j]['start']
            score = 2 + 2 * similarity - 0.5 * abs(duration_a - duration_b) / max(duration_a, duration_b)
            if offset is not None:
                score -= min(5.0, 2 * abs(_midpoint(new[j]) - _midpoint(old[i]) - offset))
            row.append(score)
        scores.append(row)

    gap = -1.0
    forward = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        forward[i][0] = i * gap
    for j in range(1, m + 1):
        forward[0][j] = j * gap
    for i in range(n):
        for j in range(m):
            pair_score = scores[i][j]
            match = forward[i][j] + pair_score if pair_score is not None else float('-inf')
            forward[i + 1][j + 1] = max(match, forward[i][j + 1] + gap, forward[i + 1][j] + gap)

    backward = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        backward[i][m] = (n - i) * gap
    for j in range(m - 1, -1, -1):
        backward[n][j] = (m - j) * gap
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            pair_score = scores[i][j]
            match = pair_score + backward[i + 1][j + 1] if pair_score is not None else float('-inf')
            backward[i][j] = max(match, backward[i + 1][j] + gap, backward[i][j + 1] + gap)

    matches = []
    i, j = n, m
    while i and j:
        score = scores[i - 1][j - 1]
        if score is not None and abs(forward[i][j] - forward[i - 1][j - 1] - score) < 1e-6:
            matches.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif abs(forward[i][j] - forward[i - 1][j] - gap) < 1e-6:
            i -= 1
        else:
            j -= 1
    matches.reverse()
    selected = dict(matches)
    ambiguous = set()
    for i, row in enumerate(scores):
        alternatives = [
            j
            for j, score in enumerate(row)
            if score is not None and forward[i][j] + score + backward[i + 1][j + 1] >= forward[n][m] - 0.5
        ]
        if len(alternatives) > 1 or (alternatives and selected.get(i) not in alternatives):
            ambiguous.add(str(old[i]['id']))
    return matches, ambiguous


def estimate_offset(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> float:
    offset, verified = _unique_offset(old, new)
    if verified:
        return offset
    matches, _ = _align(old, new, None)
    return round(median([_midpoint(new[j]) - _midpoint(old[i]) for i, j in matches]), 3) if matches else 0.0


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
    for label, segments in (('source', old), ('target', new)):
        if len({str(item['id']) for item in segments}) != len(segments):
            raise ValueError(f'duplicate {label} segment id')
        for item in segments:
            _bounds(item)
    inferred = offset_seconds is None
    anchored_shift, anchored = _unique_offset(old, new) if inferred else (0.0, True)
    matches: list[tuple[int, int]] = []
    competing: set[str] = set()
    if inferred:
        matches, competing = _align(old, new, anchored_shift if anchored else None)
        shift = (
            anchored_shift
            if anchored
            else round(median([_midpoint(new[j]) - _midpoint(old[i]) for i, j in matches]), 3) if matches else 0.0
        )
    else:
        shift = offset_seconds
    plan = _plan_at_offset(old, new, shift)
    # An inferred shift, including zero, needs independent agreement from
    # the mapped text. Explicit offsets are a caller-supplied clock contract.
    if inferred:
        aligned_ids = {str(old[i]['id']) for i, _ in matches}
        # An overlap at the inferred clock cannot override the ordered text match.
        competing.update(
            str(old[i]['id'])
            for i, j in matches
            if str(old[i]['id']) in plan.ids and str(new[j]['id']) not in plan.ids[str(old[i]['id'])]
        )
        ambiguous = tuple(
            dict.fromkeys((*plan.ambiguous, *(str(item['id']) for item in old if str(item['id']) in competing)))
        )
        unmatched = {str(item['id']) for item in old if str(item['id']) not in aligned_ids}
        ids = {sid: targets for sid, targets in plan.ids.items() if sid not in competing | unmatched}
        unresolved = tuple(
            dict.fromkeys((*plan.unresolved, *(str(item['id']) for item in old if str(item['id']) in unmatched)))
        )
        unresolved = tuple(sid for sid in unresolved if sid not in ambiguous)
        verified = anchored and (not old or not new or _text_agreement(old, new, plan) >= 0.65)
        return RemapPlan(shift, ids, unresolved, ambiguous, offset_verified=verified)
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
