"""Pipeline lab STT cassettes: ``source`` (vendor | local | synthetic), the by-audio index, word confidence,
and the local recorder interface with its Parakeet implementation (fake model; no torch, NeMo or network)."""

import json
import re
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from testing.pipeline_lab.cassette import local, local_parakeet
from testing.pipeline_lab.cassette.adapters import StubAdapter
from testing.pipeline_lab.cassette.format import (
    SCHEMA,
    Cassette,
    CassetteKey,
    Word,
    index_path,
    load,
    recorded_for_audio,
)
from testing.pipeline_lab.cassette.local import (
    LocalAdapter,
    LocalRecorder,
    LocalRecorderNotInstalled,
    LocalWord,
    local_recorder,
    register_local_recorder,
)
from testing.pipeline_lab.cassette.recorder import InMemoryLedger, Recorder

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_registered_recorder(monkeypatch):
    monkeypatch.delenv(local.LOCAL_STT_ENV, raising=False)
    monkeypatch.delenv(local_parakeet.PYTHON_ENV, raising=False)
    register_local_recorder(None)
    yield
    register_local_recorder(None)


def pcm(seconds, seed=0):
    return np.random.default_rng(seed).normal(0, 2000, int(16000 * seconds)).astype('<i2').tobytes()


def key(audio, provider='stub', model='stub-1'):
    return CassetteKey.for_audio(audio, provider=provider, model=model, language='en', vocabulary=[])


# ---- source -----------------------------------------------------------------------------------------


def test_cassette_without_source_reads_as_vendor():
    audio = pcm(1)
    value = Cassette(key(audio), 1.0, [Word(0.1, 0.4, 'w')]).to_json()
    del value['source']
    assert Cassette.from_json(value).source == 'vendor'


@pytest.mark.parametrize('source', ['vendor', 'local', 'synthetic'])
def test_source_round_trips(tmp_path, source):
    audio = pcm(1)
    Cassette(key(audio), 1.0, [Word(0.1, 0.4, 'w')], source=source).save(tmp_path)
    assert load(key(audio), tmp_path).source == source
    assert json.loads(key(audio).path(tmp_path).read_text())['source'] == source


def test_unknown_source_is_refused():
    with pytest.raises(ValueError, match='source must be one of'):
        Cassette(key(pcm(1)), 1.0, [], source='guess')
    value = Cassette(key(pcm(1)), 1.0, []).to_json()
    value['source'] = 'guess'
    with pytest.raises(ValueError):
        Cassette.from_json(value)


def test_recorder_stores_the_adapter_source(tmp_path):
    stub = Recorder(StubAdapter(), InMemoryLedger(1.0), vendor_log=tmp_path / 'v.jsonl', root=tmp_path)
    assert stub.ensure(pcm(1), language='en').source == 'synthetic'

    fake = LocalRecorder('fake_local', 'fake-1', lambda audio, language: [LocalWord(0.1, 0.3, 'w', 'S0', 0.9)])
    rec = Recorder(LocalAdapter(fake), InMemoryLedger(0.0), vendor_log=tmp_path / 'v.jsonl', root=tmp_path)
    cassette = rec.ensure(pcm(1, seed=1), language='en')
    assert cassette.source == 'local' and cassette.usd == 0.0
    assert cassette.words == [Word(0.1, 0.3, 'w', 'S0', 0.9)]
    rows = [json.loads(line) for line in (tmp_path / 'v.jsonl').read_text().splitlines()]
    assert rows[-1]['destination'].startswith('local model fake_local:fake-1') and rows[-1]['usd'] == 0


def test_word_confidence_is_stored_only_when_given(tmp_path):
    audio = pcm(1)
    Cassette(key(audio), 1.0, [Word(0.1, 0.2, 'a'), Word(0.3, 0.4, 'b', None, 0.5)]).save(tmp_path)
    raw = json.loads(key(audio).path(tmp_path).read_text())
    assert 'confidence' not in raw['words'][0] and raw['words'][1]['confidence'] == 0.5
    assert load(key(audio), tmp_path).words[1].shifted(1.0).confidence == 0.5
    assert raw['schema'] == SCHEMA


# ---- by-audio index -----------------------------------------------------------------------------------


def test_index_lists_every_cassette_of_one_audio(tmp_path):
    audio, other = pcm(1), pcm(1, seed=9)
    Cassette(key(audio, 'a', 'm'), 1.0, [], source='local').save(tmp_path)
    Cassette(key(audio, 'b', 'm'), 1.0, [], source='vendor').save(tmp_path)
    Cassette(key(audio, 'b', 'm'), 1.0, [], source='vendor').save(tmp_path)  # re-saved: listed once
    Cassette(key(other, 'a', 'm'), 1.0, []).save(tmp_path)
    found = recorded_for_audio(key(audio).audio_sha256, tmp_path)
    assert sorted(c.key.provider for c in found) == ['a', 'b']
    row = json.loads(index_path(key(audio).audio_sha256, tmp_path).read_text().splitlines()[0])
    assert set(row) >= {'provider', 'model', 'audio_sha256', 'key_digest', 'source'} and 'words' not in row


def test_index_skips_cassettes_no_longer_on_disk(tmp_path):
    audio = pcm(1)
    Cassette(key(audio), 1.0, []).save(tmp_path)
    key(audio).path(tmp_path).unlink()
    assert recorded_for_audio(key(audio).audio_sha256, tmp_path) == []


# ---- local recorder interface -------------------------------------------------------------------------


def test_registered_recorder_wins():
    fake = LocalRecorder('p', 'm', lambda audio, language: [])
    register_local_recorder(fake)
    assert local_recorder() is fake


