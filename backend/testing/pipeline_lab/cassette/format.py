"""STT cassette: one recorded vendor transcription of one exact stretch of audio.

DESIGN L2: cold STT is a separate ``record`` step per (audio stretch, provider,
model, language, vocabulary); every later run plays the cassette. The key is
the hash of those five values, where the audio hash is taken over canonical
16 kHz mono PCM16LE samples (so a container or codec change of the same audio
does not miss).

Content is vendor words and derived segments in *audio-offset* seconds (0 =
first sample of the stretch), each with the vendor's speaker label. Words keep
the vendor's own clocks so production post-processing runs on play, not here.

Location: ``$ROOT/cache/stt_cassette/<kk>/<key>.json`` (the DESIGN cache layout
with ``stt_cassette`` as the stage name). Cassettes hold transcripts, so they
live only under the private lab root, never in git.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from testing.pipeline_lab.store import atomic_write_json, lab_root, read_json

SCHEMA = 'pipeline_lab.stt_cassette/v1'
STAGE_DIR = 'stt_cassette'
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2


def audio_sha256(pcm16: bytes) -> str:
    """Hash of canonical 16 kHz mono PCM16LE bytes."""
    return hashlib.sha256(pcm16).hexdigest()


def vocabulary_sha256(vocabulary: Sequence[str] | None) -> str:
    """Order-preserving: production sends the list in order (``["Omi", *user_vocab]``)."""
    return hashlib.sha256(json.dumps(list(vocabulary or []), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class CassetteKey:
    provider: str
    model: str
    language: str
    vocabulary_sha256: str
    audio_sha256: str

    @classmethod
    def for_audio(
        cls, pcm16: bytes, *, provider: str, model: str, language: str | None, vocabulary: Sequence[str] | None
    ) -> 'CassetteKey':
        return cls(provider, model, language or 'multi', vocabulary_sha256(vocabulary), audio_sha256(pcm16))

    @property
    def digest(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def path(self, root=None) -> Path:
        digest = self.digest
        return lab_root(root) / 'cache' / STAGE_DIR / digest[:2] / f'{digest}.json'


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    speaker: str | None = None

    def shifted(self, offset: float) -> 'Word':
        return Word(self.start + offset, self.end + offset, self.text, self.speaker)

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2


@dataclass
class Cassette:
    key: CassetteKey
    audio_seconds: float
    words: list[Word]
    detected_language: str | None = None
    served_provider: str | None = None
    served_model: str | None = None
    adapter: str = ''
    recorded_at: str = ''
    usd: float = 0.0
    segments: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            'schema': SCHEMA,
            'key': asdict(self.key),
            'key_digest': self.key.digest,
            'audio': {'seconds': self.audio_seconds, 'sample_rate': SAMPLE_RATE, 'format': 'pcm16le_mono'},
            'adapter': self.adapter,
            'recorded_at': self.recorded_at,
            'served': {'provider': self.served_provider, 'model': self.served_model},
            'detected_language': self.detected_language,
            'usd': self.usd,
            'words': [asdict(w) for w in self.words],
            'segments': self.segments or derive_segments(self.words),
        }

    @classmethod
    def from_json(cls, value: dict) -> 'Cassette':
        if value.get('schema') != SCHEMA:
            raise ValueError('not an STT cassette')
        key = CassetteKey(**value['key'])
        if value.get('key_digest') not in (None, key.digest):
            raise ValueError('cassette key digest mismatch')
        served = value.get('served') or {}
        return cls(
            key=key,
            audio_seconds=float(value['audio']['seconds']),
            words=[Word(**w) for w in value.get('words') or []],
            detected_language=value.get('detected_language'),
            served_provider=served.get('provider'),
            served_model=served.get('model'),
            adapter=value.get('adapter') or '',
            recorded_at=value.get('recorded_at') or '',
            usd=float(value.get('usd') or 0.0),
            segments=list(value.get('segments') or []),
        )

    def save(self, root=None) -> Path:
        return atomic_write_json(self.key.path(root), self.to_json())

    def words_between(self, start: float, end: float) -> list[Word]:
        """Words whose midpoint lies in [start, end), shifted to start at 0."""
        return [w.shifted(-start) for w in self.words if start <= w.midpoint < end]


def load(key: CassetteKey, root=None) -> Cassette | None:
    value = read_json(key.path(root))
    return Cassette.from_json(value) if value is not None else None


def derive_segments(words: Iterable[Word], *, max_pause: float = 1.0) -> list[dict]:
    """Inspection-only grouping (same speaker, pause <= max_pause).

    Replay drivers never use this; they run production post-processing over
    ``words``. It exists so a cassette is readable on its own.
    """
    segments: list[dict] = []
    for word in words:
        last = segments[-1] if segments else None
        if last and last['speaker'] == word.speaker and word.start - last['end'] <= max_pause:
            last['end'] = max(last['end'], word.end)
            last['text'] = f"{last['text']} {word.text}".strip()
        else:
            segments.append({'start': word.start, 'end': word.end, 'speaker': word.speaker, 'text': word.text})
    return segments


def speaker_turns(words: Iterable[Word], *, max_pause: float = 1.0) -> list[dict[str, Any]]:
    """Diarization turns ``{start, end, speaker}`` implied by the vendor's word labels."""
    return [
        {'start': s['start'], 'end': s['end'], 'speaker': s['speaker'] or 'SPEAKER_00'}
        for s in derive_segments(words, max_pause=max_pause)
    ]
