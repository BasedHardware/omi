"""Pure, conservative text location using actual ASR entry boundaries.

No token is assigned an interpolated timestamp. Word-level point timings are supported; untimed coarse text is rejected.
Separate occurrences, including
copies in separate blobs, remain competitors. Callers must prove that their
source index is complete before accepting a result.
"""

import math
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

MIN_ANCHOR_TOKENS = 12
MIN_DISTINCT_TOKENS = 8
MAX_ANCHOR_TOKENS = 32
MATCH_RATIO = 0.9
COMPETITOR_RATIO = 0.8
MAX_MATCH_SECONDS = 120.0


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize('NFC', text).casefold()
    return re.findall(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0e00-\u0e7f]|[^\W_]+', text)


@dataclass(frozen=True)
class TextLocation:
    source: int
    start: float
    end: float
    score: float
    token_start: int = 0


def locate_text(
    expected: str,
    sources: Sequence[tuple[Sequence[Mapping[str, Any]], float]],
    *,
    complete: bool,
    deadline: float | None = None
) -> tuple[TextLocation | None, str]:
    """Locate one unique ordered phrase in a fully enumerated source index.

    ``sources`` contains provider entries and decoded duration per independent
    blob. A coarse entry is eligible only when the whole entry participates in
    the text match. Never cross blobs or interpolate a partial coarse entry.
    """
    full_expected = tokens(expected)
    want = full_expected[:MAX_ANCHOR_TOKENS]
    if len(full_expected) > 4096 or len(want) < MIN_ANCHOR_TOKENS or len(set(want)) < MIN_DISTINCT_TOKENS:
        return None, 'short_or_generic'
    if not complete:
        return None, 'budget_exhausted'
    matches: list[TextLocation] = []
    alignments: list[dict[int, tuple[int, int]]] = []
    invalid_alignments: list[dict[int, tuple[int, int]]] = []
    total_tokens = 0
    for source, (entries, duration) in enumerate(sources):
        timeline: list[tuple[str, float, float, int]] = []
        for entry_index, entry in enumerate(entries):
            try:
                start, end = map(float, entry['timestamp'])
                entry_tokens = tokens(str(entry.get('text') or ''))
            except (KeyError, TypeError, ValueError):
                return None, 'invalid_timing'
            total_tokens += len(entry_tokens)
            if total_tokens > 20000:
                return None, 'budget_exhausted'
            timeline.extend((token, start, end, entry_index) for token in entry_tokens)
        spoken = [row[0] for row in timeline]
        minimum = math.floor(len(want) * COMPETITOR_RATIO / (2 - COMPETITOR_RATIO))
        maximum = math.ceil(len(want) * (2 - COMPETITOR_RATIO) / COMPETITOR_RATIO)
        wanted_counts = Counter(want)
        # Exhaust every token start. Trigram seeds can omit evenly distributed
        # ASR substitutions in a near-duplicate and cannot prove uniqueness.
        for left in range(len(spoken)):
            if left % 100 == 0 and deadline is not None and time.monotonic() >= deadline:
                return None, 'budget_exhausted'
            counts: Counter[str] = Counter()
            overlap = 0
            for length in range(1, min(maximum, len(spoken) - left) + 1):
                token = spoken[left + length - 1]
                counts[token] += 1
                if counts[token] <= wanted_counts[token]:
                    overlap += 1
                if length < minimum or 2 * overlap / (len(want) + length) < COMPETITOR_RATIO:
                    continue
                right = left + length
                matcher = SequenceMatcher(None, want, spoken[left:right], autojunk=False)
                score = matcher.ratio()
                if score < COMPETITOR_RATIO:
                    continue
                alignment = {
                    block.a + delta: (source, left + block.b + delta)
                    for block in matcher.get_matching_blocks()
                    for delta in range(block.size)
                }
                # A matching subphrase inside coarse text is still a competitor,
                # but does not authorize fabricated word-level cut boundaries.
                if left and timeline[left - 1][3] == timeline[left][3]:
                    invalid_alignments.append(alignment)
                    continue
                if right < len(timeline) and timeline[right - 1][3] == timeline[right][3]:
                    entry_id = timeline[right - 1][3]
                    while right < len(timeline) and timeline[right][3] == entry_id:
                        right += 1
                    # A coarse entry may extend beyond the anchor only when all
                    # its text belongs to the authorized expected utterance.
                    extra = spoken[left:right]
                    aligned = SequenceMatcher(None, full_expected, extra, autojunk=False)
                    if sum(block.size for block in aligned.get_matching_blocks()) / len(extra) < MATCH_RATIO:
                        invalid_alignments.append(alignment)
                        continue
                span = timeline[left:right]
                start, end = span[0][1], span[-1][2]
                valid = (
                    math.isfinite(duration)
                    and duration > 0
                    and all(
                        math.isfinite(a) and math.isfinite(b) and 0 <= a <= b <= duration + 0.02 for _, a, b, _ in span
                    )
                    and all(a[1] <= b[1] for a, b in zip(span, span[1:]))
                    and 0 < end - start <= MAX_MATCH_SECONDS
                )
                # Untimed text still participates as a possible competitor.
                # Bad timing in unrelated text cannot make a valid match unique
                # by discarding a textual candidate.
                if not valid:
                    invalid_alignments.append(alignment)
                    continue
                candidate = TextLocation(source, start, end, score, left)
                same = next((i for i, mapping in enumerate(alignments) if _same_occurrence(mapping, alignment)), None)
                if same is None:
                    matches.append(candidate)
                    alignments.append(alignment)
                elif score > matches[same].score:
                    matches[same] = candidate
                    alignments[same] = alignment
                if len(matches) > 1:
                    return None, 'ambiguous'
    if any(not any(_same_occurrence(bad, good) for good in alignments) for bad in invalid_alignments):
        return None, 'ambiguous' if matches else 'invalid_timing'
    if not matches or matches[0].score < MATCH_RATIO:
        return None, 'not_found'
    return matches[0], 'located'


def _same_occurrence(a: Mapping[int, tuple[int, int]], b: Mapping[int, tuple[int, int]]) -> bool:
    """Only coalesce windows that align shared expected tokens to identical audio.

    Shifted windows of one phrase share this mapping; repeated occurrences map
    the same expected tokens to different source positions and stay competitors.
    """
    shared = a.keys() & b.keys()
    return len(shared) >= MIN_ANCHOR_TOKENS // 2 and all(a[index] == b[index] for index in shared)
