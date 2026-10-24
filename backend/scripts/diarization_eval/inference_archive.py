"""Explicit, verified reuse of immutable private inference artifacts.

An archive preserves original source/settings identity; enrichment is a new
composed stage, never evidence that current ASR/diarization code was executed.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import wave

from scripts.diarization_eval.local_artifacts import file_digest
from config.batch_pipeline_gpu_skip import diarize_speech_only_enabled, short_speech_single_enabled
from config.batch_pipeline import (
    empty_asr_disposition_enabled,
    empty_asr_recovery_enabled,
    long_speech_handoff_enabled,
    worker_silence_disposition_enabled,
    worker_validation_disposition_enabled,
)

# The primitive is backportable to the scorecard before production enrichment.
COMMUNITY_MODEL_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
EMBEDDING_REVISION = '837717ddb9ff5507820346191109dc79c958d614'

ROOT = Path(__file__).resolve().parents[2]


def effective_worker_switches():
    """Capture effective values through the same accessors the worker uses."""
    return {
        'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED': diarize_speech_only_enabled(),
        'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED': short_speech_single_enabled(),
        'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED': empty_asr_recovery_enabled(),
        'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED': empty_asr_disposition_enabled(),
        'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED': worker_silence_disposition_enabled(),
        'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED': worker_validation_disposition_enabled(),
        'BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED': long_speech_handoff_enabled(),
    }


def pcm_digest(path):
    digest = hashlib.sha256()
    with wave.open(str(path), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('archive_pcm_format_mismatch')
        while block := audio.readframes(65536):
            digest.update(block)
    return digest.hexdigest()


def verify_sources(commit, sources):
    if not re.fullmatch('[0-9a-f]{40}', commit) or not sources:
        raise ValueError('archive_source_identity_missing')
    for source in sources:
        path = Path(source['path'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('archive_invalid_source_path')
        result = subprocess.run(['git', 'show', f'{commit}:{path.as_posix()}'], cwd=ROOT.parent, capture_output=True)
        if result.returncode or hashlib.sha256(result.stdout).hexdigest() != source['sha256']:
            raise ValueError('archive_source_hash_mismatch')


def load_inference(path, *, corpus_sha256, recording, wav, current_settings):
    """Return payload and original receipt, or None for an unarchived record."""
    archive = json.loads(Path(path).read_text())
    if archive.get('schema_version') != 1 or archive.get('corpus_sha256') != corpus_sha256:
        raise ValueError('archive_corpus_mismatch')
    receipt = archive['recordings'].get(recording['id'])
    if receipt is None:
        return None
    receipt = deepcopy(receipt)
    settings = receipt['settings']
    # Older archives can supply separately reconstructed launch evidence, but
    # must preserve their original settings and cache key rather than rekeying.
    switches = settings.get('worker_switches', receipt.get('worker_switches'))
    if (
        receipt.get('provider_config_evidence') not in ('captured', 'reconstructed-original-launch')
        or receipt.get('provider_config') != current_settings['provider_config']
        or switches is None
        or switches != current_settings.get('worker_switches')
        or receipt.get('worker_switches_evidence') not in ('captured', 'reconstructed-original-launch')
        or ('worker_switches' in settings and receipt.get('worker_switches', switches) != switches)
        or any(settings.get(key) != current_settings[key] for key in ('device', 'dtype', 'model_batch_size'))
        or settings.get('model_revisions', {}).get('community_1') != COMMUNITY_MODEL_REVISION
        or settings.get('model_revisions', {}).get('parakeet') != current_settings['model_revisions']['parakeet']
        or settings.get('model_revisions', {}).get('wespeaker_v2') != EMBEDDING_REVISION
        or settings.get('packages') != current_settings['packages']
    ):
        raise ValueError('archive_effective_configuration_mismatch')
    verify_sources(receipt['source_commit'], receipt['sources'])
    audio_sha = file_digest(recording['audio'])
    if (
        receipt.get('audio_sha256') != audio_sha
        or receipt.get('crop') != [recording['t0'], recording['dur']]
        or receipt.get('crop_pcm_sha256') != pcm_digest(wav)
    ):
        raise ValueError('archive_audio_crop_mismatch')
    key_material = {
        'audio': audio_sha,
        'crop': receipt['crop'],
        'sources': [source['sha256'] for source in receipt['sources']],
        'settings': settings,
    }
    original_key = hashlib.sha256(json.dumps(key_material, sort_keys=True).encode()).hexdigest()
    if receipt.get('cache_key') != original_key or file_digest(receipt['payload_file']) != receipt['payload_sha256']:
        raise ValueError('archive_artifact_hash_mismatch')
    payload = json.loads(Path(receipt['payload_file']).read_text())
    existing_revision = payload.get('diarization', {}).get('provenance', {}).get('model_revision')
    if existing_revision not in (None, COMMUNITY_MODEL_REVISION):
        raise ValueError('archive_payload_model_mismatch')
    # Preserve original payload bytes/meaning; a later enrichment adapter owns
    # any new fields and retains this original receipt as composed provenance.
    return payload, receipt
