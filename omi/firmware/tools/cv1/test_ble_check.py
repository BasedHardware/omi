import json
from pathlib import Path
import shlex
import subprocess
import stat
import tempfile
import unittest
from unittest import mock

from bench_loop import StageFailed
from ble_check import BLECheck, MAX_RECEIPT_BYTES


class BLETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'receipt.json'
        self.serial = 'synthetic-private-serial'
        self.profile = dict(ssh_host='synthetic-receiver', app='/tmp/Helper App.app',
                            receipt_dir='/tmp/receipts', expected_serial=self.serial)
        self.runner = self.receipt_runner(dict(outcome='passed', identity=dict(status='matched')))

    @staticmethod
    def receipt_runner(receipt):
        return mock.Mock(side_effect=[subprocess.CompletedProcess([], 0, b''),
                                      subprocess.CompletedProcess([], 0, json.dumps(receipt).encode()),
                                      subprocess.CompletedProcess([], 0, b'')])

    def test_fixed_launch_and_fetch(self):
        self.assertEqual(BLECheck(self.profile, self.path, self.runner)()['result'], 'passed')
        launch, fetch, remove = self.runner.call_args_list
        self.assertEqual(launch.args[0][:4], ['/usr/bin/ssh', '-oBatchMode=yes', '-oConnectTimeout=10', 'synthetic-receiver'])
        argv = shlex.split(launch.args[0][4])
        self.assertEqual(argv[:10], ['/usr/bin/open', '-n', '-W', '/tmp/Helper App.app', '--args', 'session', '--seconds', '20', '--output', argv[9]])
        self.assertEqual(argv[10:], ['--expect-serial', self.serial])
        self.assertEqual(shlex.split(fetch.args[0][4]), ['/usr/bin/head', '-c', str(MAX_RECEIPT_BYTES + 1), argv[9]])
        self.assertEqual(shlex.split(remove.args[0][4]), ['/bin/rm', '-f', argv[9]])
        self.assertEqual(json.loads(self.path.read_bytes())['outcome'], 'passed')
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_outcomes_with_matched_identity(self):
        for outcome, result in [('passed', 'passed'), ('no_advertisement', 'skipped'),
                                ('permission_denied', 'skipped'), ('connect_failed', 'skipped'),
                                ('gatt_failed', 'failed'), ('audio_failed', 'failed'),
                                ('bluetooth_off', 'skipped'), ('interrupted', 'skipped'), ('unknown', 'failed')]:
            with self.subTest(outcome=outcome):
                runner = self.receipt_runner(dict(outcome=outcome, identity=dict(status='matched')))
                r = BLECheck(self.profile, self.path.with_name(outcome + '.json'), runner)()
                self.assertEqual(r['result'], result)
                if result == 'skipped':
                    self.assertEqual(r['reason'], outcome + ': BLE was not tested')
                    self.assertNotIn(self.serial, json.dumps(r))

    def test_unknown_outcome_stays_out_of_the_reason(self):
        r = BLECheck(self.profile, self.path, self.receipt_runner(dict(outcome=self.serial)))()
        self.assertEqual(r, dict(result='failed', reason='ble_unknown_outcome'))

    def test_oversized_receipt_is_refused_and_not_stored(self):
        runner = mock.Mock(side_effect=[subprocess.CompletedProcess([], 0, b''),
                                        subprocess.CompletedProcess([], 0, b' ' * (MAX_RECEIPT_BYTES + 1)),
                                        subprocess.CompletedProcess([], 0, b'')])
        with self.assertRaises(StageFailed) as caught:
            BLECheck(self.profile, self.path, runner)()
        self.assertEqual(caught.exception.code, 'ble_invalid_receipt')
        self.assertFalse(self.path.exists())

    def test_failed_remote_cleanup_keeps_the_result(self):
        runner = mock.Mock(side_effect=[subprocess.CompletedProcess([], 0, b''),
                                        subprocess.CompletedProcess([], 0, json.dumps(dict(outcome='passed', identity=dict(status='matched'))).encode()),
                                        subprocess.TimeoutExpired('ssh', 20)])
        self.assertEqual(BLECheck(self.profile, self.path, runner)()['result'], 'passed')

    def test_missing_local_receipt_directory_is_refused_up_front(self):
        runner = mock.Mock()
        with self.assertRaises(NotADirectoryError):
            BLECheck(self.profile, Path(self.tmp.name) / 'missing' / 'receipt.json', runner)
        runner.assert_not_called()

    def test_pass_requires_established_identity(self):
        identities = [None, {}, [], dict(status=None), dict(status='not_requested'),
                      dict(status='pending'), dict(status='wrong'), dict(status='absent'),
                      dict(status=self.serial)]
        for i, identity in enumerate(identities):
            with self.subTest(identity=identity):
                receipt = dict(outcome='passed', details=self.serial)
                if identity is not None:
                    receipt['identity'] = identity
                r = BLECheck(self.profile, self.path.with_name(str(i)), self.receipt_runner(receipt))()
                self.assertEqual(r['result'], 'skipped')
                expected = (f"identity_{identity['status']} (passed): identity was not established; BLE was not tested"
                            if isinstance(identity, dict) and identity.get('status') in ('wrong', 'absent')
                            else 'identity_not_established: BLE was not tested')
                self.assertEqual(r['reason'], expected)
                self.assertNotIn(self.serial, json.dumps(r))

    def test_profile_without_serial_cannot_pass_even_with_matched_receipt(self):
        profile = dict(self.profile)
        del profile['expected_serial']
        r = BLECheck(profile, self.path, self.runner)()
        self.assertEqual(r, dict(result='skipped', reason='identity_not_established: BLE was not tested'))
        self.assertNotIn('--expect-serial', shlex.split(self.runner.call_args_list[0].args[0][4]))

    def test_wrong_or_absent_identity_skips_without_leaking_serial(self):
        for status in ('wrong', 'absent'):
            for outcome in ('gatt_failed', 'passed', 'bluetooth_off', 'connect_failed'):
                with self.subTest(status=status, outcome=outcome):
                    receipt = dict(outcome=outcome, identity=dict(status=status, expectedSerial=self.serial,
                                   observedSerial=self.serial + '-other'), details=self.serial)
                    r = BLECheck(self.profile, self.path.with_name(status + outcome), self.receipt_runner(receipt))()
                    reason = f'identity_{status} ({outcome}): identity was not established; BLE was not tested'
                    self.assertEqual(r, dict(result='skipped', reason=reason))
                    self.assertNotIn(self.serial, json.dumps(r))

    def test_only_passed_outcome_can_pass_and_unknowns_still_fail(self):
        for i, (outcome, status) in enumerate([('gatt_failed', 'pending'), ('audio_failed', 'matched'),
                                             ('unknown', 'wrong'), ('unknown', 'absent')]):
            r = BLECheck(self.profile, self.path.with_name(str(i)), self.receipt_runner(
                dict(outcome=outcome, identity=dict(status=status))))()
            self.assertEqual(r['result'], 'failed')

    def test_audio_bounded_and_serial_quoted_as_one_argument(self):
        serial = 'synthetic; $(false) serial'
        r = BLECheck(dict(self.profile, mode='audio', expected_serial=serial), self.path, self.runner)()
        self.assertEqual(r['result'], 'passed')
        args = shlex.split(self.runner.call_args_list[0].args[0][4])
        self.assertEqual(args[5:8], ['audio', '--seconds', '3'])
        self.assertEqual(args[-2:], ['--expect-serial', serial])

    def test_bad_profile_never_launches(self):
        for changed in [dict(ssh_host='-oProxyCommand=bad'), dict(ssh_host='alias;bad'),
                        dict(app='relative.app'), dict(mode='scan'), dict(mode='audio', expected_serial=None)]:
            with self.assertRaises(ValueError):
                BLECheck(dict(self.profile, **changed), self.path, self.runner)
        self.runner.assert_not_called()

    def test_launch_and_fetch_errors_skip_without_exception_secrets(self):
        failures = [subprocess.TimeoutExpired(['fake', self.serial], 1, output=self.serial, stderr=self.serial),
                    subprocess.CalledProcessError(1, ['fake', self.serial], output=self.serial, stderr=self.serial),
                    OSError(self.serial)]
        for i, failure in enumerate(failures):
            for fetch in (False, True):
                with self.subTest(failure=type(failure).__name__, fetch=fetch):
                    effects = [subprocess.CompletedProcess([], 0, b'')] if fetch else []
                    runner = mock.Mock(side_effect=effects + [failure])
                    path = self.path.with_name(f'{i}-{fetch}')
                    r = BLECheck(self.profile, path, runner)()
                    self.assertEqual(r, dict(result='skipped', reason='central_unreachable: BLE was not tested'))
                    self.assertNotIn(self.serial, json.dumps(r))
                    self.assertEqual(runner.call_count, 2 if fetch else 1)
                    self.assertFalse(path.exists())

    def test_malformed_and_empty_arrived_receipts_still_fail(self):
        for i, data in enumerate((b'', b'{}', b'[]', b'invalid', b'{"outcome":"passed","outcome":"gatt_failed"}')):
            runner = mock.Mock(side_effect=[subprocess.CompletedProcess([], 0, b''), subprocess.CompletedProcess([], 0, data),
                                            subprocess.CompletedProcess([], 0, b'')])
            path = self.path.with_name(str(i))
            with self.assertRaises(StageFailed) as caught:
                BLECheck(self.profile, path, runner)()
            self.assertEqual(caught.exception.code, 'ble_invalid_receipt')
            self.assertEqual(path.read_bytes(), data)

    def test_local_receipt_io_errors_still_fail(self):
        with mock.patch('ble_check.os.open', side_effect=OSError('local disk full')):
            with self.assertRaises(OSError):
                BLECheck(self.profile, self.path, self.runner)()

    def test_existing_receipt_refused(self):
        self.path.write_text('keep')
        with self.assertRaises(FileExistsError):
            BLECheck(self.profile, self.path, self.runner)
        self.runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