def test_env_factory_is_loaded(monkeypatch):
    module = types.ModuleType('plab_fake_local_stt')
    module.factory = lambda: LocalRecorder(
        'env_local', 'e-1', lambda audio, language: [{'start': 0, 'end': 1, 'text': 'x'}]
    )
    monkeypatch.setitem(sys.modules, 'plab_fake_local_stt', module)
    monkeypatch.setenv(local.LOCAL_STT_ENV, 'plab_fake_local_stt:factory')
    recorder = local_recorder()
    assert recorder.provider == 'env_local'
    words = LocalAdapter(recorder).transcribe(local.STTRequest(pcm(1), 'en')).words
    assert words == [Word(0.0, 1.0, 'x')]


@pytest.mark.parametrize('spec', ['nocolon', 'no_such_module_xyz:factory'])
def test_bad_env_factory_is_a_clear_error(monkeypatch, spec):
    monkeypatch.setenv(local.LOCAL_STT_ENV, spec)
    with pytest.raises(LocalRecorderNotInstalled, match=local.LOCAL_STT_ENV):
        local_recorder()


def test_local_word_needs_start_end_and_text():
    bad = LocalRecorder('p', 'm', lambda audio, language: [{'start': 0, 'text': 'x'}])
    with pytest.raises(ValueError, match='start, end and text'):
        LocalAdapter(bad).transcribe(local.STTRequest(pcm(1), None))


def test_not_installed_default_explains_how_to_install():
    with pytest.raises(LocalRecorderNotInstalled, match='optional extra'):
        local.NOT_INSTALLED.recognize(b'', None)


# ---- local Parakeet -----------------------------------------------------------------------------------


def test_parakeet_key_is_its_own_and_pins_production_revision():
    revision = local_parakeet.asr_revision()
    source = (BACKEND / 'diarizer' / 'batch_pipeline_startup.py').read_text()
    assert re.search(rf"^ASR_REVISION = '{revision}'", source, re.M)
    model = local_parakeet.model_key(revision)
    assert model == f'parakeet-tdt-0.6b-v3@{revision[:8]}/cpu-fp32'
    assert local_parakeet.PROVIDER == 'parakeet_local' != 'parakeet'


def test_parakeet_module_imports_no_model_stack():
    assert 'nemo' not in sys.modules and 'diarizer.batch_pipeline_models' not in sys.modules


def test_default_recorder_without_the_extra_is_not_installed(monkeypatch):
    monkeypatch.setattr(local_parakeet, '_has_extra', lambda: False)
    recorder = local_recorder()
    assert (recorder.provider, recorder.installed) == ('parakeet_local', False)
    with pytest.raises(LocalRecorderNotInstalled, match='requirements-local-stt.txt'):
        recorder.recognize(pcm(1), 'en')


def test_named_worker_python_must_exist(monkeypatch, tmp_path):
    monkeypatch.setenv(local_parakeet.PYTHON_ENV, str(tmp_path / 'missing-python'))
    recorder = local_parakeet.recorder()
    assert not recorder.installed
    with pytest.raises(LocalRecorderNotInstalled, match='not an executable interpreter'):
        recorder.recognize(pcm(1), 'en')


class FakeParakeetWords:
    """``ParakeetWords.transcribe_batch`` shape: per window, ``[{word, timestamp: [s, e]}]``."""

    def __init__(self):
        self.windows = []

    def transcribe_batch(self, samples):
        self.windows.append(len(samples[0]) / 16000)
        return [[{'word': f'w{len(self.windows)}', 'timestamp': [0.5, 0.9]}]]


def test_parakeet_windows_like_the_batch_adapter_and_shifts_words():
    fake = FakeParakeetWords()
    engine = local_parakeet.ParakeetCPU('r' * 40, load=lambda revision: fake)
    words = local_parakeet.transcribe_pcm(pcm(70), 'en', engine=engine)
    assert fake.windows == [30.0, 30.0, 10.0]
    assert [(w.start, w.end, w.text, w.speaker) for w in words] == [
        (0.5, 0.9, 'w1', None),
        (30.5, 30.9, 'w2', None),
        (60.5, 60.9, 'w3', None),
    ]


class Done:
    def __init__(self, returncode=0, stderr=''):
        self.returncode, self.stderr = returncode, stderr


def test_worker_round_trip_through_files(tmp_path):
    seen = {}

    def run(command, **kwargs):
        pcm_path = Path(command[command.index('--pcm') + 1])
        seen.update(bytes=pcm_path.stat().st_size, mode=pcm_path.stat().st_mode & 0o777, cwd=kwargs['cwd'])
        out = Path(command[command.index('--out') + 1])
        out.write_text(json.dumps({'revision': 'r' * 40, 'words': [{'start': 0.1, 'end': 0.2, 'text': 'x'}]}))
        return Done()

    words = local_parakeet.Worker('/py', 'r' * 40, run=run)(pcm(2), 'en')
    assert words == [LocalWord(0.1, 0.2, 'x')]
    assert seen == {'bytes': 64000, 'mode': 0o600, 'cwd': local_parakeet.BACKEND}


def test_worker_refuses_a_different_revision_and_reports_missing_deps():
    def other(command, **kwargs):
        Path(command[command.index('--out') + 1]).write_text(json.dumps({'revision': 'x' * 40, 'words': []}))
        return Done()

    with pytest.raises(RuntimeError, match='different revision'):
        local_parakeet.Worker('/py', 'r' * 40, run=other)(pcm(1), None)
    missing = lambda command, **kwargs: Done(1, "ModuleNotFoundError: No module named 'nemo'")  # noqa: E731
    with pytest.raises(LocalRecorderNotInstalled, match='uv pip install'):
        local_parakeet.Worker('/py', 'r' * 40, run=missing)(pcm(1), None)
