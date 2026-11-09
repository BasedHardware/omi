#!/usr/bin/env python3
"""Run only pre-Bluetooth refusal paths of an already built executable."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main(executable):
    with tempfile.TemporaryDirectory(prefix='cv1-ble-refusals-') as directory:
        root = Path(directory)
        fresh = root / 'new.json'
        expected = ['--expect-serial', 'synthetic-bench']
        cases = 0

        def run(args, code):
            nonlocal cases
            result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=5)
            assert result.returncode == code, (result.returncode, result.stdout, result.stderr)
            cases += 1
            return result

        run(['audio', '--seconds', '3.01', '--output', str(fresh)] + expected, 2)
        assert not fresh.exists()
        for command, serial_flags in [
            ('audio', []), ('audio', ['--expect-serial', '']),
            ('session', ['--expect-serial']), ('session', expected + expected),
            ('scan', expected), ('session', ['--expect-serial', 'bad\nvalue']),
        ]:
            result = run([command, '--seconds', '1', '--output', str(fresh)] + serial_flags, 2)
            # Later lines repeat the usage text, which always names this flag.
            assert '--expect-serial' in result.stderr.splitlines()[0] and not fresh.exists()
        run(['session', '--seconds', 'nan', '--output', str(fresh)], 2)
        assert not fresh.exists()
        existing = root / 'existing.json'
        existing.write_text('preserve me')
        for command in ['scan', 'session', 'audio']:
            run([command, '--seconds', '1', '--output', str(existing)] + (expected if command == 'audio' else []), 2)
            assert existing.read_text() == 'preserve me'
        link = root / 'link.json'
        link.symlink_to(fresh)
        run(['scan', '--seconds', '1', '--output', str(link)], 2)
        assert link.is_symlink() and not fresh.exists()
        run(['scan', '--seconds', '1', '--output', str(root / 'missing' / 'receipt.json')], 2)
        # Audio-file refusal finalizes a receipt before any NSApplication/Bluetooth construction.
        result = run(['audio', '--seconds', '1', '--output', str(fresh), '--keep-audio', str(existing)] + expected, 1)
        receipt = json.loads(fresh.read_text())
        assert result.stdout.strip() == str(fresh)
        assert receipt['outcome'] == 'audio_failed'
        assert not receipt['advertisements'] and not receipt['connections']
        assert receipt['identity'] == {'expectedSerial': 'synthetic-bench', 'checked': False, 'status': 'pending'}
        assert existing.read_text() == 'preserve me'
        assert fresh.stat().st_mode & 0o777 == 0o600
    print(f'PASS: {cases} pre-Bluetooth refusal cases')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check_rejections.py APP/Contents/MacOS/CV1BLECentral')
    main(sys.argv[1])
