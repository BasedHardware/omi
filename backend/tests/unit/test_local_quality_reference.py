"""Synthetic reproducibility contracts for local model references, never truth."""

import json
from pathlib import Path
import types
import sys

import pytest

from scripts.diarization_eval import run_reference as reference
from scripts.diarization_eval.run_local import reference_text


def test_cache_key_includes_crop_and_engine_provenance():
    recording = {'t0': 11, 'dur': 7}
    args = {
        'source_hash': 'source',
        'crop_hash': 'crop',
        'recording': recording,
        'provenance': {'engine': 'baseline', 'revision': 'a', 'decoding': {'beam': 1}},
    }
    original = reference.artifact_key(**args)
    assert original != reference.artifact_key(**{**args, 'crop_hash': 'other'})
    assert original != reference.artifact_key(**{**args, 'recording': {'t0': 12, 'dur': 7}})
    assert original != reference.artifact_key(**{**args, 'provenance': {'engine': 'different'}})


def test_stale_or_failed_cache_is_never_reused(tmp_path):
    path = tmp_path / 'artifact.json'
    assert not reference.valid_cached(path, 'fresh')
    path.write_text(json.dumps({'cache_key': 'old', 'status': 'ok', 'text': 'fiction'}))
    assert not reference.valid_cached(path, 'fresh')
    path.write_text(json.dumps({'cache_key': 'fresh', 'status': 'BLOCKED', 'text': 'fiction'}))
    assert not reference.valid_cached(path, 'fresh')
    path.write_text(json.dumps({'cache_key': 'fresh', 'status': 'ok', 'text': 'fiction'}))
    assert reference.valid_cached(path, 'fresh')


def test_snapshot_revision_frozen_before_download_and_hash_changes_refused(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'model.bin').write_bytes(b'fictional weights')
    root = tmp_path / 'private'
    root.mkdir()
    calls = []

    class Api:
        def model_info(self, repo):
            return types.SimpleNamespace(sha='a' * 40)

    def download(**kwargs):
        assert json.loads((root / 'model-lock.json').read_text())['revision'] == 'a' * 40
        assert kwargs['revision'] == 'a' * 40
        calls.append(kwargs)
        return snapshot

    monkeypatch.setitem(sys.modules, 'huggingface_hub', types.SimpleNamespace(HfApi=Api, snapshot_download=download))
    _, lock = reference.pin_model('faster-whisper-base', root)
    assert len(lock['files']['model.bin']) == 64
    (snapshot / 'model.bin').write_bytes(b'changed weights')
    with pytest.raises(ValueError, match='hash_changed'):
        reference.pin_model('faster-whisper-base', root)
    assert len(calls) == 2


def test_run_records_real_crop_and_private_provenance(tmp_path, monkeypatch):
    audio = tmp_path / 'audio.wav'
    audio.write_bytes(b'source')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'recordings': [{'id': 'fiction', 'audio': str(audio), 't0': 5, 'dur': 3}]}))
    monkeypatch.setattr(
        reference,
        'pin_model',
        lambda *_, **__: (tmp_path, {'repo': 'fiction', 'revision': 'a' * 40, 'files': {'model': 'hash'}}),
    )
    monkeypatch.setattr(reference.importlib.metadata, 'version', lambda _: 'fixture-version')
    monkeypatch.setattr(reference.subprocess, 'check_output', lambda *_, **__: 'ffmpeg fixture\n')
    crops = []

    def crop(recording, destination):
        crops.append((recording['t0'], recording['dur']))
        destination.write_bytes(b'crop')

    monkeypatch.setattr(reference, 'decode_crop', crop)
    monkeypatch.setattr(
        reference, 'load_transcriber', lambda *_: lambda _: {'text': 'fiction', 'words': [], 'segments': []}
    )
    report = reference.run(manifest, 'mlx-whisper-large-v3', tmp_path / 'outputs')
    assert report['status'] == 'COMPLETE'
    assert report['role'] == 'model_reference_not_truth'
    assert 'fiction' not in json.dumps(report)
    assert str(tmp_path) not in json.dumps(report)
    assert crops == [(5, 3)]
    path = tmp_path / 'outputs/mlx-whisper-large-v3/recording-1.json'
    data = json.loads(path.read_text())
    assert (data['t0'], data['dur']) == (5, 3)
    assert data['provenance']['cloud_inference_calls'] == 0
    assert path.stat().st_mode & 0o777 == 0o600
    # Same immutable inputs reuse inference, but still re-decode to verify crop bytes.
    monkeypatch.setattr(reference, 'load_transcriber', lambda *_: pytest.fail('cached inference executed'))
    assert reference.run(manifest, 'mlx-whisper-large-v3', tmp_path / 'outputs')['per_recording'][0]['cache_hit']
    assert len(crops) == 2


