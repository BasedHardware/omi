"""Build the committed public speaker corpus ``speakers/fixtures/public-libri/`` from LibriSpeech dev-clean.

Real human voices with exact truth: each conversation concatenates whole LibriSpeech utterances of known
speakers, so every turn's speaker is known to the sample. Identities are synthetic roles (``owner``,
``person-a``, ...), never the readers' names. Enrollment audio for the owner and the enrolled people comes from
utterances that appear in no conversation.

LibriSpeech (c) 2014 Vassil Panayotov, CC BY 4.0 (https://www.openslr.org/12): the utterances are trimmed,
level-adjusted and concatenated; ``ATTRIBUTION.md`` beside the corpus records the source utterance ids.

    python -m testing.pipeline_lab.speakers.fixtures.make_public_corpus --librispeech <dir>/LibriSpeech

Deterministic: the same dev-clean tree gives byte-identical files. Needs ``ffmpeg`` to decode FLAC. Words are not
written here: ``python -m testing.pipeline_lab.speakers words --corpus public-libri --record-local`` adds them.

The pendant hears its wearer loudest, so the owner's turns are mixed 6 dB above everyone else's. A steady noise
floor (about -50 dBFS) runs under everything: real captures always have one, and the Parakeet batch model returns
no words at all for some windows made of speech and exact digital silence.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from array import array
from pathlib import Path

from testing.pipeline_lab.speakers.corpus import PUBLIC_ROOT
from testing.pipeline_lab.speakers.owner_export import wav_bytes

RATE = 16000
NAME = 'public-libri'

# role -> LibriSpeech dev-clean speaker id (fixed; genders noted for the scenarios that need them)
ROLES = {
    'owner': '1272',  # M
    'person-a': '2035',  # F
    'person-b': '6241',  # M
    'stranger-m': '2078',  # M
    'stranger-f': '3081',  # F
}
ENROLLED = ('owner', 'person-a', 'person-b')
IDENTITY = {'owner': 'user', 'person-a': 'person-a', 'person-b': 'person-b'}

# conversation -> (turn pattern of roles, max seconds per turn, gap seconds range)
CONVERSATIONS = {
    'owner_and_person': (['owner', 'person-a'] * 4, 4.5, (0.3, 0.7)),
    'owner_and_stranger_same_gender': (['owner', 'stranger-m'] * 4, 4.5, (0.3, 0.7)),
    'three_speakers_short_turns': (
        ['owner', 'person-a', 'stranger-m', 'person-a', 'owner', 'stranger-m'] * 2,
        2.5,
        (0.2, 0.5),
    ),
    'owner_monologue': (['owner'] * 6, 5.0, (0.4, 0.9)),
    'owner_absent': (['person-b', 'stranger-f'] * 4, 4.5, (0.3, 0.7)),
}


def _decode(path: Path) -> array:
    raw = subprocess.run(
        ['ffmpeg', '-loglevel', 'error', '-i', str(path), '-f', 's16le', '-ac', '1', '-ar', str(RATE), '-'],
        check=True,
        capture_output=True,
    ).stdout
    samples = array('h')
    samples.frombytes(raw)
    return samples


def _trim(samples: array, threshold: int = 300) -> array:
    """Drop leading/trailing near-silence so gaps are the generator's, not the recording's."""
    frame = RATE // 100
    loud = [i for i in range(0, len(samples) - frame, frame) if max(abs(v) for v in samples[i : i + frame]) > threshold]
    if not loud:
        return samples
    return samples[max(0, loud[0] - frame) : min(len(samples), loud[-1] + 2 * frame)]


def _scale(samples: array, gain: float) -> array:
    return array('h', (max(-32768, min(32767, int(v * gain))) for v in samples))


def _noise_floor(samples: array, rng: random.Random, rms: float = 100.0) -> array:
    return array('h', (max(-32768, min(32767, v + int(rng.gauss(0.0, rms)))) for v in samples))


def _utterances(root: Path, speaker: str) -> list[Path]:
    return sorted((root / 'dev-clean' / speaker).rglob('*.flac'))


class Pool:
    """Hands out each speaker's utterances in order, so no utterance is used twice."""

    def __init__(self, root: Path):
        self.files = {role: _utterances(root, sid) for role, sid in ROLES.items()}
        self.used: list[str] = []

    def take(self, role: str, max_seconds: float) -> array:
        while self.files[role]:
            path = self.files[role].pop(0)
            samples = _trim(_decode(path))
            if len(samples) < RATE:
                continue
            self.used.append(path.stem)
            return samples[: int(max_seconds * RATE)]
        raise RuntimeError(f'out of utterances for {role}')


def build(librispeech: Path, out: Path) -> dict:
    rng = random.Random(20261126)
    pool = Pool(librispeech)
    (out / 'gallery_audio').mkdir(parents=True, exist_ok=True)
    for role in ENROLLED:
        clip = array('h')
        while len(clip) < 8 * RATE:
            clip.extend(pool.take(role, 8.0))
            clip.extend(array('h', bytes(int(0.3 * RATE) * 2)))
        clip = _noise_floor(clip[: 8 * RATE], rng)
        (out / 'gallery_audio' / f'{IDENTITY[role]}.wav').write_bytes(wav_bytes(clip.tobytes()))
    summary = {}
    for name, (pattern, max_turn, (gap_lo, gap_hi)) in CONVERSATIONS.items():
        audio, turns = array('h'), []
        for role in pattern:
            audio.extend(array('h', bytes(int(rng.uniform(gap_lo, gap_hi) * RATE) * 2)))
            samples = _scale(pool.take(role, max_turn), 1.0 if role == 'owner' else 0.5)
            start = len(audio) / RATE
            audio.extend(samples)
            turns.append({'start': round(start, 3), 'end': round(len(audio) / RATE, 3), 'speaker': role})
        audio.extend(array('h', bytes(int(0.5 * RATE) * 2)))
        audio = _noise_floor(audio, rng)
        target = out / 'conversations' / name
        target.mkdir(parents=True, exist_ok=True)
        (target / 'audio.wav').write_bytes(wav_bytes(audio.tobytes()))
        identities = {role: IDENTITY.get(role) for role in sorted(set(pattern))}
        (target / 'truth.json').write_text(
            json.dumps({'kind': 'synthetic', 'turns': turns, 'identities': identities}, indent=1) + '\n'
        )
        summary[name] = {'seconds': round(len(audio) / RATE, 1), 'turns': len(turns), 'speakers': len(identities)}
    manifest = {
        'kind': 'public',
        'source': 'LibriSpeech dev-clean (CC BY 4.0), https://www.openslr.org/12',
        'roles': {role: ('enrolled' if role in ENROLLED else 'not enrolled') for role in ROLES},
        'owner_gain_db': 6,
        'noise_floor_dbfs': -50,
        'conversations': summary,
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n')
    (out / 'ATTRIBUTION.md').write_text(
        'Audio derived from LibriSpeech dev-clean, (c) 2014 Vassil Panayotov, licensed CC BY 4.0 '
        '(https://www.openslr.org/12). Utterances were trimmed, level-adjusted and concatenated by '
        '`make_public_corpus.py`. Source utterances: ' + ', '.join(pool.used) + '.\n'
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--librispeech', required=True, type=Path, help='the extracted LibriSpeech directory')
    parser.add_argument('--out', type=Path, default=PUBLIC_ROOT / NAME)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.librispeech, args.out)['conversations'], indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
