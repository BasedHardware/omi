#!/usr/bin/env python3
"""Reproducible local Whisper baselines; stronger model output is NOT truth.

Run each engine inside its own existing environment. Public model snapshots may
be downloaded; recording bytes are decoded and transcribed locally only.
"""

import argparse
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

if __package__:
    from .prep_speaker_task import private_dir, write_private
else:
    from prep_speaker_task import private_dir, write_private

ENGINES = {
    'faster-whisper-base': {
        'repo': 'Systran/faster-whisper-base',
        'packages': ['faster-whisper', 'ctranslate2', 'huggingface-hub'],
        'decoding': {'beam_size': 1, 'vad_filter': True, 'word_timestamps': True},
        'device': 'cpu',
        'compute_type': 'int8',
    },
    'mlx-whisper-base': {
        'repo': 'mlx-community/whisper-base-mlx',
        'packages': ['mlx-whisper', 'mlx', 'huggingface-hub'],
        'decoding': {
            'condition_on_previous_text': False,
            'word_timestamps': True,
            'temperature': (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        },
        'device': 'metal',
        'compute_type': 'float16',
    },
    'mlx-whisper-large-v3': {
        'repo': 'mlx-community/whisper-large-v3-mlx',
        'packages': ['mlx-whisper', 'mlx', 'huggingface-hub'],
        'decoding': {'condition_on_previous_text': False, 'word_timestamps': True, 'temperature': 0.0},
        'device': 'metal',
        'compute_type': 'float16',
    },
    'mlx-whisper-large-v3-turbo': {
        'repo': 'mlx-community/whisper-large-v3-turbo',
        'packages': ['mlx-whisper', 'mlx', 'huggingface-hub'],
        'decoding': {'condition_on_previous_text': False, 'word_timestamps': True, 'temperature': 0.0},
        'device': 'metal',
        'compute_type': 'float16',
    },
}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()


@contextmanager
def private_logs(path):
    """Capture Python and native model/download logs, including dependency paths."""
    sys.stdout.flush()
    sys.stderr.flush()
    with Path(path).open('a') as log:
        Path(path).chmod(0o600)
        saved = [os.dup(fd) for fd in (1, 2)]
        try:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            for fd, original in zip((1, 2), saved):
                os.dup2(original, fd)
                os.close(original)


def pin_model(engine, root, *, cache_dir=None):
    from huggingface_hub import HfApi, snapshot_download

    settings = ENGINES[engine]
    lock_path = root / 'model-lock.json'
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        if lock['repo'] != settings['repo'] or len(lock['revision']) != 40:
            raise ValueError('invalid_model_lock')
    else:
        revision = HfApi().model_info(settings['repo']).sha
        if not revision or len(revision) != 40:
            raise ValueError('model_revision_not_immutable')
        lock = {'repo': settings['repo'], 'revision': revision}
        # Freeze the revision before downloading any weights or running inference.
        write_private(lock_path, lock)
    path = Path(snapshot_download(repo_id=lock['repo'], revision=lock['revision'], cache_dir=cache_dir))
    hashes = {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob('*')) if p.is_file()}
    if not hashes:
        raise ValueError('empty_model_snapshot')
    if lock.get('files') is not None and lock['files'] != hashes:
        raise ValueError('model_snapshot_hash_changed')
    lock['files'] = hashes
    write_private(lock_path, lock)
    return path, lock


