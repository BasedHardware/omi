"""Exercise release floor admission with a real Git history."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name('verify_backend_release_floor.py')
WORKFLOW = SCRIPT.parents[1] / 'workflows/gcp_backend.yml'


class VerifyBackendReleaseFloorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Floor test')
        self.old = self.commit()
        self.floor = self.commit()
        self.config = self.repo / 'backend/deploy/release_floor.json'
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps(dict(floor=self.floor, reason='Purge safety', since='2026-11-18')))
        self.git('add', '.')
        self.release = self.commit()
        self.git('update-ref', 'refs/remotes/origin/main', self.release)
        self.git('checkout', '--detach', self.old)
        self.git('remote', 'add', 'origin', str(self.repo))
        self.git('update-ref', 'refs/heads/main', self.release)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, stderr=subprocess.PIPE, text=True).strip()

    def commit(self):
        self.git('commit', '--allow-empty', '-qm', 'Fixture')
        return self.git('rev-parse', 'HEAD')

    def check_sha(self, sha):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--sha', sha], cwd=self.repo, capture_output=True, text=True
        )

    def test_floor_and_descendant_are_admitted_using_origin_main(self):
        self.assertEqual(self.check_sha(self.floor).returncode, 0)
        self.assertEqual(self.check_sha(self.release).returncode, 0)

    def test_pre_floor_is_refused(self):
        result = self.check_sha(self.old)
        self.assertEqual(result.returncode, 1)
        self.assertIn('does not satisfy release floor', result.stderr)

    def test_missing_policy_is_refused(self):
        self.git('update-ref', 'refs/remotes/origin/main', self.floor)
        self.assertIn('Cannot read a valid backend release floor', self.check_sha(self.floor).stderr)

    def test_malformed_policy_is_refused(self):
        for content in ('{', '{}', '{"floor":"HEAD"}'):
            with self.subTest(content=content):
                self.config.parent.mkdir(parents=True, exist_ok=True)
                self.config.write_text(content)
                self.git('add', '.')
                self.git('update-ref', 'refs/remotes/origin/main', self.commit())
                self.assertIn('Cannot read a valid backend release floor', self.check_sha(self.floor).stderr)

    def check_revision(self, env_entries):
        revision = {'spec': {'containers': [{'env': env_entries}]}}
        gcloud = self.repo / 'gcloud'
        gcloud.write_text(f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(json.dumps(revision))}\n")
        gcloud.chmod(0o755)
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--revision', 'backend-retained', '--project', 'test', '--region', 'test'],
            cwd=self.repo,
            env={**os.environ, 'PATH': f"{self.repo}{os.pathsep}{os.environ['PATH']}"},
            capture_output=True,
            text=True,
        )

    def test_revision_stamp_at_floor_is_admitted(self):
        self.assertEqual(self.check_revision([{'name': 'OMI_BACKEND_RELEASE_SHA', 'value': self.floor}]).returncode, 0)

    def test_unstamped_revision_is_refused(self):
        result = self.check_revision([])
        self.assertEqual(result.returncode, 1)
        self.assertIn('must have exactly one valid OMI_BACKEND_RELEASE_SHA stamp', result.stderr)

    def test_break_glass_cannot_admit_pre_floor(self):
        workflow = WORKFLOW.read_text()
        step = workflow.split('- name: Verify exact admitted main source', 1)[1].split('\n      - name:', 1)[0]
        run = '\n'.join(line[10:] for line in step.split('run: |\n', 1)[1].splitlines())
        scripts = self.repo / '.github/scripts'
        scripts.mkdir(parents=True)
        (scripts / SCRIPT.name).symlink_to(SCRIPT)
        output = self.repo / 'outputs'
        result = subprocess.run(
            ['bash', '-e', '-c', run],
            cwd=self.repo,
            env={
                **os.environ,
                'DEPLOY_SHA': self.old,
                'SKIP_PROOF': 'true',
                'BREAK_GLASS_CONFIRM': 'deploy-without-proof',
                'BREAK_GLASS_REASON': 'Fixture',
                'GITHUB_OUTPUT': str(output),
            },
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('does not satisfy release floor', result.stderr)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
