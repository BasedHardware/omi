"""Two rule classes the lab keeps breaking, checked where they broke:

- private files stay under an owner-only lab root, created 0700, files 0600, and an existing group/other
  readable directory is refused rather than written into (``--keep``, ``--out``, the scenario lab root);
- stage keys cover what changes a stage's output: a staged rename or copy, mode-only and symlink edits, the raw
  baseline fields a missing timeline is built from, the ambient env the transcribe replay's product code reads,
  and the files an upstream stage wrote even when its own result was not stored.
"""

import json
import os
from pathlib import Path
import stat
import subprocess

import pytest

from testing.pipeline_lab import orchestrator, store as lab_store
from testing.pipeline_lab.affected import CodeState
from testing.pipeline_lab.lanes import plugin as lanes_plugin
from testing.pipeline_lab.registry import Registry
from testing.pipeline_lab.scenario import stack, verdict
from testing.pipeline_lab.scenario.home import HomeRecorder
from testing.pipeline_lab.scenario.spec import ScenarioError
from testing.pipeline_lab.store import Store, StoreRefused

LANES = ('ingest', 'transcribe', 'boundaries', 'speakers')


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ---- private files ----------------------------------------------------------------------------------


def test_keep_into_an_open_existing_directory_is_refused_not_chmodded(tmp_path):
    open_dir = tmp_path / 'shared'
    open_dir.mkdir()
    os.chmod(open_dir, 0o755)
    with pytest.raises(ScenarioError, match='group/other'):
        stack.output_root(str(open_dir))
    assert mode(open_dir) == 0o755  # left as it was: it may be someone else's tree


def test_keep_creates_owner_only_and_default_output_is_under_the_private_lab_root(tmp_path, monkeypatch):
    kept = stack.output_root(str(tmp_path / 'a' / 'b'))
    assert mode(kept) == 0o700 and mode(tmp_path / 'a') == 0o700
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(tmp_path / 'labroot'))
    default = stack.output_root(None)
    assert default.parent == tmp_path / 'labroot' / 'scenario-runs'
    assert mode(tmp_path / 'labroot') == 0o700 and mode(default) == 0o700