def decode_crop(recording, destination):
    subprocess.run(
        [
            'ffmpeg',
            '-nostdin',
            '-v',
            'error',
            '-y',
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
            str(destination),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    destination.chmod(0o600)


def load_transcriber(engine, model_path):
    if engine == 'faster-whisper-base':
        from faster_whisper import WhisperModel

        model = WhisperModel(str(model_path), device='cpu', compute_type='int8', local_files_only=True)

        def transcribe(audio):
            segments, info = model.transcribe(str(audio), **ENGINES[engine]['decoding'])
            rows = list(segments)
            return {
                'text': ' '.join(row.text.strip() for row in rows),
                'words': [
                    {'start': word.start, 'end': word.end, 'text': word.word}
                    for row in rows
                    for word in (row.words or [])
                ],
                'segments': [{'start': row.start, 'end': row.end, 'text': row.text} for row in rows],
                'detected_language': info.language,
            }

    else:
        import mlx_whisper

        def transcribe(audio):
            result = mlx_whisper.transcribe(
                str(audio), path_or_hf_repo=str(model_path), verbose=None, **ENGINES[engine]['decoding']
            )
            return {
                'text': result['text'],
                'words': [
                    {'start': w['start'], 'end': w['end'], 'text': w['word']}
                    for row in result['segments']
                    for w in row.get('words', [])
                ],
                'segments': [{k: row[k] for k in ('start', 'end', 'text')} for row in result['segments']],
                'detected_language': result.get('language'),
            }

    return transcribe


def artifact_key(*, source_hash, crop_hash, recording, provenance):
    return fingerprint(
        {
            'audio_sha256': source_hash,
            'crop_sha256': crop_hash,
            't0': recording['t0'],
            'dur': recording['dur'],
            'provenance': provenance,
        }
    )


def valid_cached(path, key):
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    return data.get('cache_key') == key and data.get('status') == 'ok' and isinstance(data.get('text'), str)


def run(manifest_path, engine, output_root, *, cache_dir=None):
    manifest = json.loads(Path(manifest_path).read_text())
    root = private_dir(Path(output_root) / engine)
    private_dir(root / 'crops')
    began = time.monotonic()
    model_path, lock = pin_model(engine, root, cache_dir=cache_dir)
    settings = ENGINES[engine]
    provenance = {
        'engine': engine,
        'repo': lock['repo'],
        'revision': lock['revision'],
        'model_files': lock['files'],
        'packages': {p: importlib.metadata.version(p) for p in settings['packages']},
        'decoding': settings['decoding'],
        'device': settings['device'],
        'compute_type': settings['compute_type'],
        'runner_sha256': digest(__file__),
        'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'role': 'model_reference_not_truth' if 'large-v3' in engine else 'baseline',
        'cloud_inference_calls': 0,
        'clock': 'crop',
    }
    rows, files, transcribe = [], {}, None
    for index, recording in enumerate(manifest['recordings'], 1):
        start = time.monotonic()
        row = {'recording': index}
        try:
            source_hash = digest(recording['audio'])
            crop_id = fingerprint({'audio': source_hash, 't0': recording['t0'], 'dur': recording['dur']})
            audio = root / 'crops' / (crop_id + '.wav')
            # Re-decode to verify actual crop bytes; old crop files are never trusted.
            decode_crop(recording, audio)
            crop_hash = digest(audio)
            key = artifact_key(source_hash=source_hash, crop_hash=crop_hash, recording=recording, provenance=provenance)
            artifact = root / f'recording-{index}.json'
            cached = valid_cached(artifact, key)
            if not cached:
                transcribe = transcribe or load_transcriber(engine, model_path)
                result = transcribe(audio)
                result.update(
                    {
                        'schema_version': 1,
                        'id': recording['id'],
                        'status': 'ok',
                        'cache_key': key,
                        't0': recording['t0'],
                        'dur': recording['dur'],
                        'audio_sha256': source_hash,
                        'crop_sha256': crop_hash,
                        'provenance': provenance,
                        'elapsed_seconds': time.monotonic() - start,
                    }
                )
                write_private(artifact, result)
            files[recording['id']] = str(artifact)
            row.update({'status': 'ok', 'cache_hit': cached, 'elapsed_seconds': time.monotonic() - start})
        except Exception as error:
            traceback.print_exc()
            row.update(
                {'status': 'BLOCKED', 'error_type': type(error).__name__, 'elapsed_seconds': time.monotonic() - start}
            )
        rows.append(row)
        write_private(root / 'progress.json', {'engine': engine, 'per_recording': rows})
    report = {
        'engine': engine,
        'role': provenance['role'],
        'status': 'COMPLETE' if len(files) == len(rows) else 'BLOCKED',
        'recordings': len(rows),
        'succeeded': len(files),
        'failures': len(rows) - len(files),
        'elapsed_seconds': time.monotonic() - began,
        'per_recording': rows,
    }
    write_private(root / 'reference-files.json', files)
    write_private(root / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--engine', choices=list(ENGINES), required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        root = private_dir(args.output_root / args.engine)
    except Exception as error:
        print(json.dumps({'engine': args.engine, 'status': 'BLOCKED', 'error_type': type(error).__name__}))
        return 1
    with private_logs(root / 'model-private.log'):
        try:
            report = run(args.manifest, args.engine, args.output_root, cache_dir=args.cache_dir)
        except Exception as error:
            traceback.print_exc()
            report = {'engine': args.engine, 'status': 'BLOCKED', 'error_type': type(error).__name__}
            write_private(root / 'report.json', report)
    print(json.dumps(report, allow_nan=False))
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
