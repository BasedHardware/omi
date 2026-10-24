"""Original inference identity survives explicit composed enrichment."""

import hashlib
import json
from pathlib import Path
import subprocess
import wave

import pytest

from scripts.diarization_eval.inference_archive import load_inference, pcm_digest
from scripts.diarization_eval.local_artifacts import file_digest, private_json
from scripts.diarization_eval.inference_archive import COMMUNITY_MODEL_REVISION, EMBEDDING_REVISION


def archive(tmp_path):
    root = Path(__file__).resolve().parents[3]
    source = 'backend/utils/batch_pipeline/contracts.py'
    commit = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    audio, wav, payload_file = tmp_path / 'source', tmp_path / 'crop.wav', tmp_path / 'payload.json'
    audio.write_bytes(b'synthetic-audio')
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 16000)
    private_json(payload_file, {'diarization': {'turns': []}, 'words': []})
    settings = {
        'device': 'cpu',
        'dtype': 'float32',
        'model_batch_size': 1,
        'packages': {'numpy': 'synthetic'},
        'model_revisions': {
            'community_1': COMMUNITY_MODEL_REVISION,
            'parakeet': 'pinned',
            'wespeaker_v2': EMBEDDING_REVISION,
        },
    }
    receipt = {
        'source_commit': commit,
        'sources': [{'path': source, 'sha256': file_digest(root / source)}],
        'settings': settings,
        'provider_config': {'words': 'parakeet'},
        'provider_config_evidence': 'reconstructed-original-launch',
        'worker_switches': {
            'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED': True,
            'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED': False,
            'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED': False,
            'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED': False,
            'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED': False,
            'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED': True,
            'BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED': True,
        },
        'worker_switches_evidence': 'reconstructed-original-launch',
        'audio_sha256': file_digest(audio),
        'crop': [0, 1],
        'crop_pcm_sha256': pcm_digest(wav),
        'payload_file': str(payload_file),
        'payload_sha256': file_digest(payload_file),
    }
    receipt['cache_key'] = hashlib.sha256(
        json.dumps(
            {
                'audio': receipt['audio_sha256'],
                'crop': receipt['crop'],
                'sources': [row['sha256'] for row in receipt['sources']],
                'settings': settings,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    path = tmp_path / 'archive.json'
    document = {'schema_version': 1, 'corpus_sha256': 'frozen-corpus', 'recordings': {'synthetic': receipt}}
    private_json(path, document)
    args = {
        'corpus_sha256': 'frozen-corpus',
        'recording': {'id': 'synthetic', 'audio': str(audio), 't0': 0, 'dur': 1},
        'wav': wav,
        'current_settings': {
            **settings,
            'provider_config': receipt['provider_config'],
            'worker_switches': receipt['worker_switches'],
        },
    }
    return path, document, args


def test_archive_verifies_original_key_and_retains_reconstructed_configuration_label(tmp_path):
    path, document, args = archive(tmp_path)
    payload, receipt = load_inference(path, **args)
    assert receipt['cache_key'] == document['recordings']['synthetic']['cache_key']
    assert receipt['provider_config_evidence'] == 'reconstructed-original-launch'
    assert payload == {'diarization': {'turns': []}, 'words': []}
    assert json.loads(Path(receipt['payload_file']).read_text()) == {'diarization': {'turns': []}, 'words': []}
    assert load_inference(path, **{**args, 'recording': {**args['recording'], 'id': 'not-archived'}}) is None


@pytest.mark.parametrize(
    'mutation',
    ['source', 'crop', 'payload', 'key', 'provider', 'corpus', 'switch', 'missing_switch', 'switch_evidence'],
)
def test_archive_rejects_changed_evidence(tmp_path, mutation):
    path, document, args = archive(tmp_path)
    receipt = document['recordings']['synthetic']
    if mutation == 'source':
        receipt['sources'][0]['sha256'] = 'changed'
    elif mutation == 'crop':
        receipt['crop_pcm_sha256'] = 'changed'
    elif mutation == 'payload':
        Path(receipt['payload_file']).write_text('{}')
    elif mutation == 'key':
        receipt['cache_key'] = 'changed'
    elif mutation == 'provider':
        receipt['provider_config'] = {'words': 'different'}
    elif mutation == 'switch':
        receipt['worker_switches'] = {**receipt['worker_switches'], 'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED': True}
    elif mutation == 'missing_switch':
        del receipt['worker_switches']
    elif mutation == 'switch_evidence':
        del receipt['worker_switches_evidence']
    else:
        document['corpus_sha256'] = 'changed'
    private_json(path, document)
    with pytest.raises(ValueError, match='archive_'):
        load_inference(path, **args)


@pytest.mark.parametrize(
    'name',
    [
        'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED',
        'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED',
        'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED',
        'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED',
    ],
)
def test_archive_rejects_each_changed_effective_worker_switch(tmp_path, name):
    path, document, args = archive(tmp_path)
    previous_key = document['recordings']['synthetic']['cache_key']
    args['current_settings']['worker_switches'] = {
        **args['current_settings']['worker_switches'],
        name: not args['current_settings']['worker_switches'][name],
    }
    with pytest.raises(ValueError, match='archive_effective_configuration_mismatch'):
        load_inference(path, **args)
    assert json.loads(path.read_text())['recordings']['synthetic']['cache_key'] == previous_key
