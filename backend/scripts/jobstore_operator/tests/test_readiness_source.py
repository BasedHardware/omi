# LIFECYCLE: permanent
"""Discriminators for real cleanliness checks and fixed failure-stage evidence."""

import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT.parents[1]))
from readiness_contract import CONTRACT
from testing.import_isolation import AutoMockModule, stub_modules

readiness = None


def unexpected_sdk_call(*args, **kwargs):
    raise AssertionError('PORTABLE_CONTROL_MUST_NOT_CALL_SDK')


def setUpModule():
    # Discovery stays pure. SDK substitution is confined to this test fixture,
    # through the sanctioned helper that restores modules and parent attributes.
    global readiness
    modules = {
        name: AutoMockModule(name)
        for name in (
            'google',
            'google.auth',
            'google.auth.compute_engine',
            'google.auth.compute_engine.credentials',
            'psycopg',
        )
    }
    modules['google.auth'].default = unexpected_sdk_call
    modules['google.auth.compute_engine.credentials'].Credentials = unexpected_sdk_call
    modules['psycopg'].connect = unexpected_sdk_call
    spec = importlib.util.spec_from_file_location('portable_readiness_under_test', ROOT / 'runner_readiness.py')
    with stub_modules(modules):
        readiness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(readiness)


def tearDownModule():
    global readiness
    readiness = None


EXPECTED = CONTRACT['migrations']
HOLD_KEYS = {
    'result',
    'failure_class',
    'failure_stage',
    'failure_stage_elapsed_ms',
    'customer_rows_read',
    'state_initialized',
    'write_attempted',
}


