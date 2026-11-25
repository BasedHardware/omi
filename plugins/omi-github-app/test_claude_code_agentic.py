"""Hermetic regression tests for issue #25955.

Runs the real run_agentic_claude_on_repo against a local bare remote with a
scripted Anthropic client. A run that ends without IMPLEMENTATION_COMPLETE
(or hits the iteration cap) must not commit or push and must report failure.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
# CI runs this with stdlib only; the client is replaced per test anyway.
sys.modules.setdefault('anthropic', SimpleNamespace(Anthropic=None))
import claude_code_agentic  # noqa: E402


def _git(*args, cwd):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)


def _write_call(n=0):
    return SimpleNamespace(
        stop_reason='tool_use',
        content=[
            SimpleNamespace(
                type='tool_use',
                id=f'call_{n}',
                name='write_file',
                input={'file_path': 'greeting.py', 'content': f"def greet(name):\n    return 'hello'  # {n}\n"},
            )
        ],
    )


def _end_turn(text):
    return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=text)])


class _FakeAnthropic:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.messages = SimpleNamespace(create=lambda **_: next(self._responses))


class RunAgenticClaudeOnRepoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.remote = root / 'remote.git'
        seed = root / 'seed'
        _git('init', '--bare', '-b', 'main', str(self.remote), cwd=root)
        _git('init', '-b', 'main', str(seed), cwd=root)
        (seed / 'app.py').write_text('print("hi")\n')
        _git('add', '.', cwd=seed)
        _git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-m', 'init', cwd=seed)
        _git('push', str(self.remote), 'main', cwd=seed)
        env = {
            'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
            'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t',
        }
        self._env = patch.dict(os.environ, env)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def _remote_branches(self):
        out = subprocess.run(['git', 'branch', '--list'], cwd=self.remote, capture_output=True, text=True)
        return out.stdout

    def _run(self, responses, max_iterations=15):
        with patch.object(claude_code_agentic, 'Anthropic', lambda api_key: _FakeAnthropic(responses)):
            return claude_code_agentic.run_agentic_claude_on_repo(
                str(self.remote), 'add a greeting', 'feat/greeting', 'tok', 'key', max_iterations=max_iterations
            )

    def test_end_turn_without_marker_does_not_push(self):
        result = self._run([_write_call(), _end_turn('I could not finish the feature.')])
        self.assertFalse(result['success'])
        self.assertIn('IMPLEMENTATION_COMPLETE', result['message'])
        self.assertNotIn('feat/greeting', self._remote_branches())

    def test_iteration_cap_does_not_push(self):
        result = self._run([_write_call(i) for i in range(3)], max_iterations=3)
        self.assertFalse(result['success'])
        self.assertNotIn('feat/greeting', self._remote_branches())

    def test_marker_still_pushes(self):
        result = self._run([_write_call(), _end_turn('Done. IMPLEMENTATION_COMPLETE')])
        self.assertTrue(result['success'])
        self.assertIn('feat/greeting', self._remote_branches())


if __name__ == '__main__':
    unittest.main()
