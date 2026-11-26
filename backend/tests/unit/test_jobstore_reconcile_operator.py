"""Private operator state and admission contracts with synthetic providers only."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from database.jobstore import reconcile_operator as operator
from database.jobstore.reconcile import PageCounts, PageResult, _encode_cursor

NAMESPACE = 'batch_pipeline_prod'
TARGET = ('10.1.2.3', 'synthetic-jobstore', 'synthetic-runtime')
SECRET = 'private-cursor-or-provider-error-DO-NOT-PRINT'


@pytest.fixture
def production(monkeypatch):
    for name in ('FIRESTORE_EMULATOR_HOST', 'GCLOUD_PROJECT', 'GCP_PROJECT', 'FIREBASE_PROJECT_ID'):
        monkeypatch.delenv(name, raising=False)
    env = {
        'OMI_DEPLOYMENT': 'prod',
        'OMI_ENV_STAGE': 'prod',
        'GOOGLE_CLOUD_PROJECT': 'based-hardware',
        'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware',
        'OMI_FIRESTORE_DATA_PLANE_PROJECT': 'based-hardware',
        'FIRESTORE_DATABASE_ID': '(default)',
        'JOBSTORE_SHADOW_NAMESPACES': NAMESPACE,
        'JOBSTORE_PRODUCTION_MIRROR': 'on',
        'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '10000',
        'JOBSTORE_SHADOW_WRITES': 'on',
        'BATCH_JOBSTORE_MODE': 'shadow',
        'JOBSTORE_PG_HOST': TARGET[0],
        'JOBSTORE_PG_DATABASE': TARGET[1],
        'JOBSTORE_PG_USER': TARGET[2],
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


@pytest.fixture
def providers(monkeypatch):
    harness = SimpleNamespace(events=[], failure=None, page_hook=None, end=False)

    def primary(namespace):
        harness.events.append(('primary', namespace))
        return SimpleNamespace(namespace=namespace)

    def connector(*target):
        harness.events.append(('connector', target))
        return lambda: None

    class Pool:
        def __init__(self, *args, **kwargs):
            harness.events.append(('pool',))

        @contextmanager
        def connection(self, **kwargs):
            harness.events.append(('warm', kwargs))
            if harness.failure == 'startup':
                raise RuntimeError(SECRET)
            yield object()
            harness.events.append(('warmed',))

        def close(self):
            harness.events.append(('closed',))
            if harness.failure == 'close':
                raise RuntimeError(SECRET)

    def page(mirror, **kwargs):
        harness.events.append(('page', kwargs))
        assert any(event[0] == 'warmed' for event in harness.events)
        if harness.page_hook:
            harness.page_hook()
        if harness.failure in {'page', 'commit'}:
            raise RuntimeError(SECRET)
        cursor = None if harness.end else _encode_cursor(NAMESPACE, kwargs['source'], kwargs['table'], SECRET)
        return PageResult(PageCounts(scanned=1), harness.end, cursor)

    monkeypatch.setattr(operator, 'FirestoreStore', primary)
    monkeypatch.setattr(operator, 'iam_connector', connector)
    monkeypatch.setattr(operator, 'Pool', Pool)
    monkeypatch.setattr(
        operator, 'PostgresStore', lambda namespace, **kwargs: SimpleNamespace(namespace=namespace, **kwargs)
    )
    monkeypatch.setattr(operator, 'DualStore', lambda primary, shadow: SimpleNamespace(primary=primary, shadow=shadow))
    monkeypatch.setattr(operator, 'process_page', page)
    return harness


def _argv(path, source='copy', table='jobs', apply=False, **overrides):
    options = {
        'max-rows': '2',
        'max-primary-reads': '4',
        'max-statements': '100',
        'page-seconds': '1',
        **overrides,
    }
    args = [NAMESPACE, '--source', source, '--table', table, '--state-file', str(path)]
    args += [f'--{name}={value}' for name, value in options.items()]
    return args + (['--apply'] if apply else [])


def _scope(source='copy', table='jobs', apply=False, target=TARGET, namespace=NAMESPACE):
    return hashlib.sha256(json.dumps([target, namespace, source, table, apply]).encode()).hexdigest()


def _state(path, *, scope=None, cursor=None, passes=0, mode=0o600):
    value = {'version': 1, 'scope': scope or _scope(), 'cursor': cursor, 'passes': passes}
    path.write_text(json.dumps(value))
    path.chmod(mode)
    return value


def _assert_private_output(capsys):
    captured = capsys.readouterr()
    assert not captured.err
    assert SECRET not in captured.out
    assert all(value not in captured.out for value in TARGET)
    return [json.loads(line) for line in captured.out.splitlines()]


@pytest.mark.parametrize(
    ('name', 'value'),
    [
        ('OMI_DEPLOYMENT', 'dev'),
        ('OMI_ENV_STAGE', 'dev'),
        ('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev'),
        ('OMI_CUSTOMER_DATA_PROJECT', ''),
        ('OMI_FIRESTORE_DATA_PLANE_PROJECT', ''),
        ('FIRESTORE_DATABASE_ID', 'staging'),
        ('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080'),
        ('GCLOUD_PROJECT', 'wrong-project'),
    ],
)
def test_denied_production_context_never_constructs_clients(production, providers, tmp_path, capsys, name, value):
    production.setenv(name, value)
    assert operator.reconcile_main(_argv(tmp_path / 'state')) == 2
    assert providers.events == []
    assert _assert_private_output(capsys)[0]['outcome'] == 'refused'


@pytest.mark.parametrize('name', ['JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER'])
def test_partial_target_is_refused_before_any_connection(production, providers, tmp_path, capsys, name):
    production.delenv(name)
    assert operator.reconcile_main(_argv(tmp_path / 'state')) == 2
    assert providers.events == []
    _assert_private_output(capsys)


@pytest.mark.parametrize(
    'overrides',
    [
        {'max-rows': '0'},
        {'max-rows': '1001'},
        {'max-primary-reads': '0'},
        {'max-statements': '0'},
        {'max-statements': '-1'},
        {'page-seconds': '0'},
        {'page-seconds': '-1'},
        {'page-seconds': 'nan'},
        {'page-seconds': 'inf'},
        {'page-seconds': '-inf'},
    ],
)
def test_bad_budgets_are_refused_before_any_client(production, providers, tmp_path, capsys, overrides):
    assert operator.reconcile_main(_argv(tmp_path / 'state', **overrides)) == 2
    assert providers.events == []
    assert _assert_private_output(capsys)[0]['reason'] == 'invalid_budgets'


def test_primary_budget_must_cover_discovery_and_reread(production, providers, tmp_path, capsys):
    assert operator.reconcile_main(_argv(tmp_path / 'state', source='primary', **{'max-primary-reads': '1'})) == 2
    assert providers.events == []
    _assert_private_output(capsys)


def test_copy_retirement_is_available_with_all_writer_admission_kills_off(production, providers, tmp_path, capsys):
    for name, value in {
        'JOBSTORE_SHADOW_WRITES': 'off',
        'JOBSTORE_PRODUCTION_MIRROR': 'off',
        'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '0',
        'JOBSTORE_SHADOW_NAMESPACES': '',
        'BATCH_JOBSTORE_MODE': 'firestore',
    }.items():
        production.setenv(name, value)
    assert operator.reconcile_main(_argv(tmp_path / 'copy')) == 0
    assert any(event[0] == 'page' for event in providers.events)
    assert _assert_private_output(capsys)[0]['outcome'] == 'completed'
    providers.events.clear()
    assert operator.reconcile_main(_argv(tmp_path / 'primary', source='primary')) == 2
    assert providers.events == []
    _assert_private_output(capsys)


def test_staging_uses_existing_namespace_database_fence(production, providers, tmp_path, capsys):
    production.setenv('OMI_DEPLOYMENT', 'staging')
    production.setenv('FIRESTORE_DATABASE_ID', '(default)')
    assert operator.reconcile_main(_argv(tmp_path / 'state')) == 2
    assert providers.events == []
    production.setenv('FIRESTORE_DATABASE_ID', 'staging')
    assert operator.reconcile_main(_argv(tmp_path / 'state')) == 0
    _assert_private_output(capsys)


@pytest.mark.parametrize(
    'scope',
    [
        _scope(source='primary'),
        _scope(table='owners'),
        _scope(apply=True),
        _scope(target=('other', *TARGET[1:])),
        _scope(namespace='batch_pipeline_dev'),
    ],
)
def test_checkpoint_binds_source_table_target_namespace_and_apply(production, providers, tmp_path, capsys, scope):
    path = tmp_path / 'state'
    before = _state(path, scope=scope)
    assert operator.reconcile_main(_argv(path)) == 1
    assert json.loads(path.read_text()) == before
    assert providers.events == []
    _assert_private_output(capsys)


def test_dryrun_cannot_advance_the_apply_checkpoint(production, providers, tmp_path, capsys):
    path = tmp_path / 'state'
    assert operator.reconcile_main(_argv(path)) == 0
    before = path.read_bytes()
    providers.events.clear()
    assert operator.reconcile_main(_argv(path, apply=True)) == 1
    assert path.read_bytes() == before
    assert providers.events == []
    assert operator.reconcile_main(_argv(tmp_path / 'apply-state', apply=True)) == 0
    _assert_private_output(capsys)


@pytest.mark.parametrize(
    'kind', ['checkpoint_symlink', 'lock_symlink', 'checkpoint_perms', 'lock_perms', 'fifo', 'hardlink']
)
def test_unsafe_checkpoint_or_lock_is_refused_without_clients(production, providers, tmp_path, capsys, kind):
    path = tmp_path / 'state'
    external = tmp_path / 'external'
    external.write_text(SECRET)
    external.chmod(0o600)
    if kind == 'checkpoint_symlink':
        path.symlink_to(external)
    elif kind == 'lock_symlink':
        path.with_name('state.lock').symlink_to(external)
    elif kind == 'checkpoint_perms':
        _state(path, mode=0o644)
    elif kind == 'lock_perms':
        _state(path.with_name('state.lock'), mode=0o644)
    elif kind == 'fifo':
        os.mkfifo(path, 0o600)
    else:
        os.link(external, path)
    assert operator.reconcile_main(_argv(path)) == 1
    assert providers.events == []
    assert external.read_text() == SECRET
    _assert_private_output(capsys)


def test_state_owned_by_another_uid_is_refused(production, providers, tmp_path, monkeypatch, capsys):
    path = tmp_path / 'state'
    _state(path)
    original = operator.os.fstat

    def other_owner(fd):
        metadata = original(fd)
        return SimpleNamespace(st_mode=metadata.st_mode, st_uid=os.getuid() + 1, st_nlink=metadata.st_nlink)

    monkeypatch.setattr(operator.os, 'fstat', other_owner)
    assert operator.reconcile_main(_argv(path)) == 1
    assert providers.events == []
    _assert_private_output(capsys)


@pytest.mark.parametrize('payload', [b'[]', b'{', b'x' * 32769])
def test_malformed_or_oversized_state_is_bounded_before_connection(production, providers, tmp_path, capsys, payload):
    path = tmp_path / 'state'
    path.write_bytes(payload)
    path.chmod(0o600)
    assert operator.reconcile_main(_argv(path)) == 1
    assert providers.events == []
    _assert_private_output(capsys)


def test_cursor_format_and_embedded_scope_are_validated_before_clients(production, providers, tmp_path, capsys):
    path = tmp_path / 'state'
    for cursor in (SECRET, _encode_cursor(NAMESPACE, 'copy', 'owners', SECRET)):
        _state(path, cursor=cursor)
        assert operator.reconcile_main(_argv(path)) == 1
        assert providers.events == []
        _assert_private_output(capsys)


@pytest.mark.parametrize(
    'change',
    [{'version': True}, {'passes': True}, {'passes': -1}, {'cursor': 123}, {'cursor': 'x' * 16385}],
)
def test_checkpoint_schema_cannot_coerce_booleans_or_unbounded_cursors(production, providers, tmp_path, capsys, change):
    path = tmp_path / 'state'
    value = {**_state(path), **change}
    path.write_text(json.dumps(value))
    assert operator.reconcile_main(_argv(path)) == 1
    assert providers.events == []
    _assert_private_output(capsys)


def test_checkpoint_read_uses_open_descriptor_even_when_path_is_replaced(tmp_path, monkeypatch):
    path, replacement = tmp_path / 'state', tmp_path / 'replacement'
    expected = _state(path, passes=2)
    _state(replacement, passes=9)
    original = operator.os.fstat

    def replace_after_open(fd):
        metadata = original(fd)
        os.replace(replacement, path)
        return metadata

    monkeypatch.setattr(operator.os, 'fstat', replace_after_open)
    assert operator._checkpoint_read(path, _scope()) == expected
    assert json.loads(path.read_text())['passes'] == 9


@pytest.mark.parametrize('phase', ['startup', 'page', 'commit'])
def test_failed_startup_page_or_commit_preserves_cursor_and_retry_is_private(
    production, providers, tmp_path, capsys, phase
):
    path = tmp_path / 'state'
    cursor = _encode_cursor(NAMESPACE, 'copy', 'jobs', 'previous-sensitive-key')
    before = _state(path, cursor=cursor, passes=7)
    providers.failure = phase
    assert operator.reconcile_main(_argv(path)) == 1
    assert json.loads(path.read_text()) == before
    assert providers.events[-1] == ('closed',)
    assert _assert_private_output(capsys)[0]['outcome'] == 'retry_required'
    providers.failure = None
    providers.end = True
    assert operator.reconcile_main(_argv(path)) == 0
    page_call = [event for event in providers.events if event[0] == 'page'][-1]
    assert page_call[1]['cursor'] == cursor
    assert json.loads(path.read_text())['passes'] == 8
    assert _assert_private_output(capsys)[0]['passes'] == 8


def test_checkpoint_replace_failure_preserves_old_state_and_releases_lock(
    production, providers, tmp_path, monkeypatch, capsys
):
    path = tmp_path / 'state'
    before = _state(path, passes=4)
    original = operator.os.replace

    def fail_replace(*args):
        raise OSError(SECRET)

    monkeypatch.setattr(operator.os, 'replace', fail_replace)
    assert operator.reconcile_main(_argv(path)) == 1
    assert json.loads(path.read_text()) == before
    assert not list(tmp_path.glob('.jobstore-page-*'))
    _assert_private_output(capsys)
    monkeypatch.setattr(operator.os, 'replace', original)
    assert operator.reconcile_main(_argv(path)) == 0
    _assert_private_output(capsys)


def test_lock_refuses_concurrent_run_across_entire_page_and_checkpoint(production, providers, tmp_path, capsys):
    path = tmp_path / 'state'
    providers.end = True
    nested_results = []

    def concurrent_attempt():
        nested_results.append(operator.reconcile_main(_argv(path)))

    providers.page_hook = concurrent_attempt
    assert operator.reconcile_main(_argv(path)) == 0
    assert nested_results == [1]
    assert len([event for event in providers.events if event[0] == 'page']) == 1
    assert json.loads(path.read_text())['passes'] == 1
    reports = _assert_private_output(capsys)
    assert [row['outcome'] for row in reports] == ['retry_required', 'completed']
    inode = path.with_name('state.lock').stat().st_ino
    providers.page_hook = None
    assert operator.reconcile_main(_argv(path)) == 0
    assert path.with_name('state.lock').stat().st_ino == inode
    assert json.loads(path.read_text())['passes'] == 2
    _assert_private_output(capsys)


def test_lock_also_covers_checkpoint_read_and_atomic_write(production, providers, tmp_path, monkeypatch, capsys):
    path = tmp_path / 'state'
    checked = []
    original_read, original_write = operator._checkpoint_read, operator._checkpoint_write

    def assert_locked():
        with pytest.raises(BlockingIOError):
            with operator._checkpoint_lock(path):
                raise AssertionError('concurrent checkpoint lock acquired')

    def locked_read(*args):
        assert_locked()
        checked.append('read')
        return original_read(*args)

    def locked_write(*args):
        assert_locked()
        checked.append('write')
        return original_write(*args)

    monkeypatch.setattr(operator, '_checkpoint_read', locked_read)
    monkeypatch.setattr(operator, '_checkpoint_write', locked_write)
    assert operator.reconcile_main(_argv(path)) == 0
    assert checked == ['read', 'write']
    _assert_private_output(capsys)


def test_successful_checkpoint_is_atomic_private_and_reports_never_include_cursor(
    production, providers, tmp_path, capsys
):
    path = tmp_path / 'state'
    assert operator.reconcile_main(_argv(path)) == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    state = json.loads(path.read_text())
    assert state['cursor'] == _encode_cursor(NAMESPACE, 'copy', 'jobs', SECRET)
    report = _assert_private_output(capsys)[0]
    assert 'cursor' not in report
    assert report['counts']['scanned'] == 1
    assert providers.events[-1] == ('closed',)


def test_close_provider_error_cannot_leak_or_override_committed_report(production, providers, tmp_path, capsys):
    providers.failure = 'close'
    assert operator.reconcile_main(_argv(tmp_path / 'state')) == 0
    assert _assert_private_output(capsys)[0]['outcome'] == 'completed'
