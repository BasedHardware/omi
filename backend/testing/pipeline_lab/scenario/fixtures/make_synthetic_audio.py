"""Regenerate the committed synthetic speech fixture and its ``synthetic`` STT cassette (macOS only).

    cd backend && python -m testing.pipeline_lab.scenario.fixtures.make_synthetic_audio

Speech comes from macOS ``say`` (two stock voices, one per speaker), converted to 16 kHz mono PCM16 with
``afconvert``; each line is trimmed of its edge silence and the lines are joined with fixed pauses. The
cassette's words are the script's own words, spread across each line's measured span in proportion to
their length: hand-made timings, so the cassette is ``synthetic``, not a recognizer's output. ``say``
output can differ across macOS versions, so the WAV and the cassette are always regenerated together
(the cassette is keyed on the WAV's exact samples).

The text is obviously synthetic and names no one.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import wave

from testing.pipeline_lab.cassette.format import (
    BYTES_PER_SECOND,
    SAMPLE_RATE,
    Cassette,
    CassetteKey,
    Word,
    derive_segments,
)

HERE = Path(__file__).resolve().parent
WAV = HERE / 'audio' / 'synthetic_two_voices.wav'
CASSETTES = HERE / 'stt_cassette'
PROVIDER, MODEL, LANGUAGE = 'synthetic', 'macos-say-script-v1', 'en'
RATE_WPM = 220
PAUSE_SECONDS = 0.35
LEAD_SECONDS = 0.25
SCRIPT = (
    ('Fred', 'SPEAKER_00', 'This is a synthetic test recording for the pipeline lab.'),
    ('Karen', 'SPEAKER_01', 'Lantern harbor maple pebble orchard canvas meadow copper.'),
    ('Fred', 'SPEAKER_00', 'Willow saffron beacon, the synthetic sample ends here.'),
)
SILENCE = 300  # PCM16 amplitude below which an edge sample counts as silence


def _say(voice: str, text: str, work: Path) -> bytes:
    aiff, wav = work / 'line.aiff', work / 'line.wav'
    subprocess.run(['say', '-v', voice, '-r', str(RATE_WPM), '-o', str(aiff), text], check=True)
    subprocess.run(
        ['afconvert', '-f', 'WAVE', '-d', f'LEI16@{SAMPLE_RATE}', '-c', '1', str(aiff), str(wav)], check=True
    )
    with wave.open(str(wav), 'rb') as handle:
        return handle.readframes(handle.getnframes())


def _trim(pcm: bytes) -> bytes:
    import array

    samples = array.array('h', pcm)
    loud = [i for i, value in enumerate(samples) if abs(value) > SILENCE]
    return samples[loud[0] : loud[-1] + 1].tobytes() if loud else b''


def _words(text: str, start: float, end: float, speaker: str) -> list[Word]:
    tokens = text.split()
    weights = [len(token) + 1 for token in tokens]
    total, at, out = sum(weights), start, []
    for token, weight in zip(tokens, weights):
        span = (end - start) * weight / total
        out.append(Word(round(at, 3), round(at + span * 0.9, 3), token, speaker))
        at += span
    return out


def build() -> tuple[bytes, Cassette]:
    pause = b'\x00\x00' * int(PAUSE_SECONDS * SAMPLE_RATE)
    pcm = b'\x00\x00' * int(LEAD_SECONDS * SAMPLE_RATE)
    words: list[Word] = []
    with tempfile.TemporaryDirectory() as tmp:
        for voice, speaker, text in SCRIPT:
            line = _trim(_say(voice, text, Path(tmp)))
            start = len(pcm) / BYTES_PER_SECOND
            pcm += line
            words += _words(text, start, len(pcm) / BYTES_PER_SECOND, speaker)
            pcm += pause
    key = CassetteKey.for_audio(pcm, provider=PROVIDER, model=MODEL, language=LANGUAGE, vocabulary=[])
    cassette = Cassette(
        key=key,
        audio_seconds=len(pcm) / BYTES_PER_SECOND,
        words=words,
        detected_language=LANGUAGE,
        served_provider=PROVIDER,
        served_model=MODEL,
        adapter='synthetic_script',
        recorded_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        segments=derive_segments(words),
        source='synthetic',
    )
    return pcm, cassette


def main() -> int:
    pcm, cassette = build()
    WAV.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(WAV), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm)
    for old in CASSETTES.glob('*/*.json'):
        old.unlink()
    digest = cassette.key.digest
    path = CASSETTES / digest[:2] / f'{digest}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cassette.to_json(), indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'wav': WAV.name, 'bytes': WAV.stat().st_size, 'seconds': round(cassette.audio_seconds, 3),
                      'words': len(cassette.words), 'cassette': digest[:12]}))  # fmt: skip
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
