"""Verify loaded OCI identity and owned-tag cleanup without Docker execution."""

import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import qualify_operator as qualify


def image(store='classic-overlay2'):
    checked = {
        'config_digest': 'sha256:' + 'a' * 64,
        'manifest_digest': 'sha256:' + 'b' * 64,
        'layers': [{'diff_id': 'sha256:' + 'c' * 64}],
        'config': {
            'config': {
                'User': '1000:1000',
                'Entrypoint': ['python', 'guard.py'],
                'Cmd': ['--hold'],
                'Env': ['PATH=/opt/bin'],
                'StopSignal': 'SIGTERM',
            }
        },
    }
    actual = {
        'Id': checked['config_digest'],
        'Os': 'linux',
        'Architecture': 'amd64',
        'RootFS': {'Type': 'layers', 'Layers': [row['diff_id'] for row in checked['layers']]},
        'Config': copy.deepcopy(checked['config']['config']),
    }
    actual['Config'].update(Hostname='', AttachStdin=False, OnBuild=None)
    if store == 'containerd':
        actual['Id'] = checked['manifest_digest']
        actual['Descriptor'] = {
            'digest': checked['manifest_digest'],
            'mediaType': 'application/vnd.oci.image.manifest.v1+json',
        }
    return (checked, actual, {'image_store': store})


