"""Synthetic qualification of private filesystem adapters around real projection."""

import json
from pathlib import Path
import socket

import pytest

from scripts.diarization_eval import local_artifacts
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline import projection  # Import-pure dependency setup precedes the timed real projection call.
from utils.batch_pipeline import context, projection_parts
from utils.capture import batch_coverage
from utils.stt import speaker_identity


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', '01' * 32)

    def forbidden(*args, **kwargs):
        raise AssertionError('network access forbidden in local evaluation')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def payload():
    return {
        'audio_seconds': 8,
        'speech_seconds': 3,
        'speech_spans': [{'start': 2, 'end': 5}],
        'words': [
            {'word': 'private-text.', 'timestamp': [2, 3]},
            {'word': 'private-continuation.', 'timestamp': [4, 5]},
        ],
        'diarization': {'turns': [{'start': 2, 'end': 5, 'speaker': 'raw-voice'}]},
        'words_provider': 'synthetic',
    }


def test_real_projector_persists_output_and_preserves_crop_clock(tmp_path, monkeypatch, no_network):
    artifacts = local_artifacts.Artifacts(tmp_path)
    item = WorkItem('unit', 'synthetic-owner', 1700000000, 'unused', 8, Priority.DEEP)
    binding = ProjectionBinding(
        'synthetic-owner', 'job', 'content', ('unit',), target_conversation_id='target', record_origin=True
    )
    uri = artifacts.persist_result(item, payload())
    turns = local_artifacts.project(artifacts, item, binding, uri)
    assert turns
    assert turns[0]['start'] == 2
    assert turns[-1]['end'] == 5
    assert turns[0]['speaker_id_scope'] == 'final:batch:unit'
    assert turns[0]['is_user'] is False
    assert turns[0]['person_id'] is None
    persisted = json.loads((tmp_path / 'projection/unit/part-0.json').read_text())['transcript_segments']
    assert turns == persisted
    assert 'text' in turns[0]  # Actual persisted transcript, rather than raw diarization turns.
    assert set(turns[0]) != set(payload()['diarization']['turns'][0])
    assert (Path(uri).stat().st_mode & 0o777) == 0o600
    assert (tmp_path.stat().st_mode & 0o777) == 0o700


def test_cache_key_changes_for_audio_crop_code_or_settings(tmp_path):
    audio, source = tmp_path / 'audio', tmp_path / 'source'
    audio.write_bytes(b'synthetic-audio')
    source.write_text('synthetic-code')
    args = {
        'audio': audio,
        'crop': [10, 8],
        'source_files': [source],
        'settings': {'revision': 'one', 'dtype': 'float32'},
    }
    baseline = local_artifacts.cache_key(**args)
    assert baseline == local_artifacts.cache_key(**args)
    assert baseline != local_artifacts.cache_key(**{**args, 'crop': [11, 8]})
    assert baseline != local_artifacts.cache_key(**{**args, 'settings': {'revision': 'two', 'dtype': 'float32'}})
    source.write_text('changed-code')
    assert baseline != local_artifacts.cache_key(**args)
    source.write_text('synthetic-code')
    audio.write_bytes(b'changed-audio')
    assert baseline != local_artifacts.cache_key(**args)