def test_scenario_lab_root_default_cache_dir_is_created_owner_only(tmp_path, monkeypatch):
    from testing.pipeline_lab.scenario import paths

    monkeypatch.delenv('OMI_PIPELINE_LAB_ROOT', raising=False)
    monkeypatch.setattr('testing.pipeline_lab.stack.config.DEFAULT_LAB_ROOT', str(tmp_path / 'absent'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    root = paths.private_lab_root()
    assert root == tmp_path / 'cache' / 'pipeline-lab'
    assert mode(root) == 0o700 and mode(tmp_path / 'cache') == 0o700
    os.chmod(root, 0o755)  # the lab's own default directory, made open by an older lab: tightened
    assert paths.private_lab_root() == root and mode(root) == 0o700
    configured = tmp_path / 'configured'
    configured.mkdir()
    os.chmod(configured, 0o755)
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(configured))
    with pytest.raises(StoreRefused, match='group/other'):  # the operator's choice: refused, not changed
        paths.private_lab_root()
    assert mode(configured) == 0o755


def test_reused_scenario_directory_must_be_owner_only(tmp_path):
    root = stack.output_root(str(tmp_path / 'run'))
    (root / 'one').mkdir(mode=0o755)
    os.chmod(root / 'one', 0o755)
    with pytest.raises(ScenarioError, match='group/other'):
        stack._private(root / 'one', 'scenario output')


def test_home_json_result_files_and_verdicts_are_0600(tmp_path):
    out = lab_store.private_dir(tmp_path / 'out')
    home = HomeRecorder(uid='local-dev-user', out_dir=out, offset=lambda _: 0.0, now=lambda: None)
    path = home.write()
    assert path == out / 'home.json' and mode(path) == 0o600
    verdict.write_json(out / 'verdict.json', {'outcome': 'pass'})
    assert mode(out / 'verdict.json') == 0o600
    with lab_store.private_open(out / 'firestore.log') as log:
        log.write(b'x')
    assert mode(out / 'firestore.log') == 0o600


def test_scenario_child_refuses_an_open_out_directory(tmp_path, monkeypatch, capsys):
    from testing.pipeline_lab.scenario import run as scenario_run

    open_dir = tmp_path / 'open'
    open_dir.mkdir()
    os.chmod(open_dir, 0o777)
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:1')
    previous = os.umask(0o022)
    try:
        code = scenario_run.main(['--file', 'unused.json', '--out', str(open_dir)])
    finally:
        os.umask(previous)
    assert code != 0 and 'group/other' in capsys.readouterr().out
    assert mode(open_dir) == 0o777 and not list(open_dir.iterdir())


def test_private_subdirectories_create_every_missing_parent_0700(tmp_path):
    base = lab_store.ensure_private_dir(tmp_path / 'root')
    previous = os.umask(0o022)
    try:
        lab_store.atomic_write_bytes(base / 'cache' / 'stage' / 'ab' / 'k.json', b'{}')
    finally:
        os.umask(previous)
    for directory in (base / 'cache', base / 'cache' / 'stage', base / 'cache' / 'stage' / 'ab'):
        assert mode(directory) == 0o700, directory
    assert mode(base / 'cache' / 'stage' / 'ab' / 'k.json') == 0o600


def test_inspector_verdict_root_is_validated(tmp_path):
    from testing.pipeline_lab.inspector.reader import BadRequest, Reader

    store_root = lab_store.ensure_private_dir(tmp_path / 'store')
    open_root = tmp_path / 'verdicts'
    open_root.mkdir()
    os.chmod(open_root, 0o755)
    with pytest.raises(BadRequest, match='verdict root'):
        Reader(store_root, open_root).append_verdict({'id': 'v-1'})
    fresh = tmp_path / 'deep' / 'verdicts'
    Reader(store_root, fresh).append_verdict({'id': 'v-1'})
    assert mode(tmp_path / 'deep') == 0o700 and mode(fresh) == 0o700
    assert mode(fresh / 'verdicts.jsonl') == 0o600


# ---- code keys: git status cases ------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't'}
    env['GIT_COMMITTER_EMAIL'] = 't@t'
    return subprocess.run(['git', *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def repo(tmp_path):
    path = tmp_path / 'repo'
    (path / 'backend').mkdir(parents=True)
    (path / 'backend' / 'a.py').write_text('A = 1\n')
    _git(path, 'init', '-q')
    _git(path, 'add', '-A')
    _git(path, 'commit', '-q', '-m', 'base')
    return path


def test_staged_rename_keys_differently_from_an_added_copy(repo, tmp_path):
    other = tmp_path / 'other'
    _git(tmp_path, 'clone', '-q', str(repo), str(other))

    (repo / 'backend' / 'b.py').write_text('A = 1\n')  # add new file, keep the original
    _git(repo, 'add', '-A')
    _git(other, 'mv', 'backend/a.py', 'backend/b.py')  # rename the original to the new file
    added, renamed = CodeState(repo), CodeState(other)
    assert renamed.dirty['backend/a.py'] == 'deleted'
    assert added.dirty != renamed.dirty and added.tree_key() != renamed.tree_key()
    assert renamed.blobs['backend/a.py'] == 'deleted'


def test_mode_only_and_symlink_edits_change_the_code_key(repo):
    clean = CodeState(repo).tree_key()
    os.chmod(repo / 'backend' / 'a.py', 0o755)
    executable = CodeState(repo)
    assert executable.dirty['backend/a.py'].endswith(':x') and executable.tree_key() != clean
    os.chmod(repo / 'backend' / 'a.py', 0o644)
    (repo / 'backend' / 'link.py').symlink_to('a.py')
    first = CodeState(repo).dirty['backend/link.py']
    (repo / 'backend' / 'link.py').unlink()
    (repo / 'backend' / 'other.py').write_text('A = 1\n')
    (repo / 'backend' / 'link.py').symlink_to('other.py')  # same content, another target
    assert first.startswith('symlink:') and CodeState(repo).dirty['backend/link.py'] != first


def test_nested_repository_contents_are_part_of_the_code_key(repo):
    nested = repo / 'backend' / 'vendored'
    nested.mkdir()
    (nested / 'm.py').write_text('X = 1\n')
    _git(nested, 'init', '-q')
    first = CodeState(repo).dirty['backend/vendored']
    (nested / 'm.py').write_text('X = 2\n')
    assert first.startswith('dir:') and CodeState(repo).dirty['backend/vendored'] != first


# ---- stage keys ---------------------------------------------------------------------------------------------


def _replay_writer(calls, text):
    """Stands in for the transcribe replay: one transcript and one transient (VAD) failure, so the result is
    refused storage; ``text`` is what the transcript says this time."""
    from testing.pipeline_lab.lanes.output import IngestResult, write_results

    def main(argv):
        calls.append(argv)
        run_id = argv[argv.index('--run') + 1]
        write_results(
            run_id,
            [
                IngestResult('conv-1', 'record', None, None, 'transcript', segments=[{'start': 0.0, 'text': text[0]}]),
                IngestResult('conv-2', 'sync', None, None, 'failed', error='vad_error'),
            ],
        )
        return 0

    return main


@pytest.fixture()
def audio_day(tmp_path, monkeypatch):
    from testing.pipeline_lab.contracts import AudioIndexEntry, CorpusDay
    from testing.pipeline_lab.lanes import __main__ as lanes_main

    root = tmp_path / 'store'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    store = Store.open(root, tmp_path / 'verdicts')
    store.write_day(CorpusDay(day_id='d1', date='2026-01-02', timezone='UTC'))
    store.write_audio_index(
        'd1',
        [AudioIndexEntry('conv-1', 'conv-1.wav', '2026-01-02T10:00:00Z', '2026-01-02T10:00:20Z', 'pcm', 16000)],
    )
    (store.audio_dir('d1') / 'conv-1.wav').write_bytes(b'RIFF' + b'\0' * 64)
    (store.day_dir('d1') / 'timeline.json').write_text(json.dumps({'coverage': {'with_audio': 1}, 'conversations': []}))
    calls, text = [], ['first']
    monkeypatch.setattr(lanes_main, 'main', _replay_writer(calls, text))
    registry = Registry()
    lanes_plugin.register(registry)
    return {'store': store, 'registry': registry, 'calls': calls, 'text': text}


def _lanes(audio_day):
    request = orchestrator.RunRequest(
        day_id='d1',
        ref='HEAD',
        overlay={'model_config': {'stt': {'provider': 'stub', 'model': 'stub-1'}}},
        stages=list(LANES),
    )
    outcome = orchestrator.run_pipeline(audio_day['store'], request, audio_day['registry'], backend_tree='t' * 40)
    assert outcome.exit_code == 0, outcome.error
    return outcome.run


def test_refused_upstream_result_still_keys_downstream_on_its_artifacts(audio_day):
    first = _lanes(audio_day)
    assert first.stages['transcribe'].extra['report']['cache'] == 'off'  # transient failure: not stored
    assert first.stages['boundaries'].extra['report']['cache'] == 'miss'
    audio_day['text'][0] = 'second'  # the replay produced another transcript; the outcome counts are the same
    second = _lanes(audio_day)
    assert len(audio_day['calls']) == 2
    assert second.stages['boundaries'].extra['key'] != first.stages['boundaries'].extra['key']
    assert second.stages['boundaries'].extra['report']['cache'] == 'miss'
    audio_day['text'][0] = 'second'  # the same transcript again: downstream may be served
    third = _lanes(audio_day)
    assert third.stages['boundaries'].extra['key'] == second.stages['boundaries'].extra['key']
    assert third.stages['boundaries'].extra['report']['cache'] == 'hit'


def test_ingest_keys_follow_the_raw_rows_a_missing_timeline_is_built_from(tmp_path):
    from types import SimpleNamespace

    store = Store.open(tmp_path / 'store', tmp_path / 'verdicts')
    baseline = store.baseline_dir('d1')
    lab_store.private_subdir(baseline)
    (baseline / 'conversations.jsonl').write_text('{"id": "c1"}\n')
    raw = baseline / 'raw_conversations.jsonl'
    raw.write_text('{"id": "c1", "source": "omi", "transcript_segments": [{"text": "a"}]}\n')
    ctx = SimpleNamespace(store=store, day=SimpleNamespace(day_id='d1'))
    first = lanes_plugin.IngestStage().inputs(ctx)
    raw.write_text('{"id": "c1", "source": "omi", "transcript_segments": [{"text": "b"}]}\n')
    assert lanes_plugin.IngestStage().inputs(ctx) == first  # transcript text: not a timeline input
    raw.write_text('{"id": "c1", "source": "sdcard", "transcript_segments": [{"text": "b"}]}\n')
    assert lanes_plugin.IngestStage().inputs(ctx) != first  # moves the conversation to the sync lane


@pytest.mark.slow  # walks the transcribe stage's import closure; near the fast-unit CPU limit
def test_transcribe_keys_the_ambient_env_its_product_code_reads(monkeypatch):
    code = CodeState(Path(__file__).resolve().parents[3])
    names = 'BATCH_PIPELINE_DIARIZER'
    monkeypatch.delenv(names, raising=False)
    base = code.ambient_env(['transcribe'])
    monkeypatch.setenv(names, 'other')
    assert code.ambient_env(['transcribe']) != base
    assert code.ambient_env(['transcribe'], overlay=[names]) == base  # the overlay's value is keyed there
    monkeypatch.setenv('PIPELINE_LAB_UNREAD_NAME', 'x')
    assert code.ambient_env(['transcribe'], overlay=[names]) == base
    assert getattr(lanes_plugin.TranscribeStage(), 'ambient_env', False)
