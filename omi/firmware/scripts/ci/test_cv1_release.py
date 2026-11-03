#!/usr/bin/env python3
"""Offline promotion/packaging contract tests; no signing keys or GitHub writes."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import sys
import unittest
from unittest.mock import patch
import zipfile

import cv1_release as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'build'
        self.build.mkdir()
        header = bytearray(32)
        struct.pack_into('<I', header, 0, 0x96F3B83D)
        struct.pack_into('<BBH', header, 20, 3, 0, 21)
        self.payload = bytes(header) + b'app-with-randomized-signature'
        self.manifest = {
            'format-version': 1,
            'time': 123,
            'name': 'omi',
            'files': [
                {
                    'file': 'omi.signed.bin',
                    'image_index': '0',
                    'size': len(self.payload),
                    'load_address': 66048,
                    'slot_index_primary': '1',
                    'version_MCUBOOT': '3.0.21',
                },
                {'file': 'ipc_radio.bin', 'image_index': '1', 'size': 5, 'slot_index_primary': '3'},
            ],
        }
        with zipfile.ZipFile(self.build / 'dfu_application.zip', 'w') as archive:
            archive.writestr('manifest.json', json.dumps(self.manifest))
            archive.writestr('omi.signed.bin', self.payload)
            archive.writestr('ipc_radio.bin', b'radio')
        (self.build / 'merged.hex').write_bytes(b'factory app hex')
        (self.build / 'merged_CPUNET.hex').write_bytes(b'factory net hex')
        self.run = {
            'id': 123,
            'run_attempt': 1,
            'workflow_id': 42,
            'path': release.WORKFLOW,
            'repository': {'full_name': 'BasedHardware/omi'},
            'event': 'workflow_dispatch',
            'head_sha': 'a' * 40,
            'status': 'completed',
            'conclusion': 'success',
        }
        self.context = {
            'sha': self.run['head_sha'],
            'run_id': '123',
            'run_attempt': '1',
            'workflow': release.WORKFLOW,
            'repository': 'BasedHardware/omi',
        }
        self.assets = self.root / 'qa'
        release.stage(self.build, self.assets, '3.0.21', False, self.context)

    def test_repackage_only_app_preserves_bytes_and_metadata(self):
        with zipfile.ZipFile(self.assets / release.asset_names('3.0.21')[0]) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json', 'omi.signed.bin'})
            self.assertEqual(archive.read('omi.signed.bin'), self.payload)
            manifest = release.ota_manifest(archive)
            self.assertEqual(manifest['files'], self.manifest['files'][:1])
            self.assertEqual(manifest['time'], 123)
        for original, name in zip(('merged.hex', 'merged_CPUNET.hex'), release.asset_names('3.0.21')[1:]):
            self.assertEqual((self.build / original).read_bytes(), (self.assets / name).read_bytes())

    def test_network_requires_explicit_opt_in(self):
        target = self.root / 'paired.zip'
        release.repackage(self.build / 'dfu_application.zip', target, True)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(len(release.ota_manifest(archive)['files']), 2)
            self.assertEqual(archive.read('ipc_radio.bin'), b'radio')

    def test_bad_manifest_rejected(self):
        source = self.root / 'bad.zip'
        for mutate in ('size', 'role', 'extra'):
            manifest = copy.deepcopy(self.manifest)
            if mutate == 'size':
                manifest['files'][0]['size'] = 1
            if mutate == 'role':
                manifest['files'][0]['image_index'] = '2'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                archive.writestr('omi.signed.bin', self.payload)
                archive.writestr('ipc_radio.bin', b'radio')
                if mutate == 'extra':
                    archive.writestr('extra.bin', b'extra')
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                release.repackage(source, self.root / 'bad-out.zip')

    def test_run_gate_rejects_each_wrong_field(self):
        release.validate_run(self.run, 42, 'BasedHardware/omi', 'a' * 40, '123')
        for key, value in {
            'id': 456,
            'workflow_id': 99,
            'path': 'other.yml',
            'event': 'push',
            'repository': {'full_name': 'fork/omi'},
            'head_sha': 'b' * 40,
            'status': 'in_progress',
            'conclusion': 'failure',
        }.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                release.validate_run(dict(self.run, **{key: value}), 42, 'BasedHardware/omi', 'a' * 40, '123')

    def test_provenance_gate(self):
        release.validate_assets(self.assets, self.run, '3.0.21', False)
        path = self.assets / 'qa-provenance.json'
        original = json.loads(path.read_text())
        for key, value in {
            'mode': 'publish',
            'version': '3.0.22',
            'sha': 'b' * 40,
            'run_attempt': '2',
            'run_id': '124',
            'workflow': 'other.yml',
            'repository': 'fork/omi',
            'include_network_core': True,
        }.items():
            path.write_text(json.dumps(dict(original, **{key: value})))
            with self.subTest(key=key), self.assertRaises(ValueError):
                release.validate_assets(self.assets, self.run, '3.0.21', False)
        path.write_text(json.dumps(original))
        (self.assets / release.asset_names('3.0.21')[1]).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            release.validate_assets(self.assets, self.run, '3.0.21', False)

    def test_promote_downloads_and_preserves_exact_tested_files(self):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            if args[0] == 'api':
                return json.dumps({'id': 42} if 'workflows/' in args[1] else self.run)
            self.assertEqual(args[:3], ('run', 'download', '123'))
            self.assertIn(release.ARTIFACT, args)
            shutil.copytree(self.assets, Path(args[-1]), dirs_exist_ok=True)
            return ''

        target = self.root / 'promoted'
        with patch.object(release, 'gh', side_effect=fake_gh):
            release.promote(target, '3.0.21', False, '123', 'BasedHardware/omi', 'a' * 40, 'refs/heads/main')
        for name in release.asset_names('3.0.21'):
            self.assertEqual((target / name).read_bytes(), (self.assets / name).read_bytes())
        self.assertEqual(len(calls), 3)

    def test_missing_run_and_non_main_fail_before_network(self):
        for run_id, ref in [('', 'refs/heads/main'), ('123', 'refs/heads/topic')]:
            with patch.object(release, 'gh') as gh, self.assertRaises(ValueError):
                release.promote(self.root / 'out', '3.0.21', False, run_id, 'BasedHardware/omi', 'a' * 40, ref)
            gh.assert_not_called()

    def test_version_reservation_and_bounds(self):
        conf = self.root / 'omi.conf'
        conf.write_text('CONFIG_BT_DIS_FW_REV_STR="3.0.21"\n')
        self.assertEqual(release.version('', conf), '3.0.21')
        for value in ('3.0.90', '3.0.95', '3.0.99'):
            with self.assertRaisesRegex(ValueError, 'reserved'):
                release.version(value, conf)
            self.assertEqual(release.version(value, conf, True), value)
        for value in ('3.0.89', '3.0.100', 'v3.0.21'):
            release.version(value, conf)
        for value in ('3.0.01', '3.0.21\n', '3.0.65536', '256.0.1', 'bad'):
            with self.assertRaises(ValueError):
                release.version(value, conf)

    def test_header_version_must_match_release(self):
        with zipfile.ZipFile(self.assets / release.asset_names('3.0.21')[0]) as archive:
            release.validate_signed_version(archive, '3.0.21')
            with self.assertRaisesRegex(ValueError, 'version'):
                release.validate_signed_version(archive, '3.0.22')

    def test_prepare_syncs_dis_and_signed_version_and_validates_inputs(self):
        conf = self.root / 'omi/firmware/omi/omi.conf'
        conf.parent.mkdir(parents=True)
        conf.write_text('CONFIG_BT_DIS_FW_REV_STR="3.0.20"\n')
        output = self.root / 'outputs'
        script = Path(__file__).with_name('cv1_release.py').resolve()
        env = dict(
            os.environ,
            VERSION_INPUT='3.0.21',
            GITHUB_OUTPUT=str(output),
            PUBLISH='',
            QA_RUN_ID='',
            ROLLOUT_PERCENT='1',
            BLOCKED='false',
        )
        subprocess.run(['python3', str(script), 'prepare'], cwd=self.root, env=env, check=True)
        self.assertIn('CONFIG_BT_DIS_FW_REV_STR="3.0.21"', conf.read_text())
        self.assertIn('CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="3.0.21"', conf.read_text())
        self.assertIn('ver=3.0.21', output.read_text())
        for overrides in (
            {'PUBLISH': 'publish', 'GITHUB_REF': 'refs/heads/main'},
            {'ROLLOUT_PERCENT': '101'},
            {'BLOCKED': 'invalid'},
        ):
            result = subprocess.run(
                ['python3', str(script), 'prepare'], cwd=self.root, env=dict(env, **overrides), capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)

    def test_publish_uses_only_verified_release_assets(self):
        (self.root / 'cv1-validated-run.json').write_text(json.dumps({'run': self.run, 'workflow_id': 42}))
        env = dict(
            os.environ,
            VERSION_INPUT='3.0.21',
            PUBLISH='publish',
            QA_RUN_ID='123',
            GITHUB_REF='refs/heads/main',
            GITHUB_SHA='a' * 40,
            GITHUB_REPOSITORY='BasedHardware/omi',
            INCLUDE_NETWORK_CORE='false',
            OUT=str(self.assets),
            BODY_FILE='body.md',
        )
        missing_tag = subprocess.CompletedProcess([], 1, stdout='', stderr='HTTP 404')
        with patch.dict(os.environ, env, clear=True), patch.object(
            sys, 'argv', ['cv1_release.py', 'publish']
        ), patch.object(release.subprocess, 'run', return_value=missing_tag), patch.object(release, 'gh') as gh:
            release.main()
            args = gh.call_args.args
            self.assertEqual(args[:3], ('release', 'create', 'Omi_CV1_v3.0.21'))
            self.assertEqual(list(args[-3:]), [str(self.assets / n) for n in release.asset_names('3.0.21')])
            self.assertNotIn('qa-provenance.json', ' '.join(args))
            self.assertNotIn('.elf', ' '.join(args))
            gh.reset_mock()
            (self.assets / release.asset_names('3.0.21')[1]).write_bytes(b'changed after promotion')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                release.main()
            gh.assert_not_called()

    def test_body_writes_policy_without_affecting_other_families(self):
        body = self.root / 'body.md'
        script = Path(__file__).with_name('make-release-body.sh')
        env = dict(os.environ, TITLE='CV1', VER='3.0.21', OUT=str(body))
        env.pop('ROLLOUT_PERCENT', None)
        env.pop('BLOCKED', None)
        subprocess.run(['bash', str(script)], env=env, check=True, capture_output=True)
        self.assertNotIn('rollout_percent:', body.read_text())
        subprocess.run(
            ['bash', str(script)], env=dict(env, ROLLOUT_PERCENT='1', BLOCKED='false'), check=True, capture_output=True
        )
        self.assertIn('rollout_percent:1\nblocked:false', body.read_text())


if __name__ == '__main__':
    unittest.main()
