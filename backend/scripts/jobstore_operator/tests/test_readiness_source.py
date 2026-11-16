"""Discriminators for real cleanliness checks and fixed failure-stage evidence."""

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner_readiness as readiness
from readiness_contract import CONTRACT

EXPECTED = CONTRACT['migrations']


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
        ]:
            conn = FakeConnection(failure)
            report = readiness.read_metadata(lambda: conn, EXPECTED)
            self.assertEqual(report['failure_stage'], stage)
            self.assertEqual(report['result'], 'HOLD')
            self.assertTrue(conn.closed)
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


if __name__ == '__main__':
    unittest.main()
