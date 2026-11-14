#!/usr/bin/env python3
"""Offline promotion/packaging contract tests; no signing keys or GitHub writes."""

import ast
import copy
import hashlib
import re
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

import cv1_bootloader as boot
import cv1_release as release
from cv1_bootloader import write_hex, read_hex, inspect_hex, POLICY

REAL_SIM_CATALOG = release.sim_catalog


CATALOG = {f'suite/scenario-{i}' for i in range(release.SIM_MIN_SCENARIOS)}


def sim_report(sha, ver, **overrides):
    rows = [{'id': name, 'verdict': 'pass'} for name in sorted(CATALOG)]
    report = {
        'kind': 'omi-cv1-sim-report',
        'schema_version': 1,
        'verdict': 'pass',
        'mode': 'current',
        'source_sha': sha,
        'firmware_version': ver,
        'selection': ['*'],
        'counts': {'scenarios': len(rows), 'passed': len(rows), 'failed': 0},
        'failed': [],
        'scenarios': rows,
        'fuzz': {'verdict': 'pass', 'seeds': release.SIM_MIN_FUZZ_SEEDS},
    }
    report.update(overrides)
    return report


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        catalog = patch.object(release, 'sim_catalog', return_value=set(CATALOG))
        catalog.start()
        self.addCleanup(catalog.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'build'
        self.build.mkdir()
        self.boot_memory = {0: 0x42, 8: 0x11}
        self.boot_image = boot.boot_bytes(self.boot_memory)
        policy = self.root / 'boot-policy.json'
        fixture_hash = hashlib.sha256(self.boot_image).hexdigest()
        policy.write_text(json.dumps({'build_boot_sha256': fixture_hash,
                                     'approved_boot_sha256': [fixture_hash, 'c80cf2fd68b67328c9c7692391a21f87630b266698c2ae9e251967f3e43da086']}))
        policy_patch = patch.object(boot, 'POLICY', policy)
        policy_patch.start()
        self.addCleanup(policy_patch.stop)
        boot_path = self.build / 'mcuboot/zephyr/zephyr.hex'
        boot_path.parent.mkdir(parents=True)
        write_hex(boot_path, self.boot_memory)
        header = bytearray(32)
        struct.pack_into('<I', header, 0, 0x96F3B83D)
        struct.pack_into('<BBH', header, 20, 3, 0, 21)
        self.payload = bytes(header) + b'app-with-randomized-signature'
        self.signed_sha256 = hashlib.sha256(self.payload).hexdigest()
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
        write_hex(self.build / 'merged.hex', {0: 0x42, 0x10000: 0x3d, 0x10200: 0x11})
        write_hex(self.build / 'merged_CPUNET.hex', {0x1000000: 0x33})
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
        self.sim = self.root / 'sim-report.json'
        self.sim.write_text(json.dumps(sim_report('a' * 40, '3.0.21')))
        release.stage(self.build, self.assets, '3.0.21', False, self.context, self.sim)

    def test_promotion_rejects_boot_bytes_even_with_updated_checksums(self):
        name = release.asset_names('3.0.21')[1]
        write_hex(self.assets / name, {0: 0x43, 0x10000: 0x3d})
        provenance = json.loads((self.assets / 'qa-provenance.json').read_text())
        provenance['sha256'][name] = release.digest(self.assets / name)
        (self.assets / 'qa-provenance.json').write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'unapproved CV1 boot region'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)

    def test_promotion_rejects_different_wire_app_even_with_updated_checksum(self):
        name = release.asset_names('3.0.21')[1]
        write_hex(self.assets / name, {**dict(enumerate(self.boot_image)), 0x10000: 0x3d, 0x10001: 0})
        provenance = json.loads((self.assets / 'qa-provenance.json').read_text())
        provenance['sha256'][name] = release.digest(self.assets / name)
        (self.assets / 'qa-provenance.json').write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'exactly the pinned bootloader and tested OTA signed bytes'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)

    def test_stage_reparses_and_rejects_corrupted_writer_output(self):
        def corrupt_writer(path, memory):
            write_hex(path, {**memory, 0xf6000: 1})
        with patch.object(release, 'write_hex', side_effect=corrupt_writer):
            with self.assertRaisesRegex(ValueError, 'exactly the pinned bootloader'):
                release.stage(self.build, self.root / 'bad-write', '3.0.21', False, self.context, self.sim)

    def test_stage_rejects_boot_bytes_in_network_hex(self):
        write_hex(self.build / 'merged_CPUNET.hex', {0: 0x42, 0x1000000: 0x33})
        with self.assertRaisesRegex(ValueError, 'unapproved CV1 boot region'):
            release.stage(self.build, self.root / 'bad-net', '3.0.21', False, self.context, self.sim)

    def test_stage_rejects_even_approved_boot_bytes_in_network_hex(self):
        write_hex(self.build / 'merged_CPUNET.hex', {**self.boot_memory, 0x1000000: 0x33})
        with self.assertRaisesRegex(ValueError, 'CPUNET HEX must not contain'):
            release.stage(self.build, self.root / 'approved-boot-in-net', '3.0.21', False, self.context, self.sim)

    def test_other_allowlisted_boot_or_outside_app_bytes_cannot_enter_release_hex(self):
        name = release.asset_names('3.0.21')[1]
        original = boot.wire_memory(self.payload, self.boot_image)
        factory = read_hex(POLICY.parents[1] / 'FLASH_3.0.8/MAC/merged.hex')
        factory_boot = {address: byte for address, byte in factory.items() if address < 0x10000}
        for extra in (factory_boot, {0xf6000: 1}, {0xff8000: 1}, {0x1000000: 1}):
            write_hex(self.assets / name, {**original, **extra})
            provenance = json.loads((self.assets / 'qa-provenance.json').read_text())
            provenance['sha256'][name] = release.digest(self.assets / name)
            provenance['boot_regions'][name] = inspect_hex(self.assets / name)
            (self.assets / 'qa-provenance.json').write_text(json.dumps(provenance))
            with self.subTest(extra=min(extra)), self.assertRaisesRegex(ValueError, 'pinned build bootloader|exactly the pinned bootloader'):
                release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)

    def test_stage_requires_the_exact_build_loader_and_reservation(self):
        path = self.build / 'mcuboot/zephyr/zephyr.hex'
        for index, memory in enumerate(({0: 0x43}, {**self.boot_memory, 0x10000: 1})):
            write_hex(path, memory)
            with self.subTest(memory=memory), self.assertRaisesRegex(ValueError, 'pinned build bootloader|reservation|inside'):
                release.stage(self.build, self.root / f'bad-boot-{index}', '3.0.21', False, self.context, self.sim)

    def test_promotion_rejects_app_only_replacement_even_with_receipts_updated(self):
        name = release.asset_names('3.0.21')[1]
        write_hex(self.assets / name, dict(enumerate(self.payload, 0x10000)))
        provenance = json.loads((self.assets / 'qa-provenance.json').read_text())
        provenance['sha256'][name] = release.digest(self.assets / name)
        provenance['boot_regions'][name] = inspect_hex(self.assets / name)
        (self.assets / 'qa-provenance.json').write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'initialized bytes'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)

    def test_stage_requires_a_passing_full_simulator_report(self):
        bad_rows = [{'id': 'x', 'verdict': 'pass'}] * release.SIM_MIN_SCENARIOS
        failing = [dict(r, verdict='fail') for r in sim_report('a' * 40, '3.0.21')['scenarios']]
        for name, report in {
            'missing': None,
            'verdict': sim_report('a' * 40, '3.0.21', verdict='fail'),
            'baseline-mode': sim_report('a' * 40, '3.0.21', mode='baseline'),
            'other-sha': sim_report('b' * 40, '3.0.21'),
            'dirty-sha': sim_report('a' * 40 + '-dirty', '3.0.21'),
            'other-version': sim_report('a' * 40, '3.0.22'),
            'partial-selection': sim_report('a' * 40, '3.0.21', selection=['safe/*']),
            'too-few': sim_report('a' * 40, '3.0.21', scenarios=[{'id': 'a', 'verdict': 'pass'}]),
            'duplicate-ids': sim_report('a' * 40, '3.0.21', scenarios=bad_rows),
            'scenario-failed': sim_report('a' * 40, '3.0.21', scenarios=failing),
            'counts': sim_report('a' * 40, '3.0.21', counts={'scenarios': 1, 'passed': 0, 'failed': 1}),
            'no-fuzz': sim_report('a' * 40, '3.0.21', fuzz=None),
            'fuzz-failed': sim_report('a' * 40, '3.0.21', fuzz={'verdict': 'fail', 'seeds': 50}),
            'fuzz-small': sim_report('a' * 40, '3.0.21', fuzz={'verdict': 'pass', 'seeds': 1}),
            'wrong-kind': sim_report('a' * 40, '3.0.21', kind='other'),
            # Review finding: counts alone could be satisfied by invented rows.
            'invented-ids': sim_report('a' * 40, '3.0.21', scenarios=[
                {'id': f'made-up/{i}', 'verdict': 'pass'} for i in range(release.SIM_MIN_SCENARIOS)]),
            'missing-scenario': sim_report('a' * 40, '3.0.21', scenarios=[
                {'id': name, 'verdict': 'pass'} for name in sorted(CATALOG)[1:]] + [
                {'id': 'extra/one', 'verdict': 'pass'}]),
        }.items():
            out = self.root / f'qa-{name}'
            path = self.root / f'sim-{name}.json'
            if report is not None:
                path.write_text(json.dumps(report))
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.stage(self.build, out, '3.0.21', False, self.context, path if report else None)
            self.assertFalse(out.exists(), name)

    def test_simulator_report_travels_with_the_tested_attempt(self):
        provenance = json.loads((self.assets / 'qa-provenance.json').read_text())
        self.assertEqual(provenance['sim_report_sha256'], release.digest(self.assets / release.SIM_REPORT))
        report_path = self.assets / release.SIM_REPORT
        original = report_path.read_text()
        # Tampering with the report breaks the provenance checksum.
        report_path.write_text(json.dumps(sim_report('a' * 40, '3.0.21', verdict='fail')))
        with self.assertRaisesRegex(ValueError, 'Simulator report checksum'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)
        # A consistent but failing report (checksum updated too) still fails closed.
        path = self.assets / 'qa-provenance.json'
        path.write_text(json.dumps(dict(provenance, sim_report_sha256=release.digest(report_path))))
        with self.assertRaisesRegex(ValueError, 'Simulator'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)
        # An artifact without the report (an old QA run) cannot be promoted.
        report_path.unlink()
        path.write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'Unexpected QA assets'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)
        report_path.write_text(original)
        release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)
        # A report from a different source SHA cannot ride along with these bytes.
        with self.assertRaisesRegex(ValueError, 'source SHA'):
            release.validate_sim_report(json.loads(original), 'b' * 40, '3.0.21')

    def test_real_scenario_catalog_is_read_from_the_checkout(self):
        root = Path(__file__).resolve().parents[2] / 'omi' / 'sim' / 'scenarios'
        ids = REAL_SIM_CATALOG(root)
        self.assertGreaterEqual(len(ids), release.SIM_MIN_SCENARIOS)
        self.assertIn('safe/poweron-hold-then-cold-boot', ids)

    def test_repackage_only_app_preserves_bytes_and_metadata(self):
        with zipfile.ZipFile(self.assets / release.asset_names('3.0.21')[0]) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json', 'omi.signed.bin'})
            self.assertEqual(archive.read('omi.signed.bin'), self.payload)
            manifest = release.ota_manifest(archive)
            self.assertEqual(manifest['files'], self.manifest['files'][:1])
            self.assertEqual(manifest['time'], 123)
        app_hex, net_hex = release.asset_names('3.0.21')[1:]
        self.assertEqual(read_hex(self.assets / app_hex), boot.wire_memory(self.payload, self.boot_image))
        self.assertEqual((self.build / 'merged_CPUNET.hex').read_bytes(), (self.assets / net_hex).read_bytes())

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
        release.validate_run(self.run, 42, 'BasedHardware/omi', 'a' * 40, '123', '1')
        for key, value in {
            'id': 456,
            'run_attempt': 2,
            'workflow_id': 99,
            'path': 'other.yml',
            'event': 'push',
            'repository': {'full_name': 'fork/omi'},
            'head_sha': 'b' * 40,
            'status': 'in_progress',
            'conclusion': 'failure',
        }.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                release.validate_run(dict(self.run, **{key: value}), 42, 'BasedHardware/omi', 'a' * 40, '123', '1')

    def test_provenance_gate(self):
        release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)
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
                release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)
        path.write_text(json.dumps(original))
        (self.assets / release.asset_names('3.0.21')[1]).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            release.validate_assets(self.assets, self.run, '3.0.21', False, self.signed_sha256)

    def test_promote_downloads_and_preserves_exact_tested_files(self):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            if args[0] == 'api':
                return json.dumps({'id': 42} if 'workflows/' in args[1] else self.run)
            self.assertEqual(args[:3], ('run', 'download', '123'))
            self.assertIn(f'{release.ARTIFACT}-123-1', args)
            shutil.copytree(self.assets, Path(args[-1]), dirs_exist_ok=True)
            return ''

        target = self.root / 'promoted'
        with patch.object(release, 'gh', side_effect=fake_gh):
            release.promote(
                target,
                '3.0.21',
                False,
                '123',
                '1',
                self.signed_sha256,
                'BasedHardware/omi',
                'a' * 40,
                'refs/heads/main',
            )
        for name in release.asset_names('3.0.21'):
            self.assertEqual((target / name).read_bytes(), (self.assets / name).read_bytes())
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[1][1].endswith('/runs/123/attempts/1'))

    def test_missing_run_and_non_main_fail_before_network(self):
        for run_id, ref in [('', 'refs/heads/main'), ('123', 'refs/heads/topic')]:
            with patch.object(release, 'gh') as gh, self.assertRaises(ValueError):
                release.promote(
                    self.root / 'out',
                    '3.0.21',
                    False,
                    run_id,
                    '1',
                    self.signed_sha256,
                    'BasedHardware/omi',
                    'a' * 40,
                    ref,
                )
            gh.assert_not_called()

    def test_promotion_requires_attempt_and_bench_hash_before_network(self):
        for attempt, checksum in [('', self.signed_sha256), ('0', self.signed_sha256), ('1', ''), ('1', 'bad')]:
            with self.subTest(attempt=attempt, checksum=checksum), patch.object(release, 'gh') as gh:
                with self.assertRaises(ValueError):
                    release.promote(
                        self.root / 'out',
                        '3.0.21',
                        False,
                        '123',
                        attempt,
                        checksum,
                        'BasedHardware/omi',
                        'a' * 40,
                        'refs/heads/main',
                    )
                gh.assert_not_called()

    def test_rerun_cannot_replace_tested_attempt_or_bytes(self):
        target = self.root / 'promoted'

        def fake_gh(*args):
            if args[0] == 'api':
                if 'workflows/' in args[1]:
                    return json.dumps({'id': 42})
                # Even if a run-wide query would return attempt 2, select 1.
                return json.dumps(self.run if args[1].endswith('/attempts/1') else dict(self.run, run_attempt=2))
            self.assertIn(f'{release.ARTIFACT}-123-1', args)
            shutil.copytree(self.assets, Path(args[-1]), dirs_exist_ok=True)
            return ''

        with patch.object(release, 'gh', side_effect=fake_gh):
            release.promote(
                target,
                '3.0.21',
                False,
                '123',
                '1',
                self.signed_sha256,
                'BasedHardware/omi',
                'a' * 40,
                'refs/heads/main',
            )
            # Self-consistent artifact checksums cannot replace the bench hash.
            with self.assertRaisesRegex(ValueError, 'signed image SHA-256'):
                release.promote(
                    self.root / 'wrong-hash',
                    '3.0.21',
                    False,
                    '123',
                    '1',
                    '0' * 64,
                    'BasedHardware/omi',
                    'a' * 40,
                    'refs/heads/main',
                )
        with patch.object(
            release, 'gh', side_effect=[json.dumps({'id': 42}), json.dumps(dict(self.run, run_attempt=2))]
        ) as gh:
            with self.assertRaisesRegex(ValueError, 'attempt mismatch'):
                release.promote(
                    self.root / 'wrong-attempt',
                    '3.0.21',
                    False,
                    '123',
                    '1',
                    self.signed_sha256,
                    'BasedHardware/omi',
                    'a' * 40,
                    'refs/heads/main',
                )
            self.assertEqual(gh.call_count, 2)

    def test_attempt_scoped_artifact_missing_fails_closed(self):
        with patch.object(
            release,
            'gh',
            side_effect=[
                json.dumps({'id': 42}),
                json.dumps(self.run),
                subprocess.CalledProcessError(1, ['gh']),
            ],
        ) as gh:
            with self.assertRaises(subprocess.CalledProcessError):
                release.promote(
                    self.root / 'missing',
                    '3.0.21',
                    False,
                    '123',
                    '1',
                    self.signed_sha256,
                    'BasedHardware/omi',
                    'a' * 40,
                    'refs/heads/main',
                )
            self.assertEqual(gh.call_count, 3)  # Never fall back to a run-wide artifact.

    def test_rollout_guard_and_emergency_exception(self):
        for percent in ('0', '1'):
            release.validate_policy(percent, 'false')
        for percent in ('2', '10', '100'):
            with self.subTest(percent=percent), self.assertRaisesRegex(ValueError, '0 or 1'):
                release.validate_policy(percent, 'false')
            release.validate_policy(percent, 'false', emergency=True)
        for percent in ('-1', '101', '1.5', '1\n', 'bad'):
            with self.subTest(percent=percent), self.assertRaises(ValueError):
                release.validate_policy(percent, 'false', emergency=True)

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
            QA_RUN_ATTEMPT='',
            TESTED_SIGNED_SHA256='',
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

    def publish_responses(self):
        tag_ref = json.dumps({'object': {'type': 'commit', 'sha': 'a' * 40}})
        return ['', tag_ref, '', json.dumps({'isDraft': True, 'tagName': 'Omi_CV1_v3.0.21'}), tag_ref, '']

    def publish_env(self):
        (self.root / 'cv1-validated-run.json').write_text(json.dumps({'run': self.run, 'workflow_id': 42}))
        return dict(
            os.environ,
            VERSION_INPUT='3.0.21',
            PUBLISH='publish',
            QA_RUN_ID='123',
            QA_RUN_ATTEMPT='1',
            TESTED_SIGNED_SHA256=self.signed_sha256,
            GITHUB_REF='refs/heads/main',
            GITHUB_SHA='a' * 40,
            GITHUB_REPOSITORY='BasedHardware/omi',
            INCLUDE_NETWORK_CORE='false',
            OUT=str(self.assets),
            BODY_FILE='body.md',
        )

    def test_publish_uses_only_verified_release_assets(self):
        env = self.publish_env()
        with patch.dict(os.environ, env, clear=True), patch.object(
            sys, 'argv', ['cv1_release.py', 'publish']
        ), patch.object(release, 'gh') as gh:
            gh.side_effect = self.publish_responses()
            release.main()
            args = gh.call_args_list[2].args
            self.assertEqual(args[:3], ('release', 'create', 'Omi_CV1_v3.0.21'))
            self.assertEqual(list(args[-3:]), [str(self.assets / n) for n in release.asset_names('3.0.21')])
            self.assertNotIn('qa-provenance.json', ' '.join(args))
            self.assertNotIn(release.SIM_REPORT, ' '.join(args))
            self.assertNotIn('.elf', ' '.join(args))
            self.assertIn('--draft', args)
            self.assertIn('--verify-tag', args)
            # The draft lookup must not use GET releases/tags/{tag}, which 404s on drafts.
            self.assertEqual(
                gh.call_args_list[3].args,
                ('release', 'view', 'Omi_CV1_v3.0.21', '--repo', 'BasedHardware/omi', '--json', 'isDraft,tagName'),
            )
            self.assertEqual(
                gh.call_args_list[0].args,
                (
                    'api',
                    '--method',
                    'POST',
                    'repos/BasedHardware/omi/git/refs',
                    '-f',
                    'ref=refs/tags/Omi_CV1_v3.0.21',
                    '-f',
                    'sha=' + 'a' * 40,
                ),
            )
            self.assertEqual(gh.call_args.args[:3], ('release', 'edit', 'Omi_CV1_v3.0.21'))
            gh.reset_mock()
            (self.assets / release.asset_names('3.0.21')[1]).write_bytes(b'changed after promotion')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                release.main()
            gh.assert_not_called()

    def test_publish_refuses_existing_tag_or_mismatched_release_tag(self):
        for failure in ('existing', 'before-create', 'after-create', 'release-tag'):
            responses = self.publish_responses()
            if failure == 'existing':
                responses[0] = subprocess.CalledProcessError(1, ['gh'], stderr='Reference already exists')
            elif failure == 'release-tag':
                responses[3] = json.dumps({'isDraft': True, 'tagName': 'other-tag'})
            else:
                responses[1 if failure == 'before-create' else 4] = json.dumps(
                    {'object': {'type': 'commit', 'sha': 'b' * 40}}
                )
            with self.subTest(failure=failure), patch.dict(os.environ, self.publish_env(), clear=True), patch.object(
                sys, 'argv', ['cv1_release.py', 'publish']
            ), patch.object(release, 'gh', side_effect=responses) as gh:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    release.main()
                self.assertFalse(any(call.args[:2] == ('release', 'edit') for call in gh.call_args_list))
                if failure in ('existing', 'before-create'):
                    self.assertFalse(any(call.args[:2] == ('release', 'create') for call in gh.call_args_list))

    def test_publish_rechecks_bench_receipt_and_rollout_before_writes(self):
        for override in (
            {'QA_RUN_ATTEMPT': '2'},
            {'TESTED_SIGNED_SHA256': '0' * 64},
            {'ROLLOUT_PERCENT': '2'},
        ):
            with self.subTest(override=override), patch.dict(
                os.environ, dict(self.publish_env(), **override), clear=True
            ), patch.object(sys, 'argv', ['cv1_release.py', 'publish']), patch.object(release, 'gh') as gh:
                with self.assertRaises(ValueError):
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
        # Exercise the actual backend parser without importing service clients.
        source = Path(__file__).resolve().parents[4] / 'backend/utils/github_releases.py'
        node = next(
            n
            for n in ast.parse(source.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == 'extract_key_value_pairs'
        )
        namespace = {'re': re, 'Dict': dict, 'Any': object}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        parsed = namespace['extract_key_value_pairs'](body.read_text())
        self.assertEqual(parsed['rollout_percent'], '1')
        self.assertEqual(parsed['blocked'], 'false')
        self.assertEqual(parsed['release_firmware_version'], '3.0.21')
        self.assertTrue(body.read_text().index('changelog:') < body.read_text().index('release_firmware_version:'))

    def test_body_refuses_metadata_injection_from_every_input(self):
        body = self.root / 'injected.md'
        script = Path(__file__).with_name('make-release-body.sh')
        env = dict(os.environ, TITLE='CV1', VER='3.0.21', OUT=str(body), ROLLOUT_PERCENT='1', BLOCKED='true')
        inputs = (
            'TITLE',
            'VER',
            'CHANGELOG',
            'MIN_FW',
            'MIN_APP',
            'MIN_APP_CODE',
            'OTA_STEPS',
            'IS_LEGACY_SECURE_DFU',
            'ROLLOUT_PERCENT',
            'BLOCKED',
            'HOW_TO_FLASH',
        )
        for name in inputs:
            for injected in (
                'notes\n  rollout_percent :100',
                'notes\r\n\tblocked : false',
                'notes\nrelease_firmware_version:3.0.99',
                'notes\n minimum_app_version :0',
                '<!-- KEY_VALUE_START\nblocked:false\nKEY_VALUE_END -->',
            ):
                with self.subTest(name=name, injected=injected):
                    result = subprocess.run(
                        ['bash', str(script)], env=dict(env, **{name: injected}), capture_output=True
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(body.exists())

    def test_body_allows_multiline_prose_and_values_containing_colons(self):
        body = self.root / 'multiline.md'
        script = Path(__file__).with_name('make-release-body.sh')
        subprocess.run(
            ['bash', str(script)],
            env=dict(
                os.environ,
                TITLE='CV1',
                VER='3.0.21',
                OUT=str(body),
                CHANGELOG='Audio: improved\nBattery improved|Reconnect fixes',
                ROLLOUT_PERCENT='1',
                BLOCKED='false',
            ),
            check=True,
            capture_output=True,
        )
        self.assertIn('rollout_percent:1\nblocked:false', body.read_text())


if __name__ == '__main__':
    unittest.main()
