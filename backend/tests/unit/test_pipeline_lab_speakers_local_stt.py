"""Local Parakeet recording windows (``cassette/local_parakeet.py``): VAD-packed speech spans are the default,
fixed 30 s windows stay available, and the windowing goes into the cassette key and ``source_detail``.

The engine is a fake with the CPU model's measured failure (2026-11-26, LibriSpeech mix: 38 of 102 words in fixed
windows, 102 of 102 in VAD spans): a window that holds a run of exact digital silence returns no words at all.
No torch, NeMo, model or network."""

from array import array
import json
from pathlib import Path
import subprocess

import pytest

from testing.pipeline_lab.cassette import local, local_parakeet
from testing.pipeline_lab.cassette.format import Word
from testing.pipeline_lab.cassette.local import LocalAdapter, LocalRecorder
from testing.pipeline_lab.cassette.recorder import InMemoryLedger, Recorder

RATE = 16000
SILENCE_RUN = RATE // 4  # 0.25 s of exact zeros poisons a whole window for the fake engine


def _speech(seconds: float) -> array:
    """Synthetic 'speech': a never-zero square-ish wave."""
    return array('h', ((800 if (i // 40) % 2 else -800) for i in range(int(seconds * RATE))))


def _mix(layout):
    """``[(kind, seconds)]`` -> PCM16 bytes and the speech spans (seconds)."""
    samples, spans, at = array('h'), [], 0.0
    for kind, seconds in layout:
        if kind == 'speech':
            samples.extend(_speech(seconds))
            spans.append({'start': at, 'end': at + seconds})
        else:
            samples.extend(array('h', bytes(int(seconds * RATE) * 2)))
        at += seconds
    return samples.tobytes(), spans


class FakeEngine:
    """One word per whole second of speech in the window, unless the window holds an exact-zero run."""

    def __init__(self):
        self.windows = []

    def window(self, chunk: bytes, language):
        samples = array('h')
        samples.frombytes(chunk)
        self.windows.append(len(samples) / RATE)
        run = longest = 0
        for value in samples:
            run = run + 1 if value == 0 else 0
            longest = max(longest, run)
        if longest >= SILENCE_RUN:
            return [], None
        speech = sum(1 for value in samples if value != 0) / RATE
        return [Word(float(i), float(i) + 0.5, f'w{i}') for i in range(int(speech))], None


# 60 s: turns separated by exact digital silence for the first 30 s window, continuous speech in the second.
LAYOUT = [('speech', 6), ('gap', 1.5)] * 4 + [('speech', 30)]


@pytest.fixture()
def mix():
    return _mix(LAYOUT)


def test_fixed_windows_lose_the_words_of_a_window_with_digital_silence_and_vad_spans_recover_them(mix):
    pcm, spans = mix
    fixed = local_parakeet.transcribe(pcm, 'en', engine=FakeEngine(), windows='fixed')
    assert len(fixed) == 30  # the first window holds the gaps: its 24 words are gone; the second gives 30
    engine = FakeEngine()
    words = local_parakeet.transcribe(pcm, 'en', engine=engine, windows='vad', vad=lambda _: spans)
    assert len(words) == 53  # 4 x 6 from the turns, 29 from the 29.8 s window of the long one (its tail is 0.2 s)
    # Words are on the recording clock, inside their own span (pad included).
    assert all(any(s['start'] - 0.2 <= w.start < s['end'] + 0.2 for s in spans) for w in words)
    assert max(engine.windows) <= local_parakeet.WINDOW_SECONDS


def test_speech_windows_pack_close_spans_and_split_long_ones():
    pcm = bytes(int(100 * RATE) * 2)
    spans = [{'start': 1.0, 'end': 3.0}, {'start': 3.2, 'end': 5.0}, {'start': 10.0, 'end': 75.0}]
    windows = local_parakeet.speech_windows(pcm, segments=lambda _: spans)
    assert windows[0] == [0.8, 5.2]  # joined across a 0.2 s pause, padded
    assert all(end - start <= local_parakeet.WINDOW_SECONDS + 1e-9 for start, end in windows)
    assert windows[1][0] == 9.8 and windows[-1][1] == 75.2


def test_model_key_and_source_detail_name_the_windowing():
    revision = local_parakeet.asr_revision()
    assert local_parakeet.model_key(revision, 'fixed') == f'parakeet-tdt-0.6b-v3@{revision[:8]}/cpu-fp32'
    assert local_parakeet.model_key(revision, 'vad').endswith('/cpu-fp32/vad')
    vad = local_parakeet.windowing_detail('vad')
    assert vad['windows'] == 'vad' and {'model', 'max_seconds', 'join_gap', 'pad'} <= set(vad['vad'])
    assert local_parakeet.windowing_detail('fixed') == {'windows': 'fixed', 'window_seconds': 30.0}
    with pytest.raises(ValueError):
        local_parakeet.model_key(revision, 'other')


def test_recorder_defaults_to_vad_spans(monkeypatch, tmp_path):
    python = tmp_path / 'python'
    python.write_text('#!/bin/sh\n')
    python.chmod(0o755)
    monkeypatch.delenv(local.LOCAL_STT_ENV, raising=False)
    monkeypatch.setenv(local_parakeet.PYTHON_ENV, str(python))
    default = local.local_recorder()
    assert default.model.endswith('/vad') and default.detail['windows'] == 'vad'
    assert default.recognize.windows == 'vad'
    fixed = local.local_recorder('fixed')
    assert not fixed.model.endswith('/vad') and fixed.detail['windows'] == 'fixed'


def test_worker_sends_vad_spans_to_the_model_process(tmp_path, mix):
    pcm, spans = mix
    sent = {}

    def run(command, **kwargs):
        sent['spans'] = json.loads(Path(command[command.index('--spans') + 1]).read_text())
        out = Path(command[command.index('--out') + 1])
        out.write_text(json.dumps({'revision': revision, 'words': [{'start': 1.0, 'end': 1.5, 'text': 'w'}]}))
        return subprocess.CompletedProcess(command, 0, '', '')

    revision = local_parakeet.asr_revision()
    (tmp_path / 'work').mkdir(mode=0o700)
    worker = local_parakeet.Worker(
        'python', revision, run=run, work_root=tmp_path / 'work', windows='vad', vad=lambda _: spans
    )
    words = worker(pcm, 'en')
    assert len(words) == 1 and sent['spans'] == local_parakeet.speech_windows(pcm, segments=lambda _: spans)
    silent = local_parakeet.Worker(
        'python', revision, run=run, work_root=tmp_path / 'work', windows='vad', vad=lambda _: []
    )
    assert silent(pcm, 'en') == []  # no speech: the model process is not started


def test_recorded_cassette_carries_the_windowing_in_source_detail(tmp_path, mix):
    pcm, spans = mix
    engine = FakeEngine()
    detail = local_parakeet.windowing_detail('vad')

    def recognize(audio, language):
        return local_parakeet.transcribe(audio, language, engine=engine, windows='vad', vad=lambda _: spans)

    recorder = LocalRecorder('parakeet_local', 'fake/vad', recognize, detail=detail)
    (tmp_path / 'root').mkdir(mode=0o700)
    rec = Recorder(
        LocalAdapter(recorder), InMemoryLedger(0.0), vendor_log=tmp_path / 'vendor.jsonl', root=tmp_path / 'root'
    )
    cassette = rec.ensure(pcm, language='en')
    assert cassette.source == 'local' and cassette.source_detail == detail and len(cassette.words) == 53
    stored = json.loads(cassette.key.path(tmp_path / 'root').read_text())
    assert stored['source_detail'] == detail
    from testing.pipeline_lab.cassette.format import Cassette

    assert Cassette.from_json(stored).source_detail == detail


def test_padded_speech_windows_never_overlap_near_the_packing_limit():
    from testing.pipeline_lab.cassette.local_parakeet import speech_windows

    spans = [{'start': 0.0, 'end': 29.696}, {'start': 29.824, 'end': 31.008}]
    windows = speech_windows(b'\0\0' * 16000 * 32, segments=lambda pcm: spans)
    assert all(a[1] <= b[0] for a, b in zip(windows, windows[1:])), windows
    assert windows[0][0] == 0.0 and windows[-1][1] >= 31.008
