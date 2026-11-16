"""Verify closed publication admission and current-run proof with offline controls."""

import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import preflight
import publish_operator
import qualify_operator
import registry_access
from test_operator_ingress import inputs


class ControlTests(unittest.TestCase):

    def prepared(self):
        c, _, _ = inputs()
        c.update(
            source_tree='b' * 40,
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
            'tests_run': 49,
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