class NativeIdentityTests(unittest.TestCase):

    def test_classic_store_binds_complete_config_digest(self):
        checked, actual, host = image()
        self.assertEqual(
            qualify.bind_loaded_image(actual, checked, host), (checked['config_digest'], 'classic-config-digest')
        )

    def test_containerd_store_binds_manifest_descriptor(self):
        checked, actual, host = image('containerd')
        self.assertEqual(
            qualify.bind_loaded_image(actual, checked, host),
            (checked['manifest_digest'], 'containerd-manifest-descriptor'),
        )

    def test_same_layers_and_selected_fields_do_not_admit_wrong_id(self):
        for store in ('classic-overlay2', 'containerd'):
            checked, actual, host = image(store)
            actual['Id'] = 'sha256:' + 'd' * 64
            with self.subTest(store=store), self.assertRaises(ValueError):
                qualify.bind_loaded_image(actual, checked, host)

    def test_containerd_missing_or_substituted_descriptor_refused(self):
        for descriptor in (
            None,
            {'digest': 'sha256:' + 'd' * 64, 'mediaType': 'application/vnd.oci.image.manifest.v1+json'},
            {'digest': 'sha256:' + 'b' * 64, 'mediaType': 'application/vnd.oci.image.index.v1+json'},
        ):
            checked, actual, host = image('containerd')
            actual['Descriptor'] = descriptor
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                qualify.bind_loaded_image(actual, checked, host)

    def test_full_runtime_config_platform_and_layers_refused_if_changed(self):
        for mutate in (
            lambda a: a['Config'].update(StopSignal='SIGKILL'),
            lambda a: a['Config'].update(Healthcheck={'Test': ['CMD', 'unexpected']}),
            lambda a: a.update(Os='windows'),
            lambda a: a.update(Architecture='arm64'),
            lambda a: a['RootFS'].update(Layers=[]),
        ):
            checked, actual, host = image()
            mutate(actual)
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                qualify.bind_loaded_image(actual, checked, host)

    def test_unknown_image_store_refused(self):
        checked, actual, host = image('unknown')
        with self.assertRaisesRegex(ValueError, 'STORE_IDENTITY_UNKNOWN'):
            qualify.bind_loaded_image(actual, checked, host)

    def test_native_host_reports_actual_store_or_refuses_unknown(self):
        for driver, status, expected in (
            ('overlay2', [], 'classic-overlay2'),
            ('overlayfs', [['driver-type', 'io.containerd.snapshotter.v1']], 'containerd'),
            ('unknown', [], None),
        ):
            info = {
                'OSType': 'linux',
                'Architecture': 'x86_64',
                'KernelVersion': 'kernel',
                'ServerVersion': '28.0.4',
                'Driver': driver,
                'DriverStatus': status,
            }
            with patch.object(qualify.platform, 'system', return_value='Linux'), patch.object(
                qualify.platform, 'machine', return_value='x86_64'
            ), patch.object(qualify.platform, 'release', return_value='kernel'), patch.object(
                qualify.subprocess, 'check_output', side_effect=['"unix:///var/run/docker.sock"', json.dumps(info)]
            ):
                if expected:
                    self.assertEqual(qualify.native_host()['image_store'], expected)
                else:
                    with self.assertRaises(ValueError):
                        qualify.native_host()

    def owned_case(self, *, load_error=None, preexisting=False, wrong_id=False, remove_error=False):
        checked, actual, host = image()
        if wrong_id:
            actual['Id'] = 'sha256:' + 'd' * 64
        state = {'image': actual if preexisting else None}
        calls = []

        def inspect(tag):
            return state['image']

        def command(argv, **kwargs):
            calls.append(argv)
            if argv[:2] == ['docker', 'load']:
                state['image'] = actual
                if load_error:
                    raise load_error
            elif argv == ['docker', 'image', 'rm', 'owned:fixed']:
                if remove_error:
                    raise subprocess.CalledProcessError(1, argv)
                state['image'] = None
            else:
                raise AssertionError(argv)
            return subprocess.CompletedProcess(argv, 0)

        return (checked, host, state, calls, inspect, command)

    def test_partial_load_failure_or_timeout_removes_only_owned_tag(self):
        for error in (
            subprocess.TimeoutExpired(['docker', 'load'], 600),
            subprocess.CalledProcessError(1, ['docker', 'load']),
        ):
            checked, host, state, calls, inspect, command = self.owned_case(load_error=error)
            with tempfile.TemporaryDirectory() as temporary, patch.object(
                qualify, 'inspect_tag', side_effect=inspect
            ), patch.object(qualify.subprocess, 'run', side_effect=command):
                output = Path(temporary) / 'cleanup.json'
                with self.assertRaises(type(error)):
                    with qualify.owned_loaded_image(Path('archive'), 'owned:fixed', checked, host, output):
                        self.fail('failed load yielded executable image')
                self.assertIsNone(state['image'])
                self.assertEqual(calls[-1], ['docker', 'image', 'rm', 'owned:fixed'])
                self.assertTrue(json.loads(output.read_text())['removed'])
                self.assertEqual(len(calls), 2)

    def test_preexisting_tag_never_loaded_or_removed(self):
        checked, host, state, calls, inspect, command = self.owned_case(preexisting=True)
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            qualify, 'inspect_tag', side_effect=inspect
        ), patch.object(qualify.subprocess, 'run', side_effect=command):
            with self.assertRaisesRegex(ValueError, 'PREEXISTING_TAG'):
                with qualify.owned_loaded_image(
                    Path('archive'), 'owned:fixed', checked, host, Path(temporary) / 'cleanup.json'
                ):
                    self.fail('shared tag admitted')
            self.assertEqual(calls, [])
            self.assertIsNotNone(state['image'])

    def test_wrong_loaded_identity_removed_before_any_image_execution(self):
        checked, host, state, calls, inspect, command = self.owned_case(wrong_id=True)
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            qualify, 'inspect_tag', side_effect=inspect
        ), patch.object(qualify.subprocess, 'run', side_effect=command):
            with self.assertRaisesRegex(ValueError, 'CONFIG_DIGEST_CHANGED'):
                with qualify.owned_loaded_image(
                    Path('archive'), 'owned:fixed', checked, host, Path(temporary) / 'cleanup.json'
                ):
                    self.fail('wrong image admitted')
            self.assertIsNone(state['image'])

    def test_cleanup_failure_prevents_qualification_receipt(self):
        checked, host, state, calls, inspect, command = self.owned_case(remove_error=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'archive'
            archive.write_bytes(b'image')
            fixtures = root / 'fixtures'
            fixtures.write_bytes(b'fixture')
            output = root / 'qualification.json'
            contract = {
                'archive_bytes': 5,
                'archive_sha256': hashlib.sha256(b'image').hexdigest(),
                'fixture': {'bytes': 7, 'sha256': hashlib.sha256(b'fixture').hexdigest()},
                'source_sha': 's',
                'readiness_sha256': 'a' * 64,
                'source_tree': 't',
                'build_inputs_sha256': 'i',
                'supervisor_sha256': 'g',
                'oci_manifest_digest': checked['manifest_digest'],
                'loaded_tag': 'owned:fixed',
            }
            with patch.object(qualify, 'native_host', return_value=host), patch.object(
                qualify, 'validate', return_value=checked
            ), patch.object(qualify, 'inspect_tag', side_effect=inspect), patch.object(
                qualify.subprocess, 'run', side_effect=command
            ), patch.object(
                qualify, 'fixture_files', return_value={'source_sha': 's'}
            ), patch.object(
                qualify.image_smoke,
                'run_container',
                side_effect=[
                    json.dumps(
                        {
                            'result': 'SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL',
                            'readiness_sha256': 'a' * 64,
                            'uid': 1000,
                            'full_source_check': True,
                            'credential_refusal_injected': True,
                            'real_credentials_used': False,
                            'sql_called': False,
                            'elapsed_ms': 100,
                        }
                    ),
                    'smoke',
                    'Ran 58 tests in 1.0s\n\nOK\n',
                    'hold',
                ],
            ) as containers, patch.dict(
                os.environ, {'GITHUB_WORKFLOW_SHA': 'w', 'GITHUB_RUN_ID': '1'}
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    qualify.qualify(contract, archive, fixtures, output)
                self.assertEqual(containers.call_args_list[0].kwargs, {'readiness': True})
                self.assertEqual(
                    containers.call_args_list[0].args[0],
                    [
                        '--entrypoint=/opt/operator-venv/bin/python',
                        checked['config_digest'],
                        '-c',
                        qualify.image_smoke.source_refusal_program(contract['readiness_sha256']),
                    ],
                )
                self.assertFalse(output.exists())
                self.assertEqual(
                    json.loads(output.with_suffix('.cleanup.json').read_text())['result'], 'CLEANUP_OUTCOME_UNKNOWN'
                )


if __name__ == '__main__':
    unittest.main()
