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
live only under the private lab root, never in git. The one exception is a
``synthetic`` cassette for a committed synthetic fixture (``scenario/fixtures/``).

``source`` says who produced the words: ``vendor`` (a real provider, through
``record-stt`` or a scenario's ``--stt record-vendor``), ``local`` (a model on
this machine, ``cassette/local.py``) or ``synthetic`` (hand-written or generated
for a fixture). A cassette written before the field existed reads as ``vendor``.

``$ROOT/cache/stt_cassette/by_audio/<aa>/<audio_sha256>.jsonl`` indexes every
cassette saved for one stretch of audio (any provider), so a scenario that does
not pin a provider can find what was recorded for its file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from testing.pipeline_lab.store import append_jsonl, atomic_write_json, lab_root, read_json, read_jsonl

SCHEMA = 'pipeline_lab.stt_cassette/v1'
STAGE_DIR = 'stt_cassette'
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
SOURCES = ('vendor', 'local', 'synthetic')
DEFAULT_SOURCE = 'vendor'  # cassettes recorded before ``source`` existed came from a vendor
INDEX_DIR = 'by_audio'


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
    confidence: float | None = None

    def shifted(self, offset: float) -> 'Word':
        return Word(self.start + offset, self.end + offset, self.text, self.speaker, self.confidence)

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
    source: str = DEFAULT_SOURCE

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(f'cassette source must be one of {SOURCES}, not {self.source!r}')

    def to_json(self) -> dict:
        return {
            'schema': SCHEMA,
            'key': asdict(self.key),
            'key_digest': self.key.digest,
            'audio': {'seconds': self.audio_seconds, 'sample_rate': SAMPLE_RATE, 'format': 'pcm16le_mono'},
            'adapter': self.adapter,
            'source': self.source,
            'recorded_at': self.recorded_at,
            'served': {'provider': self.served_provider, 'model': self.served_model},
            'detected_language': self.detected_language,
            'usd': self.usd,
            'words': [word_json(w) for w in self.words],
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
            source=value.get('source') or DEFAULT_SOURCE,
        )

    def save(self, root=None) -> Path:
        path = atomic_write_json(self.key.path(root), self.to_json())
        append_jsonl(index_path(self.key.audio_sha256, root), [self.index_row()])
        return path

    def index_row(self) -> dict:
        """The by-audio index entry: the key and who produced it (no words)."""
        return {
            **asdict(self.key),
            'key_digest': self.key.digest,
            'source': self.source,
            'recorded_at': self.recorded_at,
        }

    def words_between(self, start: float, end: float) -> list[Word]:
        """Words whose midpoint lies in [start, end), shifted to start at 0."""
        return [w.shifted(-start) for w in self.words if start <= w.midpoint < end]


def word_json(word: Word) -> dict:
    """A word as stored; ``confidence`` only when the producer gave one."""
    value = asdict(word)
    if value['confidence'] is None:
        del value['confidence']
    return value


def load(key: CassetteKey, root=None) -> Cassette | None:
    value = read_json(key.path(root))
    return Cassette.from_json(value) if value is not None else None


def index_path(audio: str, root=None) -> Path:
    return lab_root(root) / 'cache' / STAGE_DIR / INDEX_DIR / audio[:2] / f'{audio}.jsonl'


# The index row that says the one-time scan for cassettes saved before the index ran for this audio. Without
# it, an index holding only cassettes saved since would hide the older ones (``recorded_for_audio``).
BACKFILL_MARKER = {'backfill': 'complete'}


def recorded_for_audio(audio: str, root=None) -> list[Cassette]:
    """Every cassette of this audio hash under ``root`` that is still on disk, oldest first: the indexed ones,
    plus (once per audio, until the index records :data:`BACKFILL_MARKER`) those saved before the index."""
    seen: dict[str, Cassette] = {}
    rows = read_jsonl(index_path(audio, root))
    for row in rows:
        try:
            key = CassetteKey(**{k: row[k] for k in CassetteKey.__dataclass_fields__})
        except (KeyError, TypeError):
            continue
        if key.audio_sha256 != audio or key.digest in seen:
            continue
        cassette = load(key, root)
        if cassette is not None:
            seen[key.digest] = cassette
    if BACKFILL_MARKER not in rows:
        for cassette in _unindexed_for_audio(audio, root, indexed=set(seen)):
            seen.setdefault(cassette.key.digest, cassette)
    return sorted(seen.values(), key=lambda c: (c.recorded_at, c.key.digest))


def _unindexed_for_audio(audio: str, root=None, *, indexed: Iterable[str] = ()) -> list[Cassette]:
    """Cassettes of this audio hash saved before the by-audio index existed (``save`` then wrote only the
    cassette file): a scan of the stored cassettes, oldest first. The index is then backfilled with the ones it
    lacks and :data:`BACKFILL_MARKER`, so the scan runs once per audio, even when the index already had live
    entries saved since (a local cassette recorded after an older, unindexed vendor one)."""
    base = lab_root(root) / 'cache' / STAGE_DIR
    found: list[Cassette] = []
    for path in sorted(base.glob('*/*.json')):
        if path.parent.name == INDEX_DIR:
            continue
        try:
            text = path.read_text(encoding='utf-8')
            if audio not in text:  # cheap filter before parsing a file of words
                continue
            cassette = Cassette.from_json(json.loads(text))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if cassette.key.audio_sha256 == audio and path == cassette.key.path(root):
            found.append(cassette)
    found.sort(key=lambda c: (c.recorded_at, c.key.digest))
    try:  # an optimization only: a root the lab cannot write to still replays (and scans again next time)
        known = set(indexed)
        rows = [c.index_row() for c in found if c.key.digest not in known]
        append_jsonl(index_path(audio, root), [*rows, BACKFILL_MARKER])
    except OSError:
        pass
    return found


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
