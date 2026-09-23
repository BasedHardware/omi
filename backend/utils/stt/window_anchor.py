"""Sentence-anchored growing windows for live TDT.

nvidia/parakeet-tdt-0.6b-v3 returns empty text when a clip starts mid-utterance.
Posting [anchor, now] and re-anchoring at the last *emitted* sentence keeps the
next POST on a sentence boundary — the case the model handles.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

# Pace is how much NEW audio must accumulate before the next POST, and it is what
# should decide window size. Left at 6s, window size was instead decided by how fast
# the GPU answered: audio keeps arriving while a POST is in flight, so the next window
# spans roughly one POST latency. Measured on dev with identical audio, that produced
# ~7s windows at WER 0.242, ~9-15s at 0.245, and ~24s (the max-context cap) at 0.155.
# Accuracy tracks window size, so a busier GPU transcribed better — which is not a
# property we can ship.
#
# 15s makes windows large without reaching the 24s cap on every post, and removes the
# dependence on server load. It costs first-text latency: the first POST now waits for
# 15s of audio instead of 6s. The configurations that scored 0.155 were already ~27.5s
# to first text, so this is not a new cost, but no latency budget has been stated for
# this leg and that gap is still open.
DEFAULT_PACE_SECONDS = 15.0
DEFAULT_MAX_CONTEXT_SECONDS = 24.0
PACE_MIN_SECONDS = 1.0
PACE_MAX_SECONDS = 15.0
MAX_CONTEXT_MIN_SECONDS = 6.0
MAX_CONTEXT_MAX_SECONDS = 30.0
LEAD_IN_SECONDS = 0.3
SILENCE_FLUSH_SECONDS = 1.5
IDLE_FLUSH_SECONDS = 2.0
TRAILING_COMPLETE_GAP_SECONDS = 1.2
TERMINAL_PUNCTUATION = '.?!'


@dataclass(frozen=True)
class RawSegment:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class WindowDecision:
    emit: tuple[RawSegment, ...]
    new_anchor: float | None
    forced_cut: bool


def clamp_pace_seconds(value: float) -> float:
    return min(PACE_MAX_SECONDS, max(PACE_MIN_SECONDS, value))


def clamp_max_context_seconds(value: float) -> float:
    return min(MAX_CONTEXT_MAX_SECONDS, max(MAX_CONTEXT_MIN_SECONDS, value))


def read_pace_seconds() -> float:
    return _read_clamped('PARAKEET_WINDOW_PACE_SECONDS', DEFAULT_PACE_SECONDS, clamp_pace_seconds)


def read_max_context_seconds() -> float:
    return _read_clamped('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', DEFAULT_MAX_CONTEXT_SECONDS, clamp_max_context_seconds)


def buffer_cap_seconds(pace: float, max_context: float) -> float:
    return 2.0 * max_context + 2.0 * pace


# TDT occasionally falls into a decoding loop on a long window and repeats a short
# phrase in place of the real speech (dev, public earnings clip: "a little bit of"
# six times in one 22.6 s segment). Real speech almost never repeats a 2-6 word
# phrase three or more times back to back, so such a run is collapsed to one copy.
LOOP_MIN_REPEATS = 3
LOOP_MAX_NGRAM = 6


def _loop_key(token: str) -> str:
    return re.sub(r"[^\w']", '', token.lower())


def collapse_decoder_loops(text: str) -> tuple[str, int]:
    """Collapse any 2-6 word phrase repeated 3+ times back to back into one copy."""
    tokens = text.split()
    keys = [_loop_key(t) for t in tokens]
    collapsed = 0
    changed = True
    while changed:
        changed = False
        for n in range(LOOP_MAX_NGRAM, 1, -1):
            i = 0
            while i + 2 * n <= len(keys):
                reps = 1
                while keys[i + reps * n : i + (reps + 1) * n] == keys[i : i + n]:
                    reps += 1
                if reps >= LOOP_MIN_REPEATS and any(keys[i : i + n]):
                    del tokens[i + n : i + reps * n]
                    del keys[i + n : i + reps * n]
                    collapsed += 1
                    changed = True
                i += 1
    return (' '.join(tokens), collapsed) if collapsed else (text, 0)


def is_terminal_sentence(segment: RawSegment) -> bool:
    return segment.text.rstrip()[-1:] in TERMINAL_PUNCTUATION


def is_trailing_complete(segment: RawSegment, duration: float) -> bool:
    if duration - segment.end < TRAILING_COMPLETE_GAP_SECONDS:
        return False
    return is_terminal_sentence(segment)


def parse_tdt_segments(data: dict[str, Any], duration: float) -> list[RawSegment]:
    out: list[RawSegment] = []
    raw: object = data.get('segments', [])
    segments: list[object] = cast(list[object], raw) if isinstance(raw, list) else []
    for item in segments:
        if not isinstance(item, dict):
            continue
        seg: dict[str, Any] = cast(dict[str, Any], item)
        text = str(seg.get('text') or '').strip()
        if not text:
            continue
        start = float(seg.get('start', 0.0))
        end = float(seg.get('end', start))
        out.append(RawSegment(text=text, start=start, end=end))
    if not out:
        text = str(data.get('text') or '').strip()
        if text:
            out.append(RawSegment(text=text, start=0.0, end=duration))
    return out


def decide_window(
    segments: list[RawSegment],
    duration: float,
    max_context: float,
    *,
    force: bool,
    pause: bool = False,
    empty_cap_slide: float = 0.0,
) -> WindowDecision:
    at_cap = duration >= max_context
    if force:
        if not segments:
            return WindowDecision((), duration, forced_cut=False)
        return WindowDecision(tuple(segments), duration, forced_cut=False)
    emit = _held_emit(segments, duration, pause=pause)
    if at_cap:
        if not segments:
            slide = min(max(0.0, empty_cap_slide), duration)
            return WindowDecision((), slide if slide > 0.0 else None, forced_cut=True)
        if len(segments) == 1:
            only = segments[0]
            return WindowDecision((only,), only.end, forced_cut=True)
        new_anchor = emit[-1].end if emit else None
        return WindowDecision(tuple(emit), new_anchor, forced_cut=False)
    if not segments:
        return WindowDecision((), None, forced_cut=False)
    new_anchor = emit[-1].end if emit else None
    return WindowDecision(tuple(emit), new_anchor, forced_cut=False)


def _held_emit(segments: list[RawSegment], duration: float, *, pause: bool) -> list[RawSegment]:
    if not segments:
        return []
    emit = list(segments[:-1])
    last = segments[-1]
    if pause:
        if is_terminal_sentence(last):
            return list(segments)
    elif is_trailing_complete(last, duration):
        return list(segments)
    return emit


def _read_clamped(name: str, default: float, clamp: Callable[[float], float]) -> float:
    raw = os.getenv(name, str(default))
    try:
        return clamp(float(raw))
    except (TypeError, ValueError):
        return default
