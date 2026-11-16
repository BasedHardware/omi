"""Verify closed publication admission and current-run proof with offline controls."""

import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import copy
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import preflight
import publish_operator
import qualify_operator
import registry_access
import image_smoke
from test_operator_ingress import inputs


class ControlTests(unittest.TestCase):

    def test_source_container_containment_and_exact_cleanup(self):
        for readiness in (False, True):
            with self.subTest(readiness=readiness), patch.object(
                image_smoke.subprocess, 'check_output', return_value='owned-container\n'
            ) as create, patch.object(
                image_smoke.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='proof')
            ) as run:
                self.assertEqual(image_smoke.run_container(['image', 'program'], readiness=readiness), 'proof')
            argv = create.call_args.args[0]
            for flag in (
                '--platform=linux/amd64',
                '--network=none',
                '--read-only',
                '--memory=512m',
                '--cap-drop=ALL',
                '--security-opt=no-new-privileges',
                '--tmpfs=/tmp:rw,mode=1777',
                '--pids-limit=128',
            ):
                self.assertEqual(argv.count(flag), 1)
            self.assertEqual(
                [arg for arg in argv if arg.startswith('--cpus=')], ['--cpus=0.5' if readiness else '--cpus=2']
            )
            for flag in ('--hostname=jobstore-reconcile-0', '--env=GIT_OPTIONAL_LOCKS=0'):
                self.assertEqual(argv.count(flag), int(readiness))
            self.assertEqual(argv[-2:], ['image', 'program'])
            self.assertEqual(
                [call.args[0] for call in run.call_args_list],
                [['docker', 'start', '-a', 'owned-container'], ['docker', 'rm', '-f', 'owned-container']],
            )

    def test_optimized_python_cannot_emit_false_source_refusal_proof(self):
        # No image, credential, source file or child is accessed: the fake guard
        # supplies a failed source stage that must never become a passing proof.
        bootstrap = '''
import sys,types
guard=types.ModuleType('process_guard')
guard.run_group=lambda *a,**kw: ({'result':'DEADLINE','exit_code':None}, '{"result":"HOLD","failure_stage":"source_clean"}')
sys.modules['process_guard']=guard
'''
        program = image_smoke.SOURCE_REFUSAL_PROGRAM.replace('__READINESS_SHA256__', 'a' * 64)
        result = subprocess.run(
            [sys.executable, '-O', '-c', bootstrap + program], capture_output=True, text=True, timeout=10
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL', result.stdout)

    def test_malformed_runner_hash_refuses_before_host_or_container_access(self):
        for value in (None, True, '', 'a' * 63, 'A' * 64, "'; print('INJECTED'); #"):
            with self.subTest(value=value), patch.object(
                qualify_operator, 'native_host', side_effect=AssertionError('NO_HOST_ACCESS')
            ):
                with self.assertRaisesRegex(ValueError, 'READINESS_SHA256'):
                    qualify_operator.qualify({'readiness_sha256': value}, None, None, None)

    def prepared(self):
        c, _, _ = inputs()
        c.update(
            source_tree='b' * 40,
            readiness_sha256='a' * 64,
            build_inputs_sha256='c' * 64,
            supervisor_sha256='d' * 64,
            oci_manifest_digest='sha256:' + 'e' * 64,
            destination=publish_operator.DESTINATION,
            required_disposable_free_bytes=100,
            status='REVIEWED_EXACT_INPUTS_FOR_GUARDED_PUBLICATION',
            registry_write_authorization=None,
            registry_access_evidence={
                'repository': publish_operator.DESTINATION,
                'principal': registry_access.PRINCIPAL,
                'iam_resource': registry_access.RESOURCE,
                'decision': registry_access.DECISION,
                'effective_authorization': 'UNKNOWN_UNTIL_ACTUAL_REGISTRY_OPERATIONS',
                'allow_policy_receipt_sha256': 'f' * 64,
                'wif_metadata_receipt_sha256': 'a' * 64,
                'sa_trust_receipt_sha256': 'b' * 64,
            },
        )
        e = {
            'REQUESTED_SOURCE': c['source_sha'],
            'SKIP_PROOF': 'false',
            'BREAK_GLASS_LOCK': 'false',
            'SERVICE_IMAGES': '',
        }
        r = {
            'result': 'NATIVE_AMD64_QUALIFIED_OFFLINE_ONLY',
            **{
                k: c[k]
                for k in (
                    'source_sha',
                    'source_tree',
                    'archive_sha256',
                    'oci_manifest_digest',
                    'build_inputs_sha256',
                    'supervisor_sha256',
                )
            },
            'tests_run': 56,
            'resource_bound_source_refusal': {
                'result': 'SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL',
                'readiness_sha256': c['readiness_sha256'],
                'uid': 1000,
                'full_source_check': True,
                'credential_refusal_injected': True,
                'real_credentials_used': False,
                'sql_called': False,
                'elapsed_ms': 100,
            },
            'tests_skipped': 0,
            'uid': 1000,
            'container_network': 'none',
            'real_state_accessed': False,
            'production_calls': False,
            'workflow_sha': 'w',
            'run_id': '1',
            'native_host': {'system': 'Linux', 'machine': 'x86_64', 'docker_architecture': 'x86_64'},
        }
        return (c, e, r)

    def test_preflight_accepts_only_complete_scoped_contract(self):
        c, e, _ = self.prepared()
        preflight.check(c, e, 100)

    def test_all_bypass_and_deploy_inputs_refused(self):
        for key, value in (
            ('REQUESTED_SOURCE', '0' * 40),
            ('SKIP_PROOF', 'true'),
            ('BREAK_GLASS_LOCK', 'true'),
            ('SERVICE_IMAGES', 'backend=other'),
        ):
            c, e, _ = self.prepared()
            e[key] = value
            with self.assertRaises(ValueError):
                preflight.check(c, e, 100)

    def test_missing_ingress_permission_or_space_refused(self):
        for key, value in (('release_id', None), ('registry_access_evidence', None)):
            c, e, _ = self.prepared()
            c[key] = value
            with self.assertRaises(ValueError):
                preflight.check(c, e, 100)
        c, e, _ = self.prepared()
        with self.assertRaises(ValueError):
            preflight.check(c, e, 99)

    def test_exact_current_run_native_receipt_required(self):
        c, _, r = self.prepared()
        with patch.dict(os.environ, {'GITHUB_WORKFLOW_SHA': 'w', 'GITHUB_RUN_ID': '1'}):
            publish_operator.validate_qualification(c, r)
            for key, value in (
                ('source_sha', 'z' * 40),
                ('tests_skipped', 1),
                ('tests_run', 48),
                ('container_network', 'default'),
                ('real_state_accessed', True),
                ('run_id', 'other'),
            ):
                bad = copy.deepcopy(r)
                bad[key] = value
                with self.assertRaises(ValueError):
                    publish_operator.validate_qualification(c, bad)

    def test_missing_or_weakened_source_refusal_prevents_publication(self):
        c, _, receipt = self.prepared()
        cases = [None]
        for key, value in [
            ('readiness_sha256', 'z' * 64),
            ('full_source_check', False),
            ('real_credentials_used', True),
            ('sql_called', True),
            ('elapsed_ms', 60000),
            ('elapsed_ms', True),
        ]:
            bad = copy.deepcopy(receipt['resource_bound_source_refusal'])
            bad[key] = value
            cases.append(bad)
        with patch.dict(os.environ, {'GITHUB_WORKFLOW_SHA': 'w', 'GITHUB_RUN_ID': '1'}):
            for proof in cases:
                bad = copy.deepcopy(receipt)
                if proof is None:
                    bad.pop('resource_bound_source_refusal')
                else:
                    bad['resource_bound_source_refusal'] = proof
                with self.subTest(proof=proof), self.assertRaises(ValueError):
                    publish_operator.validate_qualification(c, bad)

            for proof in (None, 1, True, 'proof', []):
                bad = copy.deepcopy(receipt)
                bad['resource_bound_source_refusal'] = proof
                with self.subTest(malformed=proof), self.assertRaisesRegex(ValueError, 'SOURCE_REFUSAL_REQUIRED'):
                    publish_operator.validate_qualification(c, bad)

    def test_emulated_host_receipt_refused(self):
        c, _, r = self.prepared()
        r['native_host']['machine'] = 'arm64'
        with patch.dict(os.environ, {'GITHUB_WORKFLOW_SHA': 'w', 'GITHUB_RUN_ID': '1'}):
            with self.assertRaises(ValueError):
                publish_operator.validate_qualification(c, r)

    def test_non_native_actual_host_refused_before_docker(self):
        with patch.object(qualify_operator.platform, 'system', return_value='Darwin'), patch.object(
            qualify_operator.subprocess, 'check_output'
        ) as command:
            with self.assertRaises(ValueError):
                qualify_operator.native_host()
            command.assert_not_called()

    def test_fixture_path_escape_refused_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'fixtures.tar.gz'
            target = root / 'target'
            target.mkdir()
            with tarfile.open(archive, 'w:gz') as t:
                row = tarfile.TarInfo('../escape')
                row.size = 1
                t.addfile(row, io.BytesIO(b'x'))
            with self.assertRaises(ValueError):
                qualify_operator.fixture_files(archive, target)
            self.assertFalse((root / 'escape').exists())


if __name__ == '__main__':
    unittest.main()
