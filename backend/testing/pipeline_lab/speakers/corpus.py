"""Speaker corpora: audio plus everything a speaker experiment needs, one directory per conversation.

Two kinds share one layout. **Public** corpora are committed under ``speakers/fixtures/<name>/`` (synthetic or
openly licensed audio, synthetic identities); **private** corpora live under the owner-only lab root at
``<lab root>/speakers/corpus/<name>/`` and never enter Git (``owner_export.py`` writes them).

::

    <corpus>/manifest.json                    kind (public|owner), counts, provenance
    <corpus>/gallery.json                     {identity: voiceprint}; ``user`` is the owner (optional)
    <corpus>/gallery_audio/<identity>.wav     enrollment audio, embedded through the peer instead (optional)
    <corpus>/people.json                      [{id, name}] (optional)
    <corpus>/conversations/<key>/audio.wav    16 kHz mono PCM16; every clock below is seconds on this file
    <corpus>/conversations/<key>/words.json   {"source", "model", "words": [{start, end, text}]}
    <corpus>/conversations/<key>/truth.json   {"kind": gold|silver|synthetic, "turns": [{start, end, speaker}],
                                               "identities": {speaker: "user"|person id|null}}
    <corpus>/conversations/<key>/conversation.json
                                              production's stored labels (owner corpora): segments with
                                              ``start``/``end`` on the stored clock and ``segment_clock_offset``

``words.json`` is derived (local Parakeet, cached like an STT cassette); ``truth.json`` is written by a person
(gold), by ``truth.py`` (silver) or by the generator (synthetic). A conversation without truth is still useful:
the bench reports agreement with production and label stability, never accuracy, for it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional
import wave
from testing.pipeline_lab.scenario.paths import private_lab_root
from testing.pipeline_lab.store import ensure_private_dir
from testing.pipeline_lab.store import atomic_write_json

PUBLIC_ROOT = Path(__file__).resolve().parent / 'fixtures'
SAMPLE_RATE = 16000


def private_corpus_root() -> Path:

    return ensure_private_dir(ensure_private_dir(private_lab_root() / 'speakers') / 'corpus')


def corpus_dir(name: str, *, create: bool = False) -> Path:
    """A committed public corpus by name, else the private one (created owner-only when ``create``)."""
    if not name or '/' in name or name.startswith('.'):
        raise ValueError(f'invalid corpus name: {name!r}')
    public = PUBLIC_ROOT / name
    if public.is_dir() and not create:
        return public
    root = private_corpus_root() / name
    if create:

        return ensure_private_dir(root)
    if not root.is_dir():
        raise FileNotFoundError(f'no speaker corpus named {name!r} (public {public} or private {root})')
    return root


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), 'rb') as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, SAMPLE_RATE):
            raise ValueError(f'{path.name}: expected 16 kHz mono PCM16')
        return handle.readframes(handle.getnframes())


def _json(path: Path) -> Any:
    return json.loads(path.read_text()) if path.is_file() else None


@dataclass
class Conversation:
    key: str
    path: Path
    words: Optional[dict] = None
    truth: Optional[dict] = None
    production: Optional[dict] = None
    scenario: Optional[dict] = None

    @property
    def audio_path(self) -> Path:
        return self.path / 'audio.wav'

    def pcm(self) -> bytes:
        return read_pcm(self.audio_path)

    @property
    def seconds(self) -> float:
        return self.audio_path.stat().st_size / (2 * SAMPLE_RATE)


@dataclass
class Corpus:
    name: str
    path: Path
    manifest: dict = field(default_factory=dict)
    gallery: dict = field(default_factory=dict)
    people: list = field(default_factory=list)

    @property
    def public(self) -> bool:
        return PUBLIC_ROOT in self.path.parents

    def conversations(self, keys: Optional[list[str]] = None) -> Iterator[Conversation]:
        root = self.path / 'conversations'
        names = sorted(p.name for p in root.iterdir() if (p / 'audio.wav').is_file()) if root.is_dir() else []
        for key in names:
            if keys and key not in keys:
                continue
            path = root / key
            yield Conversation(
                key=key,
                path=path,
                words=_json(path / 'words.json'),
                truth=_json(path / 'truth.json'),
                production=_json(path / 'conversation.json'),
                scenario=_json(path / 'scenario.json'),
            )

    def gallery_audio(self) -> dict[str, Path]:
        root = self.path / 'gallery_audio'
        return {p.stem: p for p in sorted(root.glob('*.wav'))} if root.is_dir() else {}


def load(name: str) -> Corpus:
    path = corpus_dir(name)
    return Corpus(
        name=name,
        path=path,
        manifest=_json(path / 'manifest.json') or {},
        gallery=_json(path / 'gallery.json') or {},
        people=_json(path / 'people.json') or [],
    )


def write_json(path: Path, value: Any, *, private: bool) -> None:
    if private:

        atomic_write_json(path, value)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + '\n')
