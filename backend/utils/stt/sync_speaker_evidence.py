"""Bounded, distinct WAV evidence for batch enrollment verification."""

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass
from typing import Sequence

from utils.stt.speaker_match import SPEAKER_MATCH_MAX_CLIPS

# Preserve sync's existing total eligibility floor; five seconds is a target,
# not permission to discard the short speakers already recognized in production.
SYNC_MIN_EVIDENCE_SECONDS = 1.0
SYNC_CLIP_SECONDS = 10.0


@dataclass(frozen=True)
class SpeakerAudioEvidence:
    clips: list[tuple[bytes, float]]
    available_seconds: float


def collect_speaker_audio(audio: bytes, intervals: Sequence[tuple[float, float]]) -> SpeakerAudioEvidence:
    """Pool longest distinct intervals into <=3 WAVs of <=10s each.

    Clamp to real frames, union overlaps (never count a sample twice), then pack
    longest intervals first. Short turns share a WAV without intervening silence.
    This gives 4x2s one 8s query, while bounding payload and embedding calls. A
    trailing sub-second remainder joins the previous clip by rebalancing frames.
    """
    with wave.open(io.BytesIO(audio), 'rb') as source:
        rate = source.getframerate()
        count = source.getnframes()
        bounds = sorted(
            (max(0, int(start * rate)), min(count, int(end * rate)))
            for start, end in intervals
            if math.isfinite(start) and math.isfinite(end) and end > start
        )
        merged: list[tuple[int, int]] = []
        for start, end in bounds:
            if end <= start:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        available = sum(end - start for start, end in merged)
        if available < rate * SYNC_MIN_EVIDENCE_SECONDS:
            return SpeakerAudioEvidence([], available / rate)
        budget = int(rate * SYNC_CLIP_SECONDS * SPEAKER_MATCH_MAX_CLIPS)
        parts: list[bytes] = []
        for start, end in sorted(merged, key=lambda span: span[1] - span[0], reverse=True):
            frames = min(end - start, budget)
            # Match the old center crop when a long interval exceeds the budget.
            source.setpos(start + (end - start - frames) // 2)
            parts.append(source.readframes(frames))
            budget -= frames
            if budget == 0:
                break
        pcm = b''.join(parts)
        width = source.getsampwidth() * source.getnchannels()
        frames = len(pcm) // width
        clip_count = min(SPEAKER_MATCH_MAX_CLIPS, math.ceil(frames / (rate * SYNC_CLIP_SECONDS)))
        # Equal sizes prevent a tiny tail from carrying equal centroid weight.
        clips: list[tuple[bytes, float]] = []
        for index in range(clip_count):
            start = frames * index // clip_count
            end = frames * (index + 1) // clip_count
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as output:
                output.setparams(source.getparams())
                output.writeframes(pcm[start * width : end * width])
            clips.append((buffer.getvalue(), (end - start) / rate))
    return SpeakerAudioEvidence(clips, available / rate)