class CollectionTests(unittest.TestCase):
    def test_discovery_never_substitutes_sdk_modules_or_loads_runner(self):
        program = f'''
import sys,pathlib,unittest.mock as mock
sys.path.insert(0, {str(ROOT.parents[1])!r})
import testing.import_isolation as isolation
path=pathlib.Path({str(Path(__file__).resolve())!r})
before={{k:v for k,v in sys.modules.items() if k=='google' or k.startswith('google.') or k=='psycopg'}}
namespace={{'__file__':str(path),'__name__':'collection_only'}}
with mock.patch.object(mock.patch,'dict',side_effect=AssertionError('DISCOVERY_SDK_MUTATION')), mock.patch.object(isolation,'stub_modules',side_effect=AssertionError('DISCOVERY_SDK_MUTATION')):
    exec(compile(path.read_text(),str(path),'exec'),namespace)
after={{k:v for k,v in sys.modules.items() if k=='google' or k.startswith('google.') or k=='psycopg'}}
assert before.keys()==after.keys() and all(after[k] is v for k,v in before.items())
assert namespace['readiness'] is None
'''
        result = subprocess.run([sys.executable, '-S', '-c', program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


class Cursor:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class FakeConnection:
    def __init__(self, failure=None):
        self.failure = failure
        self.closed = False

    def execute(self, sql, params=None):
        if sql.startswith('SELECT current_database'):
            if self.failure == 'sql':
                raise ConnectionError('synthetic-sensitive')
            return Cursor(readiness.TARGET)
        if 'SELECT ssl ' in sql:
            return Cursor((self.failure != 'tls',))
        if 'to_regclass' in sql:
            return Cursor((True,))
        if 'SELECT version,name,checksum' in sql:
            return Cursor(EXPECTED[:-1] if self.failure == 'schema' else EXPECTED)
        if 'FROM pg_index' in sql:
            return Cursor([[name, self.failure != 'index', True] for name in readiness.INDEXES])
        if sql == 'ROLLBACK' and self.failure == 'rollback':
            raise RuntimeError('synthetic-sensitive')
        return Cursor(None)

    def close(self):
        self.closed = True
        if self.failure == 'close':
            raise RuntimeError('synthetic-sensitive')


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'source'
        self.root.mkdir()
        self.git('init', '-q')
        (self.root / 'tracked.py').write_text('original = True\n')
        self.git('add', 'tracked.py')
        self.git('-c', 'user.name=Offline Test', '-c', 'user.email=offline@example.invalid', 'commit', '-qm', 'fixture')
        self.head = self.git('rev-parse', 'HEAD').strip()
        self.source_patch = patch.object(readiness, 'SOURCE', self.head)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True, stderr=subprocess.DEVNULL)

    def verify(self):
        return readiness.verify_source(self.root, time.monotonic() + 30)

    def test_real_clean_then_tracked_and_untracked_changes_refuse(self):
        self.assertIsNone(self.verify())
        for name, text in [('tracked.py', 'original = False\n'), ('shadow.py', 'private_import_shadow\n')]:
            with self.subTest(name=name):
                (self.root / name).write_text(text)
                with self.assertRaises(readiness.SourceFailure) as caught:
                    self.verify()
                self.assertEqual(caught.exception.fields['failure_stage'], 'source_clean')
                self.assertNotIn(text.strip(), json.dumps(caught.exception.fields))
                if name == 'tracked.py':
                    (self.root / name).write_text('original = True\n')
                else:
                    (self.root / name).unlink()

    def test_changed_head_and_source_or_git_symlinks_refuse(self):
        with patch.object(readiness, 'SOURCE', 'a' * 40), self.assertRaises(readiness.SourceFailure) as caught:
            self.verify()
        self.assertEqual(caught.exception.fields['failure_stage'], 'source_head')
        alias = Path(self.tmp.name) / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(readiness.SourceFailure) as caught:
            readiness.verify_source(alias, time.monotonic() + 30)
        self.assertEqual(caught.exception.fields['failure_stage'], 'source_root')
        gitdir = self.root / '.git'
        relocated = Path(self.tmp.name) / 'gitdir'
        gitdir.rename(relocated)
        gitdir.symlink_to(relocated, target_is_directory=True)
        with self.assertRaises(readiness.SourceFailure) as caught:
            self.verify()
        self.assertEqual(caught.exception.fields['failure_stage'], 'source_root')

    def test_git_configuration_cannot_hide_untracked_source(self):
        self.git('config', 'status.showUntrackedFiles', 'no')
        (self.root / 'shadow.py').write_text('untracked = True\n')
        self.assertEqual(self.git('status', '--porcelain'), '')
        with self.assertRaises(readiness.SourceFailure) as caught:
            self.verify()
        self.assertEqual(caught.exception.fields['failure_stage'], 'source_clean')

    def test_timeout_stage_is_distinct_and_has_no_command_or_output(self):
        for stage, prefix in [('source_head', []), ('source_clean', [self.head])]:
            error = subprocess.TimeoutExpired('SECRET_COMMAND', 5, output='SECRET_OUTPUT')
            with self.subTest(stage=stage), patch.object(
                readiness.subprocess, 'check_output', side_effect=prefix + [error]
            ):
                with self.assertRaises(readiness.SourceFailure) as caught:
                    self.verify()
                fields = caught.exception.fields
                self.assertEqual(fields['failure_stage'], stage)
                self.assertEqual(fields['failure_class'], 'TimeoutExpired')
                self.assertEqual(set(fields), {'failure_stage', 'failure_class', 'failure_stage_elapsed_ms'})
                self.assertNotIn('SECRET', json.dumps(fields))

    def test_remaining_deadline_caps_both_git_calls_and_expiration_refuses(self):
        # A full remaining budget uses the measured stage allocation; both
        # calls still share the unchanged overall readiness deadline.
        with patch.object(readiness.time, 'monotonic', return_value=50), patch.object(
            readiness.subprocess, 'check_output', side_effect=[self.head, '']
        ) as command:
            readiness.verify_source(self.root, 100)
        self.assertEqual([call.kwargs['timeout'] for call in command.call_args_list], [5, 30])
        self.assertEqual(readiness.READINESS_SECONDS, 50)
        with patch.object(readiness.time, 'monotonic', return_value=99), patch.object(
            readiness.subprocess, 'check_output', side_effect=[self.head, '']
        ) as command:
            readiness.verify_source(self.root, 100)
        self.assertEqual([call.kwargs['timeout'] for call in command.call_args_list], [1, 1])
        with patch.object(readiness.time, 'monotonic', return_value=100), patch.object(
            readiness.subprocess, 'check_output'
        ) as command, self.assertRaises(readiness.SourceFailure) as caught:
            readiness.verify_source(self.root, 100)
        self.assertEqual(caught.exception.fields['failure_class'], 'TimeoutError')
        command.assert_not_called()


class ReportTests(unittest.TestCase):
    def test_success_shape_unchanged_and_sql_failures_localize(self):
        result = readiness.read_metadata(lambda: FakeConnection(), EXPECTED)
        self.assertEqual(
            result,
            {
                'result': 'METADATA_READY_ONLY',
                'customer_rows_read': False,
                'state_initialized': False,
                'write_attempted': False,
                'session': list(readiness.TARGET),
                'tls': True,
                'migrations': EXPECTED,
                'indexes': [[name, True, True] for name in readiness.INDEXES],
                'rollback': True,
            },
        )
        for failure, stage in [
            ('sql', 'identity'),
            ('tls', 'tls'),
            ('schema', 'migrations'),
            ('index', 'indexes'),
            ('rollback', 'rollback'),
            ('close', 'close'),
        ]:
            conn = FakeConnection(failure)
            report = readiness.read_metadata(lambda: conn, EXPECTED)
            self.assertEqual(report['failure_stage'], stage)
            self.assertEqual(report['result'], 'HOLD')
            self.assertTrue(conn.closed)
            self.assertEqual(set(report), HOLD_KEYS)
            self.assertNotIn('synthetic-sensitive', json.dumps(report))

    def test_unknown_exception_names_and_messages_are_not_exported(self):
        SecretClassName = type('SecretClassName', (Exception,), {})

        def fail():
            raise SecretClassName('SECRET_MESSAGE')

        report = readiness.read_metadata(fail, EXPECTED)
        self.assertEqual(report['failure_class'], 'UnexpectedFailure')
        self.assertEqual(report['failure_stage'], 'connect')
        self.assertNotIn('Secret', json.dumps(report))
        self.assertNotIn('SECRET', json.dumps(report))

    def test_wrong_workload_failure_is_staged_and_nonzero_before_source(self):
        output = io.StringIO()
        with patch.object(readiness.os, 'getuid', return_value=1000), patch.object(
            readiness.socket, 'gethostname', return_value='wrong-host'
        ), patch.object(readiness, 'verify_source') as verify, redirect_stdout(output):
            self.assertEqual(readiness.main(), 2)
        verify.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report['result'], 'HOLD')
        self.assertEqual(report['failure_stage'], 'workload_binding')
        self.assertEqual(report['failure_class'], 'ValueError')
        self.assertFalse(report['customer_rows_read'])
        self.assertFalse(report['state_initialized'])
        self.assertFalse(report['write_attempted'])
        self.assertEqual(set(report), HOLD_KEYS)

    def test_main_metadata_hold_has_exact_failure_shape_without_success_provenance(self):
        conn = types.SimpleNamespace(iam_connector=lambda *args: lambda: FakeConnection('tls'))
        migrations = [types.SimpleNamespace(version=v, name=n, checksum=c) for v, n, c in EXPECTED]
        migrate = types.SimpleNamespace(load=lambda: migrations)
        supervisor = types.SimpleNamespace(hexdigest=lambda: CONTRACT['supervisor_sha256'])
        output = io.StringIO()
        with patch.object(readiness.os, 'getuid', return_value=1000), patch.object(
            readiness.socket, 'gethostname', return_value='jobstore-reconcile-0'
        ), patch.object(readiness, 'verify_source'), patch.object(
            readiness.Path, 'read_bytes', return_value=b'fixture'
        ), patch.object(
            readiness.hashlib, 'sha256', return_value=supervisor
        ), patch.object(
            readiness.Path, 'exists', return_value=False
        ), patch.object(
            readiness.Path, 'home', return_value=Path('/synthetic-home')
        ), patch.dict(
            readiness.os.environ, {}, clear=True
        ), patch.object(
            readiness.google.auth, 'default', return_value=(object(), None)
        ), patch.object(
            readiness, 'Credentials', object
        ), patch.object(
            readiness.sys, 'version', '3.11.15 fixture'
        ), patch.object(
            readiness.psycopg, '__version__', '3.2.10', create=True
        ), patch.object(
            readiness, 'load_module', side_effect=[conn, migrate]
        ), redirect_stdout(
            output
        ):
            self.assertEqual(readiness.main(), 2)
        report = json.loads(output.getvalue())
        self.assertEqual(set(report), HOLD_KEYS)
        self.assertEqual(report['failure_stage'], 'tls')


if __name__ == '__main__':
    unittest.main()