def test_engines_keep_stronger_reference_and_turbo_distinct():
    assert reference.ENGINES['faster-whisper-base']['decoding']['beam_size'] == 1
    assert reference.ENGINES['faster-whisper-base']['decoding']['vad_filter']
    assert reference.ENGINES['mlx-whisper-base']['decoding']['condition_on_previous_text'] is False
    assert reference.ENGINES['mlx-whisper-base']['decoding']['temperature'] == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    assert reference.ENGINES['mlx-whisper-large-v3']['decoding']['temperature'] == 0.0
    assert reference.ENGINES['mlx-whisper-large-v3']['repo'] != reference.ENGINES['mlx-whisper-large-v3-turbo']['repo']


def test_invalid_private_output_reports_only_aggregate_error(tmp_path, monkeypatch, capsys):
    (tmp_path / '.git').write_text('gitdir: fictional')
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'run_reference',
            '--manifest',
            str(tmp_path / 'private-manifest.json'),
            '--engine',
            'mlx-whisper-base',
            '--output-root',
            str(tmp_path),
        ],
    )
    assert reference.main() == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['status'] == 'BLOCKED'
    assert str(tmp_path) not in captured.out + captured.err


def test_scorecard_refuses_stale_source_crop_engine_or_lock(tmp_path):
    import copy
    import wave

    source = tmp_path / 'source'
    source.write_bytes(b'synthetic-source')
    recording = {'id': 'synthetic-id', 'audio': str(source), 't0': 0, 'dur': 1}
    root = tmp_path / 'reference'
    (root / 'crops').mkdir(parents=True)
    source_hash = reference.digest(source)
    crop_id = reference.fingerprint({'audio': source_hash, 't0': 0, 'dur': 1})
    crop = root / 'crops' / (crop_id + '.wav')
    with wave.open(str(crop), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 16000)
    engine = 'mlx-whisper-large-v3'
    config = reference.ENGINES[engine]
    lock = {'repo': config['repo'], 'revision': 'a' * 40, 'files': {'model': 'verified-digest'}}
    (root / 'model-lock.json').write_text(json.dumps(lock))
    provenance = {
        'engine': engine,
        'repo': lock['repo'],
        'revision': lock['revision'],
        'model_files': lock['files'],
        'clock': 'crop',
        'role': 'model_reference_not_truth',
        'cloud_inference_calls': 0,
        'decoding': config['decoding'],
    }
    baseline = {
        'status': 'ok',
        'id': recording['id'],
        't0': 0,
        'dur': 1,
        'text': 'synthetic reference',
        'audio_sha256': source_hash,
        'crop_sha256': reference.digest(crop),
        'provenance': provenance,
    }
    baseline['cache_key'] = reference.artifact_key(
        source_hash=source_hash, crop_hash=baseline['crop_sha256'], recording=recording, provenance=provenance
    )
    artifact = root / 'recording.json'
    artifact.write_text(json.dumps(baseline))
    assert reference_text(artifact, recording, crop, engine) == 'synthetic reference'
    for key, value in [
        ('status', 'BLOCKED'),
        ('id', 'other'),
        ('dur', 2),
        ('audio_sha256', 'wrong'),
        ('crop_sha256', 'wrong'),
    ]:
        changed = copy.deepcopy(baseline)
        changed[key] = value
        artifact.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match='provenance_mismatch'):
            reference_text(artifact, recording, crop, engine)
    artifact.write_text(json.dumps(baseline))
    lock['revision'] = 'b' * 40
    (root / 'model-lock.json').write_text(json.dumps(lock))
    with pytest.raises(ValueError, match='provenance_mismatch'):
        reference_text(artifact, recording, crop, engine)
