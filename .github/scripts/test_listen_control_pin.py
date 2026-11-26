"""Exercise the production listen control check after main advances."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class ListenControlPinTests(unittest.TestCase):
    def test_main_advance_after_approval_cannot_change_the_admitted_tree(self):
        workflow = Path(__file__).resolve().parents[1] / 'workflows/gcp_backend_listen_helm.yml'
        steps = yaml.safe_load(workflow.read_text())['jobs']['helm-upgrade']['steps']
        checkout, guard = steps[1:3]
        self.assertTrue(checkout['with']['ref'].startswith("${{ inputs.control_sha != '' && github.sha || "))
        self.assertEqual(guard['if'], "${{ inputs.control_sha != '' }}")
        with tempfile.TemporaryDirectory() as workdir:
            def git(*args):
                return subprocess.run(
                    ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args],
                    cwd=workdir, check=True, capture_output=True, text=True,
                ).stdout.strip()

            git('init', '-b', 'main')
            git('commit', '--allow-empty', '-m', 'admitted by the production gate')
            admitted = git('rev-parse', 'HEAD')
            Path(workdir, 'chart-values.yaml').write_text('replicas: 99\n')
            git('add', 'chart-values.yaml')
            git('commit', '-m', 'main moved after approval')
            moved = git('rev-parse', 'main')
            env = dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_SHA=admitted,
                       CONTROL_SHA=admitted, DEPLOY_ENV='prod', DEPLOY_MODE='deploy')

            def guard_result(**updates):
                return subprocess.run(['bash', '-c', guard['run']], cwd=workdir,
                                      env=env | updates, capture_output=True, text=True)

            moved_checkout = guard_result()
            self.assertEqual(moved_checkout.returncode, 1)
            self.assertIn('Listen control mismatch', moved_checkout.stdout)
            git('checkout', '--detach', admitted)
            self.assertEqual(guard_result().returncode, 0)
            for updates in ({'GITHUB_SHA': moved}, {'DEPLOY_MODE': 'rollback'}, {'DEPLOY_ENV': 'development'}):
                with self.subTest(updates=updates):
                    self.assertEqual(guard_result(**updates).returncode, 1)


if __name__ == '__main__':
    unittest.main()