def test_runner_all_fail_is_blocked_and_cli_prints_no_private_values(tmp_path, monkeypatch, capsys, no_network):
    from scripts.diarization_eval import run_local

    profile, people, manifest = tmp_path / 'profile.json', tmp_path / 'people.json', tmp_path / 'corpus.json'
    profile.write_text('{}')
    people.write_text('[]')
    manifest.write_text(
        json.dumps(
            {
                'profile_file': str(profile),
                'people_file': str(people),
                'recordings': [
                    {
                        'id': 'secret-uid',
                        'audio': str(tmp_path / 'secret-audio'),
                        't0': 10,
                        'dur': 8,
                        'words': [{'start': 2, 'end': 3, 'truth': 'secret-name', 'text': 'secret-text'}],
                        'identity_table': {},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr('sys.argv', ['run_local.py', '--manifest', str(manifest)])
    assert run_local.main() == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['status'] == 'BLOCKED'
    assert report['failures'] == 1
    assert report['pooled'] is None or report['pooled']['engineering_gate'] != 'PASS'
    assert 'secret' not in captured.out + captured.err
    assert str(tmp_path) not in captured.out + captured.err


@pytest.mark.parametrize('rich_diagnostic', [False, True])
def test_runner_success_uses_persisted_projection_and_hides_model_logs(
    tmp_path, monkeypatch, capsys, no_network, rich_diagnostic
):
    import sys
    from types import SimpleNamespace

    from diarizer import batch_pipeline_startup
    from scripts.diarization_eval import run_local

    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'true')
    for name in (
        'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED',
        'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED',
        'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED',
    ):
        monkeypatch.setenv(name, 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED', 'true')
    profile, people, manifest = tmp_path / 'profile.json', tmp_path / 'people.json', tmp_path / 'corpus.json'
    audio = tmp_path / 'synthetic-audio'
    audio.write_bytes(b'synthetic-only')
    profile.write_text('{}')
    people.write_text('[]')
    manifest.write_text(
        json.dumps(
            {
                'profile_file': str(profile),
                'people_file': str(people),
                'recordings': [
                    {
                        'id': 'secret-uid',
                        'audio': str(audio),
                        't0': 10,
                        'dur': 8,
                        'words': [
                            {'start': 2, 'end': 3, 'truth': 'secret-name', 'text': 'private-text.'},
                            {'start': 4, 'end': 5, 'truth': 'secret-name', 'text': 'private-continuation.'},
                        ],
                        'identity_table': {'secret-name': {'is_user': True}},
                        'enrollment_spans': [[0, 1]] if rich_diagnostic else [],
                    }
                ],
            }
        )
    )
    calls = []

    def crop(recording, output):
        import wave

        assert recording['t0'] == 10
        calls.append('crop')
        with wave.open(str(output), 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * 128000)

    class Worker:
        def __init__(self, artifacts):
            self.artifacts = artifacts

        def process_batch(self, items):
            calls.append('inference')
            print('secret-text secret-name secret-uid vector=[0.1,0.2]')
            print('secret-error-model-log', file=sys.stderr)
            return [SimpleNamespace(outcome='success', result_uri=self.artifacts.persist_result(items[0], payload()))]

    monkeypatch.setattr(
        run_local,
        'build_gallery',
        lambda *args, **kwargs: {
            'gallery': {'user': [1, 0]},
            'names': {},
            'identity_table': {'secret-name': {'is_user': True}},
            'excluded_spans': [],
        },
    )
    monkeypatch.setattr(run_local, 'crop_audio', crop)
    monkeypatch.setattr(batch_pipeline_startup, 'load_local_worker', lambda artifacts, **kwargs: Worker(artifacts))
    monkeypatch.setattr(sys, 'argv', ['run_local.py', '--manifest', str(manifest)])
    assert run_local.main() == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['status'] == 'COMPLETE'
    assert report['per_recording'][0]['strict_all_word_accuracy'] == 0
    assert report['pooled']['engineering_gate'] == 'FAIL'
    assert 'secret' not in captured.out + captured.err
    assert 'vector=' not in captured.out + captured.err
    assert str(tmp_path) not in captured.out + captured.err
    assert calls == ['crop', 'inference']
    runs = json.loads((tmp_path / 'pr1/runs.json').read_text())
    assert runs['recordings'][0]['turns'][0]['start'] == 2
    assert runs['recordings'][0]['turns'][0]['is_user'] is False
    if rich_diagnostic:
        rich_runs = json.loads((tmp_path / 'pr1/runs-enrollment-rich.json').read_text())
        rich_row = rich_runs['recordings'][0]
        assert rich_row['status'] == 'ok' and rich_row['diagnostic_only'] is True
        assert rich_row['provenance']['production_path'] is True
        assert (
            rich_row['provenance']['projection_fingerprint']
            == runs['recordings'][0]['provenance']['projection_fingerprint']
        )
        assert rich_row['cache_key'] == runs['recordings'][0]['cache_key']
        assert rich_row['turns'] == runs['recordings'][0]['turns']
    # The identical corpus/settings reuse computation, then re-run projection.
    assert run_local.main() == 0
    capsys.readouterr()
    assert calls == ['crop', 'inference']
    monkeypatch.setenv('BATCH_PIPELINE_WINDOW_SECONDS', '20')
    assert run_local.main() == 0
    capsys.readouterr()
    assert calls == ['crop', 'inference', 'crop', 'inference']
    for name, value in (
        ('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'true'),
        ('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false'),
        ('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true'),
        ('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true'),
        ('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'true'),
        ('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false'),
        ('BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED', 'false'),
    ):
        previous = len(calls)
        monkeypatch.setenv(name, value)
        assert run_local.main() == 0
        capsys.readouterr()
        assert len(calls) == previous + 2
        assert calls[-2:] == ['crop', 'inference']


def test_declared_language_is_carried_in_existing_staging_envelope(tmp_path, monkeypatch):
    import io
    import wave
    from types import SimpleNamespace
    from scripts.diarization_eval import run_local
    from utils.batch_pipeline.audio import read_context

    body = io.BytesIO()
    with wave.open(body, 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 16000)
    output = tmp_path / 'crop.wav'

    def decode(*args, **kwargs):
        output.write_bytes(body.getvalue())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_local.subprocess, 'run', decode)
    run_local.crop_audio({'audio': 'synthetic.m4a', 't0': 60, 'dur': 1, 'declared_language': 'en'}, output)
    context = read_context(output.read_bytes())
    assert context['stt_language'] == 'en'
    assert context['stt_language_evidence'] == 'declared'
    assert context['stt_language_confidence'] == 1.0


def test_private_artifact_root_rejects_git_checkout(tmp_path):
    from scripts.diarization_eval.local_artifacts import Artifacts

    (tmp_path / '.git').mkdir()
    with pytest.raises(ValueError, match='outside a Git checkout'):
        Artifacts(tmp_path / 'output')


@pytest.mark.parametrize('person', ['user', 'enrolled'])
def test_frozen_snapshot_reaches_real_persisted_projection_without_network(tmp_path, monkeypatch, no_network, person):
    from utils.stt.voice_centroids import COMMUNITY_MODEL_REVISION, EMBEDDING_MODEL, EMBEDDING_REVISION, EMBEDDING_SPACE

    monkeypatch.setenv('BATCH_PIPELINE_LOCAL_QUALITY_ENABLED', 'true')
    artifacts = local_artifacts.Artifacts(tmp_path)
    item = WorkItem('unit', 'synthetic-owner', 1700000000, 'unused', 8, Priority.DEEP)
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('unit',), record_origin=True)
    data = payload()
    data['diarization'].update(
        centroids={'raw-voice': {'embedding': [1, 0], 'evidence_seconds': 8}},
        embedding_space=EMBEDDING_SPACE,
        provenance={
            'model_revision': COMMUNITY_MODEL_REVISION,
            'embedding_model': EMBEDDING_MODEL,
            'embedding_revision': EMBEDDING_REVISION,
        },
    )
    uri = artifacts.persist_result(item, data)
    snapshot = local_artifacts.frozen_naming_snapshot({person: [1, 0]}, owner_id='synthetic-owner')
    turns = local_artifacts.project(artifacts, item, binding, uri, naming_snapshot=snapshot)
    assert [(s['is_user'], s['person_id']) for s in turns] == [(person == 'user', None if person == 'user' else person)]
    assert json.loads((tmp_path / 'projection/unit/part-0.json').read_text())['transcript_segments'] == turns


def test_external_projection_serializes_frozen_snapshot_privately(tmp_path, monkeypatch):
    from types import SimpleNamespace

    artifacts = local_artifacts.Artifacts(tmp_path)
    item = WorkItem('unit', 'synthetic-owner', 1700000000, 'unused', 8, Priority.DEEP)
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('unit',))
    snapshot = local_artifacts.frozen_naming_snapshot({'user': [1, 0]}, owner_id='synthetic-owner')

    def run(command, **kwargs):
        request = json.loads((tmp_path / 'projection-request.json').read_text())
        assert request['naming_snapshot']['owner_profile']['speaker_embedding'] == [1, 0]
        assert 'validate' not in request['naming_snapshot']
        assert (tmp_path / 'projection-request.json').stat().st_mode & 0o777 == 0o600
        assert not any('speaker_embedding' in str(arg) for arg in command)
        local_artifacts.private_json(tmp_path / 'projection-response.json', [])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(local_artifacts.subprocess, 'run', run)
    assert (
        local_artifacts.project_external('python', artifacts, item, binding, 'unused', naming_snapshot=snapshot) == []
    )


def test_relative_runpy_entrypoint_fingerprints_sources_before_model_loading(tmp_path, monkeypatch, no_network):
    import runpy

    root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(root)
    profile, people, manifest = tmp_path / 'profile.json', tmp_path / 'people.json', tmp_path / 'corpus.json'
    profile.write_text('{}')
    people.write_text('[]')
    manifest.write_text(json.dumps({'profile_file': str(profile), 'people_file': str(people), 'recordings': []}))
    # The standard torch-thread wrapper passes this relative spelling to runpy;
    # its __file__ stays relative even though ROOT was normalized at import.
    namespace = runpy.run_path('backend/scripts/diarization_eval/run_local.py', run_name='relative_eval_fixture')
    assert not Path(namespace['__file__']).is_absolute()
    report = namespace['evaluate'](manifest, run_name='relative-fixture')
    assert report['recordings_expected'] == 0
    assert report['cloud_inference_calls'] == 0
