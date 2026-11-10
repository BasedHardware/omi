"""Small audio and annotation helpers for the quality corpus (public audio only)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    speaker: str


def load_audio(path: Path) -> np.ndarray:
    """Mono float32 at 16 kHz. Resamples with librosa (present in the batch image) when needed."""
    import soundfile as sf

    data, rate = sf.read(str(path), dtype='float32', always_2d=True)
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        import librosa  # batch-pipeline image only

        mono = librosa.resample(mono, orig_sr=rate, target_sr=SAMPLE_RATE)
    return np.ascontiguousarray(mono, dtype=np.float32)


def parse_rttm(text: str, file_id: str | None = None) -> list[Turn]:
    turns = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 8 or parts[0] != 'SPEAKER':
            continue
        if file_id is not None and parts[1] != file_id:
            continue
        start, duration = float(parts[3]), float(parts[4])
        if duration > 0:
            turns.append(Turn(start, start + duration, parts[7]))
    return sorted(turns, key=lambda t: (t.start, t.end, t.speaker))


def parse_ami_words(xml_by_speaker: dict[str, str]) -> list[dict]:
    """AMI NXT ``<meeting>.<X>.words.xml`` -> timed words with the speaker letter.

    Only ``<w>`` elements with both times are kept; punctuation-only tokens are
    dropped (``punc="true"``). Returned sorted by start time.
    """
    words = []
    for speaker, text in xml_by_speaker.items():
        root = ET.fromstring(text)
        for element in root.iter():
            if not element.tag.endswith('w'):
                continue
            start, end = element.get('starttime'), element.get('endtime')
            if start is None or end is None or element.get('punc') == 'true':
                continue
            token = (element.text or '').strip()
            if token:
                words.append({'text': token, 'start': float(start), 'end': float(end), 'speaker': speaker})
    return sorted(words, key=lambda w: (w['start'], w['end']))


def crop_words(words: list[dict], start: float, end: float) -> list[dict]:
    """Midpoint crop and rebase to the crop start (the Oct-15 bench rule)."""
    out = []
    for w in words:
        mid = (w['start'] + w['end']) / 2
        if start <= mid < end:
            out.append({**w, 'start': max(0.0, w['start'] - start), 'end': min(end - start, w['end'] - start)})
    return out


def crop_turns(turns: list[Turn], start: float, end: float) -> list[Turn]:
    return [
        Turn(max(start, t.start) - start, min(end, t.end) - start, t.speaker)
        for t in turns
        if t.end > start and t.start < end
    ]


def quiet_bed(seconds: float, seed: int, dbfs: float = -55.0) -> np.ndarray:
    """Deterministic low-level noise bed imitating wearable capture between utterances."""
    rng = np.random.default_rng(seed)
    amplitude = 10 ** (dbfs / 20.0)
    return (rng.standard_normal(int(seconds * SAMPLE_RATE)) * amplitude).astype(np.float32)


def speaker_at(turns: list[Turn], t: float) -> str | None:
    """Reference speaker at time ``t``; None in gaps or overlap (excluded from scoring)."""
    active = {turn.speaker for turn in turns if turn.start <= t < turn.end}
    return next(iter(active)) if len(active) == 1 else None


def turns_from_words(words: list[dict]) -> list[Turn]:
    return [Turn(w['start'], w['end'], str(w['speaker'])) for w in words if w['end'] > w['start']]


def merge_turns(turns: list[Turn], gap: float = 0.3) -> list[Turn]:
    """Join same-speaker turns separated by at most ``gap`` seconds (word-level RTTM -> utterances)."""
    merged: dict[str, list[Turn]] = {}
    for turn in sorted(turns, key=lambda t: (t.speaker, t.start)):
        rows = merged.setdefault(turn.speaker, [])
        if rows and turn.start - rows[-1].end <= gap:
            rows[-1] = Turn(rows[-1].start, max(rows[-1].end, turn.end), turn.speaker)
        else:
            rows.append(turn)
    return sorted((t for rows in merged.values() for t in rows), key=lambda t: (t.start, t.end, t.speaker))
