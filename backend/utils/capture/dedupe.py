"""One speaker-independent decision for bridge donors and incoming sync chunks.

Frame receipts and same-scope retry evidence run first. Text is a fallback: an
unambiguous conversation-wide clock estimate only narrows the search, and a
near-identical line must still occupy the same two-second window. Speaker labels
are never evidence that two pieces of speech are the same or different.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Sequence
from difflib import SequenceMatcher
import math
import re
from statistics import median

from config import refactor_modes
from utils.capture.identity import compatible_keys
from utils.capture.frame_proof import evaluate as evaluate_frames
from utils.capture.shadow import compare
from utils.observability.fallback import record_fallback
from utils.sync.capture_repeat_evidence import capture_covered_indices
from utils.sync.live_overlap import compatible_capture
from utils.sync.live_speech_dedupe import drop_proven_exact_retries

FLAG = 'CAPTURE_COVERAGE_MODE'
MAX_SEGMENTS = 4096
MAX_TOKENS = 256
MAX_CHARS = 4096
CLOCK_SEARCH_SECONDS = 90
MATCH_SECONDS = 2


def _tokens(segment: dict) -> tuple[str, ...]:
    text = segment.get('text') or ''
    if not isinstance(text, str) or len(text) > MAX_CHARS:
        return ()
    tokens = tuple(re.findall(r'[^\W_]+', text.casefold()))
    return tokens if len(tokens) <= MAX_TOKENS else ()


def _span(segment: dict) -> tuple[float, float] | None:
    try:
        start = float(segment['timestamp'])
        duration = float(segment['end']) - float(segment['start'])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(start) or not math.isfinite(duration) or duration <= 0:
        return None
    return start, duration


def _windows(segments: list[dict]) -> list[dict]:
    ordered = sorted(
        [(i, segment, span) for i, segment in enumerate(segments) if (span := _span(segment)) is not None],
        key=lambda item: item[2][0],
    )
    windows = []
    for position, (index, segment, span) in enumerate(ordered):
        start, duration = span
        end, tokens, members = start + duration, _tokens(segment), [index]
        if not tokens:
            continue
        windows.append(dict(start=start, duration=duration, tokens=tokens, members=frozenset(members)))
        for next_index, following, following_span in ordered[position + 1 : position + 3]:
            low, length = following_span
            part = _tokens(following)
            if not part or low - end > 2 or low < end - 0.5 or len(tokens) + len(part) > MAX_TOKENS:
                break
            end = max(end, low + length)
            tokens += part
            members.append(next_index)
            windows.append(dict(start=start, duration=end - start, tokens=tokens, members=frozenset(members)))
    return sorted(windows, key=lambda item: item['start'])


def _offset(windows: list[dict], reference: list[dict]) -> float:
    """Estimate once from unique anchors across the whole stored conversation."""
    by_text = defaultdict(list)
    for window in windows:
        if len(window['tokens']) >= 6:
            by_text[window['tokens']].append(window)
    reference_tokens = [_tokens(segment) for segment in reference]
    counts = Counter(reference_tokens)
    anchors, members = [], set()
    for segment, tokens in zip(reference, reference_tokens):
        span = _span(segment)
        if not span or len(tokens) < 6 or counts[tokens] != 1:
            continue
        matches = [w for w in by_text[tokens] if abs(w['start'] - span[0]) <= CLOCK_SEARCH_SECONDS]
        if len(matches) != 1 or members.intersection(matches[0]['members']):
            continue
        anchors.append(matches[0]['start'] - span[0])
        members.update(matches[0]['members'])
    if len(anchors) < 2 or max(anchors) - min(anchors) > MATCH_SECONDS:
        return 0.0
    return median(anchors)


def _similar(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    # Frequent short acknowledgements need frame or retry proof.
    if min(len(left), len(right)) < 4:
        return False
    if min(len(left), len(right)) < 8:
        return left == right
    # Preserve changed numbers and negation even in otherwise similar speech.
    protected = lambda tokens: {
        token for token in tokens if any(c.isdigit() for c in token) or token in {'no', 'not', 'never'}
    }
    return protected(left) == protected(right) and SequenceMatcher(None, left, right, autojunk=False).ratio() >= 0.9


def _reference_segments(rows: Sequence[dict], reference_row: dict, incoming: list[dict]) -> list[dict]:
    references = []
    for row in rows:
        if row.get('id') == reference_row.get('id') or not compatible_capture(row, reference_row):
            continue
        if not compatible_keys(row, reference_row):
            continue
        origin = row['started_at'].timestamp()
        references.extend(
            dict(segment, timestamp=origin + segment['start']) for segment in row.get('transcript_segments') or []
        )
        if len(references) > MAX_SEGMENTS:
            return incoming
    return references + incoming


def dedupe_segments(
    existing: list[dict],
    incoming: list[dict],
    *,
    incoming_row: dict,
    reference_row: dict,
    conversation_rows: Sequence[dict] = (),
    proof=capture_covered_indices,
) -> list[dict]:
    """Keep input objects intact so assignment can acknowledge exact input indices."""
    if not existing or len(existing) > MAX_SEGMENTS or len(incoming) > MAX_SEGMENTS:
        return list(incoming)
    if not compatible_capture(reference_row, incoming_row) or not compatible_keys(reference_row, incoming_row):
        return list(incoming)
    verified = proof(incoming, incoming_row.get('capture_evidence'), reference_row.get('capture_evidence'))
    frame_verified, positioned = evaluate_frames(incoming, incoming_row, [reference_row, *conversation_rows])
    verified |= frame_verified
    positioned_ids = {id(segment) for i, segment in enumerate(incoming) if i in positioned}
    # Source-frame coverage is authoritative. Same-scope retry proofs are also
    # preserved; neither path consults is_user, person_id, or provider speaker IDs.
    survivors, _, _ = drop_proven_exact_retries(
        [(i, segment) for i, segment in enumerate(incoming) if i not in verified and i not in positioned],
        existing,
    )
    retry_kept = {id(segment) for segment in survivors}
    survivors = [
        segment
        for i, segment in enumerate(incoming)
        if i not in verified and (i in positioned or id(segment) in retry_kept)
    ]
    windows = _windows(existing)
    starts = [window['start'] for window in windows]
    offset = _offset(windows, _reference_segments(conversation_rows, reference_row, incoming))
    consumed, kept = set(), []
    for segment in survivors:
        span, tokens = _span(segment), _tokens(segment)
        if not span or id(segment) in positioned_ids:
            kept.append(segment)
            continue
        target = span[0] + offset
        candidates = windows[bisect_left(starts, target - MATCH_SECONDS) : bisect_right(starts, target + MATCH_SECONDS)]
        matches = [
            window
            for window in candidates
            if not consumed.intersection(window['members'])
            and abs(span[1] - window['duration']) / max(span[1], window['duration']) <= 0.25
            and _similar(tokens, window['tokens'])
        ]
        if not matches:
            kept.append(segment)
            continue
        match = min(matches, key=lambda window: abs(window['start'] - target))
        consumed.update(match['members'])
    return kept


def choose_segments(
    uid: str, path: str, existing: list[dict], incoming: list[dict], legacy: list[dict], **kwargs
) -> list[dict]:
    if not refactor_modes.shadow_or_serve(FLAG):
        return legacy
    try:
        proposed = dedupe_segments(existing, incoming, **kwargs)
    except Exception:
        compare(path, 'error')
        record_fallback(
            component='sync_dispatch', from_mode='capture_dedupe', to_mode='legacy', reason='other', outcome='degraded'
        )
        return legacy
    compare(path, 'agree' if [id(s) for s in proposed] == [id(s) for s in legacy] else 'disagree')
    return proposed if refactor_modes.serving_for(FLAG, uid) else legacy
