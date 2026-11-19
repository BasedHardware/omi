"""scripts/sweep_agent_vm_firestore.py: explicit project identity and write accounting.

The sweep is operator-run and irreversible, so the synthetic contract here is the
receipt, not the SDK: the run must name its project, refuse a client pinned
elsewhere, and never report a queued batch operation as committed when the batch
failed.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import create_autospec

import pytest

from scripts import sweep_agent_vm_firestore as sweep

PROJECT = 'based-hardware'


class _Ref:
    def __init__(self, path: str) -> None:
        self.path = path


class _Snapshot:
    def __init__(self, path: str, data: dict[str, Any]) -> None:
        self.reference = _Ref(path)
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _Batch:
    def __init__(self, db: _Db) -> None:
        self.db = db
        self.ops: list[tuple[str, str, dict[str, Any] | None]] = []

    def update(self, ref: _Ref, data: dict[str, Any]) -> None:
        self.ops.append(('update', ref.path, data))

    def delete(self, ref: _Ref) -> None:
        self.ops.append(('delete', ref.path, None))

    def commit(self) -> None:
        if self.db.fail_next_commits:
            self.db.fail_next_commits -= 1
            raise RuntimeError('commit unavailable')
        self.db.commits.append(list(self.ops))
        self.db.committed_ops += len(self.ops)


class _Query:
    def __init__(self, docs: list[_Snapshot]) -> None:
        self._docs = docs
        self._after: _Snapshot | None = None
        self._size = sweep.PAGE_SIZE

    def order_by(self, _field: str) -> _Query:
        return self

    def limit(self, size: int) -> _Query:
        self._size = size
        return self

    def start_after(self, doc: _Snapshot) -> _Query:
        self._after = doc
        return self

    def stream(self) -> list[_Snapshot]:
        start = 0 if self._after is None else self._docs.index(self._after) + 1
        return self._docs[start : start + self._size]


class _Stream:
    def __init__(self, docs: list[_Snapshot]) -> None:
        self._docs = docs

    def stream(self) -> list[_Snapshot]:
        return list(self._docs)


class _Db:
    def __init__(self, project: str, docs: dict[str, list[_Snapshot]] | None = None) -> None:
        self.project = project
        self.docs = docs or {}
        self.batches: list[_Batch] = []
        self.commits: list[list[tuple[str, str, dict[str, Any] | None]]] = []
        self.committed_ops = 0
        self.fail_next_commits = 0

    def batch(self) -> _Batch:
        batch = _Batch(self)
        self.batches.append(batch)
        return batch

    def collection(self, name: str) -> Any:
        docs = self.docs.get(name, [])
        return _Collection(docs)

    def collection_group(self, name: str) -> _Stream:
        return _Stream(self.docs.get(name, []))


class _Collection:
    def __init__(self, docs: list[_Snapshot]) -> None:
        self._docs = docs

    def order_by(self, _field: str) -> _Query:
        return _Query(self._docs)

    def limit(self, size: int) -> _Query:
        return _Query(self._docs).limit(size)

    def stream(self) -> list[_Snapshot]:
        return list(self._docs)


class _FakeFs:
    DELETE_FIELD = object()

    def __init__(self, db: _Db) -> None:
        self.db = db
        self.requested_projects: list[str] = []

    def client(self, app=None) -> _Db:
        self.requested_projects.append(app['projectId'])
        return self.db


class _FakeFirebaseAdmin:
    def __init__(self) -> None:
        self._apps: list[object] = []

    def initialize_app(self, credential=None, options=None, name='[DEFAULT]') -> dict[str, str]:
        self._apps.append(options)
        return options


def _users(*specs: tuple[str, dict[str, Any]]) -> dict[str, list[_Snapshot]]:
    return {
        sweep.USERS: [_Snapshot(f'{sweep.USERS}/{uid}', data) for uid, data in specs],
    }


def _run_main(monkeypatch, fake_fs: _FakeFs, argv: list[str]) -> int:
    monkeypatch.setattr(sweep, 'fa', _FakeFirebaseAdmin())
    monkeypatch.setattr(sweep, 'fs', fake_fs)
    monkeypatch.setattr(sys, 'argv', ['sweep_agent_vm_firestore.py', '--project', PROJECT, *argv])
    return sweep.main()


def test_project_selection_is_required(monkeypatch):
    fake_fs = _FakeFs(_Db(PROJECT))
    monkeypatch.setattr(sweep, 'fa', _FakeFirebaseAdmin())
    monkeypatch.setattr(sweep, 'fs', fake_fs)
    monkeypatch.setattr(sys, 'argv', ['sweep_agent_vm_firestore.py', '--apply'])
    with pytest.raises(SystemExit) as refused:
        sweep.main()
    assert refused.value.code == 2
    assert fake_fs.requested_projects == []


def test_unexpected_client_binding_is_defensively_refused_before_data_io(monkeypatch, capsys):
    # Fault-injected SDK boundary: the real pinned SDK derives db.project from
    # app.options.projectId. This does not simulate credential-project discovery.
    db = _Db('some-compute-project', _users(('u1', {'agentVm': {'state': 'running'}})))
    fake_fs = _FakeFs(db)
    code = _run_main(monkeypatch, fake_fs, ['--apply'])
    assert code == 2
    assert fake_fs.requested_projects == [PROJECT]
    assert db.batches == []
    assert db.committed_ops == 0
    err = capsys.readouterr().err
    assert 'REFUSED' in err
    assert 'some-compute-project' in err


def test_dry_run_receipt_names_project_and_writes_nothing(monkeypatch, capsys):
    db = _Db(PROJECT, _users(('u1', {'agentVm': {'state': 'running'}}), ('u2', {'anonymous': True})))
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', 'users']) == 0
    out = capsys.readouterr().out
    assert 'DRY-RUN project=based-hardware target=users' in out
    assert 'matched=1 queued=0 committed=0' in out
    assert 'failed_batches=0' in out
    assert 'TOTAL' in out
    assert db.committed_ops == 0
    assert all(not batch.ops for batch in db.batches)


def test_full_batches_report_every_operation_as_committed(monkeypatch, capsys):
    monkeypatch.setattr(sweep, 'BATCH_LIMIT', 2)
    db = _Db(PROJECT, _users(*[(f'u{i}', {'agentVm': {}}) for i in range(3)]))
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', 'users', '--apply']) == 0
    out = capsys.readouterr().out
    assert 'matched=3 queued=3 committed=3 failed_ops=0 failed_batches=0' in out
    assert [len(commit) for commit in db.commits] == [2, 1]


def test_failed_batch_is_reported_as_queued_but_not_committed(monkeypatch, capsys):
    monkeypatch.setattr(sweep, 'BATCH_LIMIT', 2)
    db = _Db(PROJECT, _users(*[(f'u{i}', {'agentVm': {}}) for i in range(3)]))
    db.fail_next_commits = 1
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', 'users', '--apply']) == 1
    captured = capsys.readouterr()
    assert 'matched=3 queued=3 committed=1 failed_ops=2 failed_batches=1' in captured.out
    assert 'project=based-hardware batch commit failed (2 ops)' in captured.err
    assert 'INCOMPLETE project=based-hardware' in captured.err
    assert db.committed_ops == 1
    assert [len(commit) for commit in db.commits] == [1]


def test_marker_target_uses_the_same_project_and_commit_accounting(monkeypatch, capsys):
    monkeypatch.setattr(sweep, 'BATCH_LIMIT', 2)
    db = _Db(
        PROJECT,
        {
            sweep.ACCOUNT_DELETIONS: [
                _Snapshot(f'{sweep.ACCOUNT_DELETIONS}/a', {'late_agent_vm_cleanup': {'state': 'pending'}}),
                _Snapshot(f'{sweep.ACCOUNT_DELETIONS}/b', {'wipe_status': 'running'}),
            ]
        },
    )
    db.fail_next_commits = 1
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', 'markers', '--apply']) == 1
    out = capsys.readouterr().out
    assert 'APPLIED project=based-hardware target=markers scanned=2 matched=1' in out
    assert 'queued=1 committed=0 failed_ops=1 failed_batches=1' in out


def test_project_binding_uses_the_installed_firebase_admin_sdk_signatures(monkeypatch):
    app = object()
    db = _Db(PROJECT)
    initialize_app = create_autospec(sweep.fa.initialize_app, return_value=app)
    client = create_autospec(sweep.fs.client, return_value=db)
    monkeypatch.setattr(sweep.fa, 'initialize_app', initialize_app)
    monkeypatch.setattr(sweep.fs, 'client', client)
    monkeypatch.setattr(sys, 'argv', ['sweep_agent_vm_firestore.py', '--project', PROJECT, '--target', 'users'])

    assert sweep.main() == 0
    initialize_app.assert_called_once_with(options={'projectId': PROJECT}, name='agent-vm-retirement-sweep')
    client.assert_called_once_with(app=app)


def _target_docs(target: str, count: int) -> dict[str, list[_Snapshot]]:
    paths = {
        'users': ('users/u{}', {'agentVm': {}, 'retained': True}),
        'migrations': ('users/u{}/agentVmMigrations/migration', {'retained': True}),
        'markers': ('account_deletions/u{}', {'late_agent_vm_cleanup': {}, 'wipe_status': 'running'}),
        'leases': ('agent_vm_reconciler_leases/lease{}', {'retained': True}),
    }
    path, data = paths[target]
    collection = {'markers': sweep.ACCOUNT_DELETIONS, 'migrations': sweep.MIGRATIONS}.get(target, target)
    if target == 'leases':
        collection = sweep.LEASES
    return {collection: [_Snapshot(path.format(i), data) for i in range(count)]}


@pytest.mark.parametrize('applied', [False, True])
def test_migration_target_preserves_other_parents_and_nested_names(monkeypatch, capsys, applied):
    paths = [
        'agentVmMigrations/root',
        'projects/project/agentVmMigrations/foreign',
        'users/u1/other/child/agentVmMigrations/nested',
        'users/u1/agentVmMigrations/parent/agentVmMigrations/nested',
        'users//agentVmMigrations/empty-user',
        'users/u1/agentVmMigrations/first',
        'users/u2/agentVmMigrations/second',
    ]
    db = _Db(PROJECT, {sweep.MIGRATIONS: [_Snapshot(p, {}) for p in paths]})
    args = ['--target', 'migrations', *(['--apply'] if applied else [])]
    assert _run_main(monkeypatch, _FakeFs(db), args) == 0
    out = capsys.readouterr().out
    assert 'target=migrations scanned=7 matched=2' in out
    expected = [('delete', path, None) for path in paths[-2:]]
    assert db.commits == ([expected] if applied else [])
    assert all(path not in out for path in paths)


@pytest.mark.parametrize('target', sweep.TARGETS)
@pytest.mark.parametrize('applied', [False, True])
def test_negative_limit_is_rejected_before_firebase_setup(monkeypatch, target, applied):
    admin = _FakeFirebaseAdmin()
    db = _Db(PROJECT, _target_docs(target, 2))
    fake_fs = _FakeFs(db)
    monkeypatch.setattr(sweep, 'fa', admin)
    monkeypatch.setattr(sweep, 'fs', fake_fs)
    monkeypatch.setattr(
        sys,
        'argv',
        ['sweep_agent_vm_firestore.py', '--project', PROJECT, '--target', target, '--limit', '-1']
        + (['--apply'] if applied else []),
    )
    with pytest.raises(SystemExit) as refused:
        sweep.main()
    assert refused.value.code == 2
    assert admin._apps == []
    assert fake_fs.requested_projects == []
    assert db.batches == []


@pytest.mark.parametrize('target', sweep.TARGETS)
@pytest.mark.parametrize('applied', [False, True])
@pytest.mark.parametrize('limit,count', [(0, 0), (0, 2), (3, 0), (3, 2)])
def test_exhausted_targets_report_scan_and_operation_complete(monkeypatch, capsys, target, applied, limit, count):
    db = _Db(PROJECT, _target_docs(target, count))
    args = ['--target', target, '--limit', str(limit), *(['--apply'] if applied else [])]
    assert _run_main(monkeypatch, _FakeFs(db), args) == 0
    out = capsys.readouterr().out
    assert f'target={target} scanned={count} matched={count}' in out
    assert out.count('scan_complete=1 complete=1') == 2  # Target and selected-target TOTAL.
    assert db.committed_ops == (count if applied else 0)


@pytest.mark.parametrize('target', sweep.TARGETS)
@pytest.mark.parametrize('applied', [False, True])
@pytest.mark.parametrize('count', [1, 2])
def test_reaching_limit_cannot_certify_completion(monkeypatch, capsys, target, applied, count):
    db = _Db(PROJECT, _target_docs(target, count))
    args = ['--target', target, '--limit', '1', *(['--apply'] if applied else [])]
    assert _run_main(monkeypatch, _FakeFs(db), args) == 1
    captured = capsys.readouterr()
    assert f'target={target} scanned=1 matched=1' in captured.out
    assert captured.out.count('scan_complete=0 complete=0') == 2
    assert 'INCOMPLETE project=based-hardware' in captured.err
    assert db.committed_ops == (1 if applied else 0)


@pytest.mark.parametrize('target', ['users', 'migrations', 'markers'])
def test_capped_zero_match_is_not_a_zero_state_proof(monkeypatch, capsys, target):
    docs = _target_docs(target, 1)
    key = next(iter(docs))
    prefix = 'projects/other/agentVmMigrations/foreign' if target == 'migrations' else f'{key}/unmatched'
    docs[key].insert(0, _Snapshot(prefix, {'retained': True}))
    db = _Db(PROJECT, docs)
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', target, '--limit', '1', '--apply']) == 1
    captured = capsys.readouterr()
    assert f'target={target} scanned=1 matched=0 queued=0 committed=0' in captured.out
    assert 'scan_complete=0 complete=0' in captured.out
    assert db.commits == []


def test_total_cannot_hide_a_partial_target(monkeypatch, capsys):
    db = _Db(PROJECT, _target_docs('users', 2))
    assert _run_main(monkeypatch, _FakeFs(db), ['--limit', '1']) == 1
    captured = capsys.readouterr()
    total = next(line for line in captured.out.splitlines() if 'target=TOTAL ' in line)
    assert 'scan_complete=0 complete=0' in total
    assert 'scan_complete=1 complete=1' in captured.out  # Other targets really exhausted.


@pytest.mark.parametrize('target', sweep.TARGETS)
def test_commit_failure_does_not_erase_scan_exhaustion_or_claim_completion(monkeypatch, capsys, target):
    db = _Db(PROJECT, _target_docs(target, 2))
    db.fail_next_commits = 1
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', target, '--apply']) == 1
    out = capsys.readouterr().out
    assert 'matched=2 queued=2 committed=0 failed_ops=2 failed_batches=1' in out
    assert out.count('scan_complete=1 complete=0') == 2


@pytest.mark.parametrize('has_vm', [False, True])
def test_user_update_removes_only_declared_retired_fields(monkeypatch, has_vm):
    fields = (*sweep.LEGACY_USER_FIELDS, *(['agentVm'] if has_vm else []))
    data = {**dict.fromkeys(fields, 1), 'profile': {'retained': True}}
    db = _Db(PROJECT, _users(('u1', data)))
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', 'users', '--apply']) == 0
    assert db.commits == [[('update', 'users/u1', dict.fromkeys(fields, sweep.fs.DELETE_FIELD))]]


def test_marker_update_preserves_status_and_wipe_fields(monkeypatch):
    db = _Db(PROJECT, _target_docs('markers', 1))
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', 'markers', '--apply']) == 0
    assert db.commits == [[('update', 'account_deletions/u0', {'late_agent_vm_cleanup': sweep.fs.DELETE_FIELD})]]


@pytest.mark.parametrize('target', ['migrations', 'leases'])
def test_stream_cap_does_not_pull_an_extra_document(monkeypatch, target):
    docs = next(iter(_target_docs(target, 2).values()))
    pulled = []

    class ObservedStream:
        def stream(self):
            for doc in docs:
                pulled.append(doc.reference.path)
                yield doc

    db = _Db(PROJECT)
    monkeypatch.setattr(
        db, 'collection_group' if target == 'migrations' else 'collection', lambda _name: ObservedStream()
    )
    assert _run_main(monkeypatch, _FakeFs(db), ['--target', target, '--limit', '1']) == 1
    assert pulled == [docs[0].reference.path]
