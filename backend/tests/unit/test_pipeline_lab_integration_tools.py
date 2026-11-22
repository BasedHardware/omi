"""Integration-pass tools: production overlay from runtime_env, Parakeet batch adapter, add-day audio, record-stt."""

import json
import os
import struct
import wave

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.cassette.adapters import ParakeetBatchAdapter, STTRequest, make_adapter
from testing.pipeline_lab.cassette.format import BYTES_PER_SECOND
from testing.pipeline_lab.seed.synthetic import write_synthetic_snapshot
from testing.pipeline_lab.stack.runtime_env import overlay_from_runtime_env
from testing.pipeline_lab.stack.overlay import Overlay

DAY = '2026-03-14'

RUNTIME_ENV = """
schema_version: 2
environments:
  prod:
    gke:
      backend-listen:
        env:
          NOTES_MODE: {value: serve, category: rollout}
          OMI_SHAPED_AGENT_MODE: {value: 'on', category: rollout}
          SOME_FLAG_ENABLED: {value: true, category: ops_kill}
          VENDOR_API_KEY: {value: not-a-real-key, category: rollout}
          HOSTED_THING_URL: {value: 'http://10.0.0.1:80', category: rollout}
          OMI_ENV_STAGE: {value: prod, category: rollout}
          FROM_SECRET: {valueFrom: {secretKeyRef: {name: s, key: k}}}
          FULL_SERVE_PERCENT: {value: '100', category: rollout}
          HALF_SERVE_PERCENT: {value: '50', category: rollout}
          NONE_SERVE_PERCENT: {value: '0', category: rollout}
"""


def test_overlay_from_runtime_env_keeps_flags_drops_secrets_and_pins_cohorts(tmp_path):
    path = tmp_path / 'runtime_env.yaml'
    path.write_text(RUNTIME_ENV)
    overlay, report = overlay_from_runtime_env(path, service='backend-listen')
    assert overlay['env'] == {'NOTES_MODE': 'serve', 'OMI_SHAPED_AGENT_MODE': 'on', 'SOME_FLAG_ENABLED': 'true'}
    cohorts = {k: overlay['serving'][k] for k in ('FULL', 'HALF', 'NONE')}
    assert cohorts == {'FULL': True, 'HALF': False, 'NONE': False}
    # *_MODE env without cohort env is pinned too (uid-independent), so no decision stays unpinned
    assert overlay['serving']['NOTES_MODE'] is True and report['pinned_static'] == 2
    assert report['unresolved'] == ['HALF']
    assert report['dropped'] == {'secret': 1, 'endpoint': 1, 'lab_owned': 1, 'not_scalar': 1}
    Overlay.from_mapping(overlay)  # the one schema
    resolved, report = overlay_from_runtime_env(path, service='backend-listen', owner_uid='synthetic-owner-uid')
    assert {'FULL', 'HALF', 'NONE'} <= set(resolved['serving']) and report['unresolved'] == []
    assert resolved['serving']['FULL'] is True and resolved['serving']['NONE'] is False
    assert 'synthetic-owner-uid' not in json.dumps(resolved)


def test_parakeet_batch_adapter_records_per_window_on_the_conversation_clock():
    calls = []

    def window(wav, language):
        calls.append(len(wav))
        return [{'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00', 'text': f'w{len(calls)}'}], 'en'

    adapter = ParakeetBatchAdapter(model='parakeet-batch', window_seconds=30, transcribe_window=window)
    response = adapter.transcribe(STTRequest(b'\x00\x00' * int(65 * BYTES_PER_SECOND / 2), 'en'))
    assert len(calls) == 3
    assert [(w.start, w.text, w.speaker) for w in response.words] == [
        (0.5, 'w1', 'w0:SPEAKER_00'),
        (30.5, 'w2', 'w1:SPEAKER_00'),
        (60.5, 'w3', 'w2:SPEAKER_00'),
    ]
    assert (response.served_provider, response.served_model, response.detected_language) == (
        'parakeet',
        'parakeet-batch',
        'en',
    )
    assert adapter.estimate_usd(STTRequest(b'\x00\x00' * 16000, None)) == 0.0
    with pytest.raises(ValueError):
        make_adapter('nope')


def test_parakeet_batch_adapter_needs_an_endpoint(monkeypatch):
    monkeypatch.delenv('OMI_PIPELINE_LAB_PARAKEET_URL', raising=False)
    with pytest.raises(ValueError, match='OMI_PIPELINE_LAB_PARAKEET_URL'):
        ParakeetBatchAdapter()


def _wav(path, seconds=2.0, rate=16000, seed=37):
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b''.join(struct.pack('<h', (i * seed) % 2000 - 1000) for i in range(int(seconds * rate))))


def test_add_day_with_audio_then_record_stt_stub(tmp_path, capsys):
    root, verdicts = tmp_path / 'store', tmp_path / 'verdicts'
    snap = write_synthetic_snapshot(tmp_path / 'snap', day=DAY)
    audio = tmp_path / 'audio'
    audio.mkdir()
    for seed, cid in enumerate(('conv-006', 'conv-007', 'conv-001')):  # conv-001 is an earlier day: ignored
        _wav(audio / f'{cid}.wav', seed=31 + seed)
    code = cli.main(
        [
            '--root',
            str(root),
            '--verdicts',
            str(verdicts),
            '--json',
            'corpus',
            'add-day',
            '--snapshot',
            str(snap),
            '--date',
            DAY,
            '--timezone',
            'UTC',
            '--audio-dir',
            str(audio),
        ]
    )
    added = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0 and added['audio_files'] == 2
    index = json.loads((root / 'corpus' / DAY / 'audio' / 'index.json').read_text())
    assert sorted(e['conversation_id'] for e in index) == ['conv-006', 'conv-007']
    assert all(e['sample_rate'] == 16000 and e['codec'] == 'pcm_s16le' for e in index)
    assert oct((root / 'corpus' / DAY / 'audio' / 'conv-006.wav').stat().st_mode & 0o777) == '0o600'
    assert added['coverage']['with_audio'] == 2
    timeline = json.loads((root / 'corpus' / DAY / 'timeline.json').read_text())
    assert {c['id']: c['lane'] for c in timeline['conversations']}['conv-007'] == 'record'

    code = cli.main(
        ['--root', str(root), '--verdicts', str(verdicts), 'record-stt', '--day', DAY, '--adapter', 'stub']
        + ['--budget-usd', '0.5']
    )
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0 and summary['misses'] == 2 and summary['mode'] == 'span'
    record_dir = root / 'stt_records' / f'{DAY}-stub'
    vendor = [json.loads(line) for line in (record_dir / 'vendor_log.jsonl').read_text().splitlines()]
    assert len(vendor) == 2 and all(row['outcome'] == 'ok' for row in vendor)
    assert json.loads((record_dir / 'ledger.json').read_text())
    assert len(list((root / 'cache' / 'stt_cassette').rglob('*.json'))) == 2
    assert not os.path.exists(root / 'runs' / f'{DAY}-stub')  # recordings are not runs
