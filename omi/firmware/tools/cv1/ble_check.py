"""Post-boot BLE check. Connection details belong only in a private profile.

The injected runner has subprocess.run's argv/timeout/check/capture_output API.
No runner is invoked on import. SSH remote commands are quoted fixed templates;
profile values are data, never command fragments. Receipts may contain private
serials and must remain outside Git.
"""
from pathlib import Path, PurePosixPath
import os
import re
import shlex
import subprocess
import uuid

from artifact_preflight import strict_json
from bench_loop import StageFailed


# Well above any real receipt; a larger one is refused rather than stored.
MAX_RECEIPT_BYTES = 4 * 1024 * 1024


class BLECheck:
    def __init__(self, profile, receipt_path, runner=subprocess.run):
        self.profile = dict(profile)
        self.receipt_path = Path(receipt_path)
        self.runner = runner
        host = self.profile['ssh_host']
        if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', host):
            raise ValueError('ssh_host must be a fixed SSH config host alias')
        for field in ('app', 'receipt_dir'):
            value = self.profile[field]
            if not isinstance(value, str) or not value.startswith('/') or any(c in value for c in '\x00\n\r'):
                raise ValueError(field + ' must be an absolute remote path')
        if not self.profile['app'].endswith('.app'):
            raise ValueError('app must name the helper app bundle')
        if self.profile.get('mode', 'session') not in ('session', 'audio'):
            raise ValueError('BLE mode must be session or audio')
        serial = self.profile.get('expected_serial')
        if serial is not None and (not isinstance(serial, str) or not serial or '\x00' in serial):
            raise ValueError('invalid expected_serial')
        if self.profile.get('mode') == 'audio' and not serial:
            raise ValueError('audio requires a private expected_serial')
        if self.receipt_path.exists() or self.receipt_path.is_symlink():
            raise FileExistsError(self.receipt_path)
        if not self.receipt_path.parent.is_dir():
            raise NotADirectoryError(self.receipt_path.parent)

    def remote(self, argv, timeout):
        # ssh joins its remote argv into shell text: quote each argument explicitly.
        return self.runner(['/usr/bin/ssh', '-oBatchMode=yes', '-oConnectTimeout=10',
                            self.profile['ssh_host'], shlex.join(argv)],
                           timeout=timeout, check=True, capture_output=True)

    def __call__(self):
        mode = self.profile.get('mode', 'session')
        remote_path = str(PurePosixPath(self.profile['receipt_dir']) / ('cv1-' + uuid.uuid4().hex + '.json'))
        argv = ['/usr/bin/open', '-n', '-W', self.profile['app'], '--args', mode,
                '--seconds', '3' if mode == 'audio' else '20', '--output', remote_path]
        if self.profile.get('expected_serial'):
            argv += ['--expect-serial', self.profile['expected_serial']]
        try:
            self.remote(argv, 65)
            data = self.remote(['/usr/bin/head', '-c', str(MAX_RECEIPT_BYTES + 1), remote_path], 20).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            # Remote errors can include argv (and the private serial), stdout or
            # stderr. None of that belongs in the skipped stage's receipt.
            return {'result': 'skipped', 'reason': 'central_unreachable: BLE was not tested'}
        # The remote copy holds private identifiers, and it's already been fetched.
        try:
            self.remote(['/bin/rm', '-f', remote_path], 20)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            pass
        if isinstance(data, str):
            data = data.encode('utf-8')
        if len(data) > MAX_RECEIPT_BYTES:
            raise StageFailed('ble_invalid_receipt', 'receipt too large')
        # Preserve exactly what was fetched, including malformed/empty evidence.
        fd = os.open(self.receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        try:
            receipt = strict_json(data)
            outcome = receipt['outcome']
        except (ValueError, KeyError, TypeError) as failure:
            raise StageFailed('ble_invalid_receipt') from failure
        known = ('passed', 'no_advertisement', 'permission_denied', 'bluetooth_off',
                 'connect_failed', 'gatt_failed', 'audio_failed', 'interrupted')
        if outcome not in known:
            # An unknown value is untrusted receipt data, so it stays out of the summary.
            return {'result': 'failed', 'reason': 'ble_unknown_outcome'}
        identity = receipt.get('identity')
        status = identity.get('status') if isinstance(identity, dict) else None
        if status in ('wrong', 'absent'):
            return {'result': 'skipped', 'reason': f'identity_{status} ({outcome}): '
                    'identity was not established; BLE was not tested'}
        if outcome in ('no_advertisement', 'permission_denied', 'bluetooth_off', 'connect_failed', 'interrupted'):
            return {'result': 'skipped', 'reason': outcome + ': BLE was not tested'}
        if outcome == 'passed':
            if self.profile.get('expected_serial') and status == 'matched':
                return {'result': 'passed', 'outcome': outcome, 'mode': mode}
            return {'result': 'skipped', 'reason': 'identity_not_established: BLE was not tested'}
        return {'result': 'failed', 'reason': 'ble_' + outcome}
