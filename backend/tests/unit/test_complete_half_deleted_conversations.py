"""The half-deleted cleanup tool only mutates the exact runtime plane it scanned."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import complete_half_deleted_conversations as cleanup


@pytest.fixture
def runtime(monkeypatch):
    client = MagicMock()
    client.project = 'plane-a'
    client._database = '(default)'
    client.collection.return_value.select.return_value.stream.return_value = []
    monkeypatch.setenv('PINECONE_INDEX_NAME', 'index-a')
    monkeypatch.setattr(cleanup, 'runtime_client', lambda: client)
    monkeypatch.setattr(cleanup, 'route_client_project', lambda: 'plane-a')
    monkeypatch.setattr(
        cleanup, 'scan', lambda *a: iter([('u1', 'live-1', 'live'), ('u1', 'gone-1', 'gone'), ('u2', 'live-2', 'live')])
    )
    deleted = []
    monkeypatch.setattr(cleanup, 'complete_with_route', lambda uid, cid: deleted.append((uid, cid)))
    monkeypatch.setattr(cleanup, 'tombstone_exists', lambda _client, uid, cid: cid != 'live-2')
    monkeypatch.setattr(cleanup.time, 'sleep', lambda seconds: None)
    return SimpleNamespace(
        client=client, deleted=deleted, digest=cleanup.runtime_digest(cleanup.runtime_bindings(client))
    )


def test_dry_run_reports_counts_and_the_runtime_digest(runtime, capsys):
    assert cleanup.main([]) == 0
    out = capsys.readouterr().out
    assert f'runtime_digest={runtime.digest}' in out
    assert '"firestore_project": "plane-a"' in out and '"pinecone_index": "index-a"' in out
    assert 'conversation_live=2' in out and 'accounts_with_live_leftovers=2' in out
    assert runtime.deleted == []


def test_execute_refuses_a_standalone_project_scan(runtime, monkeypatch):
    standalone = MagicMock()
    monkeypatch.setattr(cleanup.firestore, 'Client', standalone)
    assert cleanup.main(['--project', 'plane-a', '--execute', '--confirm-runtime', runtime.digest]) == 2
    standalone.assert_not_called()
    assert runtime.deleted == []


@pytest.mark.parametrize('confirm', [None, 'deadbeefdeadbeef'])
def test_execute_refuses_without_the_matching_runtime_digest(runtime, confirm):
    argv = ['--execute'] + (['--confirm-runtime', confirm] if confirm else [])
    assert cleanup.main(argv) == 2
    assert runtime.deleted == []


def test_execute_refuses_when_a_binding_changed_since_the_dry_run(runtime, monkeypatch):
    monkeypatch.setenv('PINECONE_INDEX_NAME', 'index-b')  # vector plane moved after the reviewed dry run
    assert cleanup.main(['--execute', '--confirm-runtime', runtime.digest]) == 2
    assert runtime.deleted == []


def test_execute_refuses_when_the_route_resolves_another_project(runtime, monkeypatch):
    monkeypatch.setattr(cleanup, 'route_client_project', lambda: 'plane-b')
    assert cleanup.main(['--execute', '--confirm-runtime', runtime.digest]) == 2
    assert runtime.deleted == []


def test_execute_completes_live_leftovers_after_re_reading_their_tombstones(runtime, capsys):
    assert cleanup.main(['--execute', '--confirm-runtime', runtime.digest]) == 0
    assert runtime.deleted == [('u1', 'live-1')]
    out = capsys.readouterr().out
    assert 'completed_via_route=1' in out and 'skipped_tombstone_missing=1' in out


def test_execute_exits_nonzero_when_a_completion_fails(runtime, monkeypatch):
    monkeypatch.setattr(cleanup, 'complete_with_route', MagicMock(side_effect=RuntimeError('busy')))
    assert cleanup.main(['--execute', '--confirm-runtime', runtime.digest]) == 1
