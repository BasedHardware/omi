"""Hermetic regression tests for issue #25956.

Runs the real run_claude_code_on_repo against a local bare remote with a fake
`claude-code` executable on PATH. A failed or timed-out generator run must not
commit or push anything and must report success: False.
"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_code_cli  # noqa: E402


def _git(*args, cwd):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)


class RunClaudeCodeOnRepoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.remote = root / 'remote.git'
        seed = root / 'seed'
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        _git('init', '--bare', '-b', 'main', str(self.remote), cwd=root)
        _git('init', '-b', 'main', str(seed), cwd=root)
        (seed / 'app.py').write_text('print("hi")\n')
        _git('add', '.', cwd=seed)
        _git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-m', 'init', cwd=seed)
        _git('push', str(self.remote), 'main', cwd=seed)
        self.fake = bin_dir / 'claude-code'
        env = {
            'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
            'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
            'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t',
        }
        self._env = patch.dict(os.environ, env)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def _write_fake(self, exit_code):
        self.fake.write_text(f'#!/bin/sh\necho "partial work" > app.py\necho "panic" >&2\nexit {exit_code}\n')
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)

    def _remote_branches(self):
        out = subprocess.run(['git', 'branch', '--list'], cwd=self.remote, capture_output=True, text=True)
        return out.stdout

    def _run(self):
        return claude_code_cli.run_claude_code_on_repo(str(self.remote), 'add a greeting', 'feat/greeting', 'tok', 'key')

    def test_nonzero_exit_does_not_push(self):
        self._write_fake(1)
        result = self._run()
        self.assertFalse(result['success'])
        self.assertIn('exited with code 1', result['message'])
        self.assertNotIn('feat/greeting', self._remote_branches())

    def test_timeout_does_not_push(self):
        self._write_fake(0)
        real_run = subprocess.run

        def fake_run(cmd, *a, **kw):
            if cmd[0] == 'claude-code':
                raise subprocess.TimeoutExpired(cmd, 300)
            return real_run(cmd, *a, **kw)

        with patch.object(claude_code_cli.subprocess, 'run', side_effect=fake_run):
            result = self._run()
        self.assertFalse(result['success'])
        self.assertIn('timed out', result['message'])
        self.assertNotIn('feat/greeting', self._remote_branches())

    def test_success_still_pushes(self):
        self._write_fake(0)
        result = self._run()
        self.assertTrue(result['success'])
        self.assertIn('feat/greeting', self._remote_branches())


if __name__ == '__main__':
    unittest.main()
