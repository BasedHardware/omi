#!/usr/bin/env python3
"""Run the shipping adapters and projection against an explicitly private corpus.

Only aggregate scorecards reach stdout. Detailed model logs and persisted text
stay in a permission-restricted artifact directory beside the corpus manifest.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import secrets
import subprocess
import time
import traceback

from scripts.diarization_eval.local_artifacts import Artifacts, cache_key, file_digest, private_json, project
from scripts.diarization_eval.run_reference import private_logs
from scripts.diarization_eval.prep_speaker_task import private_dir
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.conversations.final_pass_assignment import name_centroids
from utils.stt.diarization_eval import aggregate_scorecards, model_reference_wer, score_recording
from utils.stt.voiceprints import usable_person_voiceprint

ROOT = Path(__file__).resolve().parents[2]
EMBEDDING_SPACE = 'pyannote/wespeaker-voxceleb-resnet34-LM:v2'


def crop_audio(recording, output):
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


def evaluate(manifest_path, *, device='cpu', dtype='float32', run_name='pr1', reference_files=None):
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
    settings = {'device': device, 'dtype': dtype, 'packages': model_versions, 'model_batch_size': 1}
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
    scores, recordings, failures = [], [], 0
    worker, model_failed = None, False
    for index, recording in enumerate(manifest['recordings']):
        began = time.monotonic()
        public = {'recording': index + 1}
        try:
            key = cache_key(
                audio=recording['audio'],
                crop=[recording['t0'], recording['dur']],
                source_files=sources,
                settings=settings,
            )
            cached = root / (key + '.json')
            wav = root / f'crop-{index}.wav'
            if not cached.exists():
                crop_audio(recording, wav)
                if worker is None:
                    if model_failed:
                        raise RuntimeError('models_unavailable')
                    startup = importlib.import_module('diarizer.batch_pipeline_startup')
                    try:
                        worker = startup.load_local_worker(artifacts, device=device, dtype=dtype, model_batch_size=1)
                    except Exception:
                        model_failed = True
                        raise
                item = WorkItem(key, 'local-evaluation', 1_700_000_000.0, str(wav), recording['dur'], Priority.DEEP)
                outcomes = worker.process_batch([item])
                if len(outcomes) != 1 or getattr(outcomes[0], 'outcome', None) != 'success':
                    raise RuntimeError('pipeline_did_not_produce_transcript')
                payload = artifacts.load_result(item, outcomes[0].result_uri)
                private_json(cached, payload)
            else:
                payload = json.loads(cached.read_text())
                item = WorkItem(key, 'local-evaluation', 1_700_000_000.0, str(wav), recording['dur'], Priority.DEEP)
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
            persisted = project(artifacts, item, binding, str(cached))
            for turn in persisted:
                if turn.get('is_user'):
                    turn['display_name'] = 'You'
                elif turn.get('person_id') in display_names:
                    turn['display_name'] = display_names[turn['person_id']]
            truth = [{**word, 'speaker': word['truth']} for word in recording['words']]
            reference = None
            if reference_files and recording['id'] in reference_files:
                reference = json.loads(Path(reference_files[recording['id']]).read_text())['text']
            score = score_recording(truth, persisted, recording['identity_table'], model_reference=reference)
            if reference is not None:
                score['whisper_base_model_reference_wer'] = {}
                for engine in ('faster-whisper-base', 'mlx-whisper-base'):
                    index_file = manifest_path.parent / 'references' / engine / 'reference-files.json'
                    if index_file.exists():
                        paths = json.loads(index_file.read_text())
                        artifact = json.loads(Path(paths[recording['id']]).read_text())
                        score['whisper_base_model_reference_wer'][engine] = model_reference_wer(
                            reference, artifact['text']
                        )
            elapsed = time.monotonic() - began
            public.update(score)
            public.update(
                {
                    'execution_status': 'ok',
                    'naming_evidence': 'compatible' if compatible else 'ABSTAIN_MISSING_COMPATIBLE_CENTROIDS',
                    'centroid_decisions': len(decisions),
                    'elapsed_seconds': elapsed,
                    'rtf': elapsed / recording['dur'],
                }
            )
            scores.append(score)
            recordings.append(
                {
                    'id': recording['id'],
                    'status': 'ok',
                    'clock': 'crop',
                    'turns': persisted,
                    'provenance': {'production_path': True, **settings},
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
        'enrollment_rich': {'status': 'NOT_EVALUATED', 'diagnostic_only': True},
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
            )
        except Exception as error:
            traceback.print_exc()
            report = {'status': 'BLOCKED', 'error_type': type(error).__name__, 'non_english': 'NOT_EVALUATED'}
    print(json.dumps(report, indent=2, allow_nan=False))
    return 1 if report['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
