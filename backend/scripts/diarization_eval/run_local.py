#!/usr/bin/env python3
"""Run the shipping adapters and projection against an explicitly private corpus.

Only aggregate scorecards reach stdout. Detailed model logs and persisted text
stay in a permission-restricted artifact directory beside the corpus manifest.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import secrets
import subprocess
import sys
import time
import traceback
import wave

from scripts.diarization_eval.local_artifacts import (
    Artifacts,
    cache_key,
    file_digest,
    private_json,
    project,
    project_external,
)
from scripts.diarization_eval.run_reference import ENGINES, artifact_key, fingerprint, private_logs
from scripts.diarization_eval.prep_speaker_task import private_dir
from scripts.diarization_eval.enrollment import build_gallery
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.audio import with_context
from utils.conversations.final_pass_assignment import name_centroids
from utils.stt.diarization_eval import aggregate_scorecards, model_reference_wer, score_recording
from utils.stt.voiceprints import usable_person_voiceprint
from config.batch_pipeline_providers import provider_config
from scripts.diarization_eval.inference_archive import effective_worker_switches, load_inference

ROOT = Path(__file__).resolve().parents[2]
EMBEDDING_SPACE = 'pyannote/wespeaker-voxceleb-resnet34-LM:v2'


def crop_audio(recording, output):
    language = recording.get('declared_language')
    if not isinstance(language, str) or not language:
        raise ValueError('explicit_corpus_language_required')
    # ffmpeg stderr can contain source paths: capture it, never relay it.
    result = subprocess.run(
        [
            'ffmpeg',
            '-nostdin',
            '-v',
            'error',
            '-ss',
            str(recording['t0']),
            '-i',
            recording['audio'],
            '-t',
            str(recording['dur']),
            '-ar',
            '16000',
            '-ac',
            '1',
            '-c:a',
            'pcm_s16le',
            '-y',
            str(output),
        ],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError('audio_decode_failed')
    output.write_bytes(
        with_context(
            output.read_bytes(),
            {
                'stt_language': language,
                'stt_language_evidence': 'declared',
                'stt_language_confidence': 1.0,
            },
        )
    )
    output.chmod(0o600)


def load_gallery(manifest):
    profile = json.loads(Path(manifest['profile_file']).read_text())
    people = json.loads(Path(manifest['people_file']).read_text())
    gallery = {'user': profile['speaker_embedding']} if profile.get('speaker_embedding') else {}
    names = {}
    for person in people:
        vector = usable_person_voiceprint(person)
        if vector and person.get('id') and not person.get('is_dismissed'):
            gallery[person['id']] = vector
            names[person['id']] = person.get('name', '')
    return gallery, names


def versions():
    result = {}
    for package in ('torch', 'torchaudio', 'nemo_toolkit', 'pyannote.audio', 'numpy'):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = 'NOT_INSTALLED'
    return result


def reference_text(path, recording, wav, engine):
    """Require the declared engine, immutable lock and exact frozen audio crop."""
    path = Path(path)
    artifact = json.loads(path.read_text())
    provenance = artifact['provenance']
    lock = json.loads((path.parent / 'model-lock.json').read_text())
    source_hash = file_digest(recording['audio'])
    crop_id = fingerprint({'audio': source_hash, 't0': recording['t0'], 'dur': recording['dur']})
    crop = path.parent / 'crops' / (crop_id + '.wav')
    expected = ENGINES[engine]
    if not (
        artifact.get('status') == 'ok'
        and artifact.get('id') == recording['id']
        and isinstance(artifact.get('text'), str)
        and artifact.get('t0') == recording['t0']
        and artifact.get('dur') == recording['dur']
        and artifact.get('audio_sha256') == source_hash
        and artifact.get('crop_sha256') == file_digest(crop)
        and provenance.get('engine') == engine
        and provenance.get('repo') == expected['repo']
        and lock.get('repo') == expected['repo']
        and provenance.get('revision') == lock['revision']
        and len(lock['revision']) == 40
        and provenance.get('model_files') == lock['files']
        and lock['files']
        and provenance.get('cloud_inference_calls') == 0
        and provenance.get('clock') == 'crop'
        and provenance.get('role') == ('model_reference_not_truth' if 'large-v3' in engine else 'baseline')
        and fingerprint(provenance.get('decoding')) == fingerprint(expected['decoding'])
        and artifact.get('cache_key')
        == artifact_key(
            source_hash=source_hash, crop_hash=artifact['crop_sha256'], recording=recording, provenance=provenance
        )
    ):
        raise ValueError('reference_provenance_mismatch')

    def pcm_digest(audio_path):
        import hashlib

        digest = hashlib.sha256()
        with wave.open(str(audio_path), 'rb') as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ValueError('reference_pcm_format_mismatch')
            while block := audio.readframes(65536):
                digest.update(block)
        return digest.hexdigest()

    if pcm_digest(crop) != pcm_digest(wav):
        raise ValueError('reference_crop_mismatch')
    return artifact['text']


def evaluate(
    manifest_path,
    *,
    device='cpu',
    dtype='float32',
    run_name='pr1',
    reference_files=None,
    projection_python=None,
    inference_archive=None,
):
    manifest_path = Path(manifest_path)
    private_dir(manifest_path.parent)
    if not run_name or any(
        c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run_name
    ):
        raise ValueError('invalid_run_name')
    manifest = json.loads(manifest_path.read_text())
    if reference_files is None:
        reference_index = manifest_path.parent / 'references' / 'mlx-whisper-large-v3' / 'reference-files.json'
        if reference_index.exists():
            reference_files = json.loads(reference_index.read_text())
    root = manifest_path.parent / run_name
    artifacts = Artifacts(root)
    manifest_hash = file_digest(manifest_path)
    frozen = manifest_path.parent / 'corpus-frozen.json'
    if frozen.exists() and json.loads(frozen.read_text())['sha256'] != manifest_hash:
        raise ValueError('frozen_corpus_changed')
    private_json(frozen, {'sha256': manifest_hash})
    gallery, display_names = load_gallery(manifest)
    model_versions = versions()
    settings = {
        'device': device,
        'dtype': dtype,
        'packages': model_versions,
        'model_batch_size': 1,
        'provider_config': asdict(provider_config()),
        'worker_switches': effective_worker_switches(),
    }
    settings['model_revisions'] = {
        'parakeet': '541d1f99c6b0c3cd0b11a95167540bb8edefd82b',
        'community_1': '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee',
        'wespeaker_v2': '837717ddb9ff5507820346191109dc79c958d614',
    }
    sources = [
        *sorted((ROOT / 'diarizer').glob('batch_pipeline*.py')),
        *sorted((ROOT / 'utils/batch_pipeline').glob('*.py')),
        *sorted((ROOT / 'config').glob('batch_pipeline*.py')),
    ]
    scores, recordings, failures, rich_scores = [], [], 0, []
    worker, model_failed = None, False
    for index, recording in enumerate(manifest['recordings']):
        began = time.monotonic()
        public = {'recording': index + 1}
        try:
            key = cache_key(
                audio=recording['audio'],
                crop=[recording['t0'], recording['dur']],
                source_files=sources,
                settings={**settings, 'declared_language': recording.get('declared_language')},
            )
            cached = root / (key + '.json')
            wav = root / f'crop-{index}.wav'
            if not wav.exists() or not cached.exists():
                crop_audio(recording, wav)
            # Archive durations are rounded; admit the exact decoded capture,
            # leaving the frozen crop and every reference-word clock intact.
            with wave.open(str(wav), 'rb') as audio:
                captured_seconds = audio.getnframes() / audio.getframerate()
            item = WorkItem(key, 'local-evaluation', 1_700_000_000.0, str(wav), captured_seconds, Priority.DEEP)
            archived = (
                load_inference(
                    inference_archive,
                    corpus_sha256=manifest_hash,
                    recording=recording,
                    wav=wav,
                    current_settings=settings,
                )
                if inference_archive
                else None
            )
            if archived is not None:
                payload, original_receipt = archived
                key = original_receipt['cache_key']
                item = replace(item, segment_id=key)
                cached = root / ('archive-' + key + '.json')
                private_json(cached, payload)
            elif not cached.exists():
                if worker is None:
                    if model_failed:
                        raise RuntimeError('models_unavailable')
                    startup = importlib.import_module('diarizer.batch_pipeline_startup')
                    try:
                        worker = startup.load_local_worker(artifacts, device=device, dtype=dtype, model_batch_size=1)
                    except Exception:
                        model_failed = True
                        raise
                outcomes = worker.process_batch([item])
                if len(outcomes) != 1 or getattr(outcomes[0], 'outcome', None) != 'success':
                    private_json(
                        root / f'failure-{index}.json',
                        {
                            'outcomes': [type(outcome).__name__ for outcome in outcomes],
                            'reasons': [getattr(outcome, 'reason', None) for outcome in outcomes],
                        },
                    )
                    raise RuntimeError('pipeline_did_not_produce_transcript')
                payload = artifacts.load_result(item, outcomes[0].result_uri)
                private_json(cached, payload)
            else:
                payload = json.loads(cached.read_text())
            diarization = payload['diarization']
            compatible = diarization.get('embedding_space') == EMBEDDING_SPACE
            # PR1 intentionally reports today's absence of compatible evidence.
            # This call is diagnostic; only production projection may publish it.
            decisions = name_centroids(diarization.get('centroids', {}) if compatible else {}, gallery)
            binding = ProjectionBinding(
                'local-evaluation',
                'local-job',
                'local-content',
                (key,),
                target_conversation_id='local-conversation',
                record_origin=True,
            )
            persisted = (
                project_external(projection_python, artifacts, item, binding, str(cached))
                if projection_python is not None
                and Path(projection_python).absolute() != Path(sys.executable).absolute()
                else project(artifacts, item, binding, str(cached))
            )
            for turn in persisted:
                if turn.get('is_user'):
                    turn['display_name'] = 'You'
                elif turn.get('person_id') in display_names:
                    turn['display_name'] = display_names[turn['person_id']]
            truth = [{**word, 'speaker': word['truth']} for word in recording['words']]
            reference = None
            if reference_files and recording['id'] in reference_files:
                reference = reference_text(reference_files[recording['id']], recording, wav, 'mlx-whisper-large-v3')
            score = score_recording(truth, persisted, recording['identity_table'], model_reference=reference)
            if reference is not None:
                score['whisper_base_model_reference_wer'] = {}
                for engine in ('faster-whisper-base', 'mlx-whisper-base'):
                    index_file = manifest_path.parent / 'references' / engine / 'reference-files.json'
                    historical_index = manifest_path.parent / 'references-historical' / engine / 'reference-files.json'
                    if historical_index.exists():
                        index_file = historical_index
                    if index_file.exists():
                        paths = json.loads(index_file.read_text())
                        text = reference_text(paths[recording['id']], recording, wav, engine)
                        score['whisper_base_model_reference_wer'][engine] = model_reference_wer(reference, text)
            elapsed = time.monotonic() - began
            public.update(score)
            public.update(
                {
                    'execution_status': 'ok',
                    'naming_evidence': 'compatible' if compatible else 'ABSTAIN_MISSING_COMPATIBLE_CENTROIDS',
                    'centroid_decisions': len(decisions),
                    'elapsed_seconds': elapsed,
                    'rtf': elapsed / recording['dur'],
                    'decoded_audio_seconds': captured_seconds,
                    'declared_crop_seconds': recording['dur'],
                    'inference_reused': archived is not None,
                    'original_configuration_evidence': (
                        archived[1]['provider_config_evidence'] if archived else 'captured'
                    ),
                }
            )
            scores.append(score)
            if recording.get('enrollment_spans'):
                try:
                    if not wav.exists():
                        crop_audio(recording, wav)
                    rich = build_gallery(recording, wav, root / f'enrollment-{index}.json', base_gallery=gallery)
                    rich_decisions = name_centroids(
                        diarization.get('centroids', {}) if compatible else {}, rich['gallery']
                    )
                    # PR1 has no production batch naming seam: its persisted
                    # output stays anonymous even with richer enrollment.
                    diagnostic = score_recording(
                        truth, persisted, rich['identity_table'], excluded_spans=rich['excluded_spans']
                    )
                    diagnostic.update(
                        diagnostic_only=True,
                        enrolled_voices=len(rich['gallery']),
                        centroid_decisions=len(rich_decisions),
                    )
                    public['enrollment_rich'] = diagnostic
                    rich_scores.append(diagnostic)
                except Exception as error:
                    traceback.print_exc()
                    public['enrollment_rich'] = {
                        'status': 'BLOCKED',
                        'error_type': type(error).__name__,
                        'diagnostic_only': True,
                    }
            recordings.append(
                {
                    'id': recording['id'],
                    'status': 'ok',
                    'clock': 'crop',
                    'turns': persisted,
                    'provenance': {
                        'production_path': True,
                        **settings,
                        'full_current_worker_executed': archived is None,
                        'original_inference': archived[1] if archived else None,
                    },
                    'cache_key': key,
                }
            )
        except Exception as error:
            traceback.print_exc()
            failures += 1
            public.update({'status': 'BLOCKED', 'error_type': type(error).__name__})
            recordings.append({'id': recording['id'], 'status': 'BLOCKED'})
        private_json(root / f'score-{index}.json', public)
    report = {
        'status': 'BLOCKED' if failures else 'COMPLETE',
        'failures': failures,
        'recordings_expected': len(manifest['recordings']),
        'per_recording': [
            json.loads((root / f'score-{i}.json').read_text()) for i in range(len(manifest['recordings']))
        ],
        'pooled': aggregate_scorecards(scores) if scores else None,
        'non_english': 'NOT_EVALUATED',
        'device': device,
        'dtype': dtype,
        'packages': model_versions,
        'peak_rss_native_units': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'snapshot_enrolled_people': len(gallery) - int('user' in gallery),
        'enrollment_rich': {
            'status': 'COMPLETE' if len(rich_scores) == len(manifest['recordings']) else 'BLOCKED',
            'diagnostic_only': True,
            'pooled': aggregate_scorecards(rich_scores) if rich_scores else None,
        },
        'model_reference': 'model reference, not truth' if reference_files else 'NOT_EVALUATED',
        'firestore_reads': 0,
        'cloud_inference_calls': 0,
    }
    if failures:
        report['engineering_gate'] = 'BLOCKED'
        if report['pooled'] is not None:
            report['pooled']['engineering_gate'] = 'BLOCKED'
    private_json(root / 'runs.json', {'recordings': recordings})
    private_json(root / 'scorecard.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda:0'], default='cpu')
    parser.add_argument('--dtype', choices=['float32', 'bfloat16'], default='float32')
    parser.add_argument('--run-name', default='pr1')
    parser.add_argument('--projection-python', type=Path, default=ROOT / '.venv' / 'bin' / 'python')
    parser.add_argument(
        '--inference-archive', type=Path, help='Explicit immutable inference archive with verified receipts'
    )
    parser.add_argument(
        '--reference-files', type=Path, help='Private JSON mapping recording IDs to model-reference files'
    )
    args = parser.parse_args()
    os.umask(0o077)
    # Filesystem projection never decrypts account data. Supply a disposable
    # local key for shared schema imports, never a serving secret or ADC.
    os.environ['ENCRYPTION_SECRET'] = secrets.token_hex(32)
    log_path = args.manifest.parent / 'model-private.log'
    private_dir(log_path.parent)
    with private_logs(log_path), log_path.open('a') as log, redirect_stdout(log), redirect_stderr(log):
        try:
            report = evaluate(
                args.manifest,
                device=args.device,
                dtype=args.dtype,
                run_name=args.run_name,
                reference_files=json.loads(args.reference_files.read_text()) if args.reference_files else None,
                projection_python=args.projection_python,
                inference_archive=args.inference_archive,
            )
        except Exception as error:
            traceback.print_exc()
            report = {'status': 'BLOCKED', 'error_type': type(error).__name__, 'non_english': 'NOT_EVALUATED'}
    print(json.dumps(report, indent=2, allow_nan=False))
    return 1 if report['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
