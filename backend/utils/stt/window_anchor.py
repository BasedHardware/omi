"""Sentence-anchored growing windows for live TDT.

nvidia/parakeet-tdt-0.6b-v3 returns empty text when a clip starts mid-utterance.
Posting [anchor, now] and re-anchoring at the last *emitted* sentence keeps the
next POST on a sentence boundary — the case the model handles.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

DEFAULT_PACE_SECONDS = 6.0
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
