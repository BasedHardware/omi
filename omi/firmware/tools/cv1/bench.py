#!/usr/bin/env python3
"""Software-only CV1 orchestration primitives. No hardware adapter is enabled."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True) + '\n'
    if exclusive:
        with path.open('x') as stream:
            stream.write(text)
    else:
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_text(text)
        os.replace(temp, path)


class Busy(RuntimeError):
    pass


class Lease:
    """One cooperative, whole-bench lock. Never delete/steal by age or PID."""
    def __init__(self, folder, owner):
        self.folder = Path(folder)
        self.owner = owner
        self.clean = False

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.fd = (self.folder / 'bench.lock').open('a+')
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fd.close()
            raise Busy('bench lease already held')
        metadata = self.folder / 'lease.json'
        try:
            previous = json.loads(metadata.read_text()) if metadata.exists() else {}
            if previous.get('state') not in (None, 'idle'):
                raise Busy('prior lease not cleanly closed; quarantine requires operator review')
            self.record = {'state': 'held', 'owner': self.owner, 'pid': os.getpid(),
                           'host': socket.gethostname(), 'acquired_at': utc(),
                           'resource': 'CV1-whole-bench', 'token': str(uuid.uuid4())}
            save(metadata, self.record)
            return self
        except BaseException:
            self.fd.close()
            raise

    def __exit__(self, typ, value, traceback):
        try:
            self.record.update(state='idle' if self.clean else 'quarantined',
                               released_at=utc(), cleanup_verified=self.clean)
            save(self.folder / 'lease.json', self.record)
        finally:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()


def hex_ranges(path):
    """Validate Intel HEX checksums and record explicit addressed bytes, not gaps."""
    upper = 0
    ranges = []
    ended = False
    for text in Path(path).read_text().splitlines():
        if not text:
            continue
        if ended or not text.startswith(':'):
            raise ValueError('bad Intel HEX record or data after EOF')
        raw = bytes.fromhex(text[1:])
        if len(raw) < 5 or raw[0] + 5 != len(raw) or sum(raw) % 256:
            raise ValueError('Intel HEX length/checksum mismatch')
        length, kind = raw[0], raw[3]
        addr = int.from_bytes(raw[1:3], 'big')
        data = raw[4:-1]
        if kind == 0 and length:
            ranges.append((upper + addr, upper + addr + length))
        elif kind == 1:
            if length != 0:
                raise ValueError('bad EOF')
            ended = True
        elif kind in (2, 4):
            if length != 2:
                raise ValueError('bad extended address')
            upper = int.from_bytes(data, 'big') << (4 if kind == 2 else 16)
        elif kind not in (0, 3, 5):
            raise ValueError('unknown Intel HEX record type')
    if not ended:
        raise ValueError('missing Intel HEX EOF')
    merged = []
    for lo, hi in sorted(ranges):
        if merged and lo < merged[-1][1]:
            raise ValueError('overlapping Intel HEX data')
        if merged and lo == merged[-1][1]:
            merged[-1][1] = max(hi, merged[-1][1])
        else:
            merged.append([lo, hi])
    return [{'start': hex(lo), 'end_exclusive': hex(hi)} for lo, hi in merged]


def verify_manifest(path):
    path = Path(path)
    value = json.loads(path.read_text())
    for item in value['artifacts']:
        snapshot = (path.parent / item['snapshot']).resolve(strict=True)
        if snapshot.parent != path.parent.resolve() or digest(snapshot) != item['sha256']:
            raise ValueError('manifest artifact path/hash mismatch')
    return value


def manifest(folder, role, artifacts, revision, baseline=None):
    if role not in ('baseline', 'candidate'):
        raise ValueError('invalid role')
    if role == 'candidate' and not baseline:
        raise ValueError('candidate requires baseline manifest')
    baseline_ref = None
    if baseline:
        base = verify_manifest(baseline)
        if base['role'] != 'baseline':
            raise ValueError('reference must be a baseline')
        baseline_ref = {'path': str(Path(baseline).resolve()), 'sha256': digest(baseline)}
    run = Path(folder) / (role + '-' + uuid.uuid4().hex)
    run.mkdir(parents=True, exist_ok=False)
    items = []
    for index, artifact in enumerate(artifacts):
        source = Path(artifact).resolve(strict=True)
        if not source.is_file():
            raise ValueError('artifact must be a regular file')
        before = digest(source)
        copy = run / ('%02d-' % index + source.name)
        # Copy exact bytes; never mutate the SDK build or granted scanner app.
        with source.open('rb') as inp, copy.open('xb') as out:
            for block in iter(lambda: inp.read(1024 * 1024), b''):
                out.write(block)
        if digest(copy) != before or digest(source) != before:
            raise ValueError('source artifact changed during snapshot')
        item = {'source': str(source), 'snapshot': copy.name,
                'sha256': digest(copy), 'size_bytes': copy.stat().st_size}
        if source.suffix.lower() == '.hex':
            item['address_ranges'] = hex_ranges(copy)
        items.append(item)
    result = {'schema_version': 1, 'run_id': run.name, 'role': role,
              'created_at': utc(), 'source_revision_claim': revision,
              'fresh_build_verified': False, 'installed_on_device_verified': False,
              'hardware_acceptance': 'unqualified', 'baseline': baseline_ref,
              'artifacts': items}
    save(run / 'manifest.json', result, exclusive=True)
    return run / 'manifest.json'


def validate_corpus(record, root):
    if record.get('schema_version') != 1 or record.get('provenance') not in ('operator_supplied', 'synthetic'):
        raise ValueError('explicit operator_supplied/synthetic provenance required')
    if record['provenance'] == 'synthetic':
        if 'source' in record or 'observation' in record or not record.get('scenario'):
            raise ValueError('synthetic scenarios must not impersonate observed receipts')
        if 'stimulus' not in record or 'expected' not in record:
            raise ValueError('synthetic stimulus/expected required')
    else:
        if any(key in record for key in ('expected', 'stimulus', 'scenario')):
            raise ValueError('operator-supplied observations cannot include invented expectations/stimuli')
        source = record['source']
        if source['kind'] != 'ble_scan_json':
            raise ValueError('only existing BLE scan receipts currently supported')
        path = (Path(root) / source['snapshot']).resolve(strict=True)
        if path.parent != Path(root).resolve():
            raise ValueError('receipt snapshot must remain within corpus')
        if digest(path) != source['sha256']:
            raise ValueError('supplied source hash mismatch')
        observation = json.loads(path.read_text())
        if observation != record['observation']:
            raise ValueError('supplied payload differs from receipt')
        if observation.get('state') != 'completed' or observation.get('error') is not None:
            raise ValueError('not a completed observation')
    return True


def corpus(folder, receipts):
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for receipt in receipts:
        src = Path(receipt)
        name = digest(src) + '.json'
        target = root / name
        if not target.exists():
            with target.open('xb') as out:
                out.write(src.read_bytes())
        record = {'schema_version': 1, 'provenance': 'operator_supplied',
                  'source': {'kind': 'ble_scan_json', 'original_path': str(src.resolve()),
                             'snapshot': name, 'sha256': digest(src)},
                  'observation': json.loads(target.read_text())}
        validate_corpus(record, root)
        records.append(record)
    records.append({'schema_version': 1, 'provenance': 'synthetic',
                    'scenario': 'parser-unrelated-device',
                    'stimulus': {'name': 'Other device', 'service_uuids': ['180F']},
                    'expected': {'omi_match': False}})
    for record in records:
        validate_corpus(record, root)
    save(root / 'index.json', records, exclusive=True)
    return root / 'index.json'


def synthetic_run(folder, delay=0.01, timeout=1, ignore_term=False):
    if not 0 < timeout <= 30 or not 0 <= delay <= 60:
        raise ValueError('synthetic limits: timeout (0,30], delay [0,60]')
    root = Path(folder)
    run = root / ('synthetic-' + uuid.uuid4().hex)
    run.mkdir(parents=True)
    result = {'schema_version': 1, 'provenance': 'synthetic', 'hardware_access': False,
              'started_at': utc(), 'timeout_seconds': timeout, 'state': 'starting'}
    with Lease(root / 'lease', run.name) as lease:
        proc = None
        try:
            child = ('import signal,time,sys; '
                     'signal.signal(signal.SIGTERM, signal.SIG_IGN if sys.argv[2]=="1" else signal.SIG_DFL); '
                     'print("synthetic child ready", flush=True); time.sleep(float(sys.argv[1]))')
            with (run / 'stdout.log').open('xb') as stdout:
                proc = subprocess.Popen([sys.executable, '-c', child, str(delay), str(int(ignore_term))],
                                        stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    result['returncode'] = proc.wait(timeout=timeout)
                    result['state'] = 'completed' if proc.returncode == 0 else 'failed'
                except subprocess.TimeoutExpired:
                    result['state'] = 'timeout'
                finally:
                    # This group is created by this run, never a broad process-name kill.
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        result['kill_required'] = True
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=1)
                    group_exists = False
                    try:
                        os.killpg(proc.pid, 0)
                        group_exists = True
                    except ProcessLookupError:
                        pass
                    result['returncode'] = proc.returncode
                    result['direct_child_reaped'] = True
                    result['process_group_absent'] = not group_exists
                    lease.clean = not group_exists
        finally:
            result['completed_at'] = utc()
            result['cleanup_verified'] = lease.clean
            save(run / 'result.json', result, exclusive=True)
    return run / 'result.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('synthetic-run')
    p.add_argument('--output', required=True)
    p.add_argument('--delay', type=float, default=.01)
    p.add_argument('--timeout', type=float, default=1)
    p = sub.add_parser('manifest')
    p.add_argument('--output', required=True)
    p.add_argument('--role', choices=['baseline', 'candidate'], required=True)
    p.add_argument('--artifact', action='append', required=True)
    p.add_argument('--source-revision', required=True)
    p.add_argument('--baseline')
    p = sub.add_parser('preflight')
    p.add_argument('manifest')
    p.add_argument('--contract', required=True)
    p = sub.add_parser('corpus')
    p.add_argument('--output', required=True)
    p.add_argument('--receipt', action='append', required=True)
    args = parser.parse_args()
    if args.action == 'preflight':
        from artifact_preflight import evaluate
        try:
            result = evaluate(args.manifest, args.contract)
        except (OSError, ValueError, KeyError, TypeError) as ex:
            result = {'eligible_for_live_identity_gate': False, 'errors': [str(ex)]}
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['eligible_for_live_identity_gate'] else 2)
    if args.action == 'synthetic-run':
        result = synthetic_run(args.output, args.delay, args.timeout)
    elif args.action == 'manifest':
        result = manifest(args.output, args.role, args.artifact, args.source_revision, args.baseline)
    else:
        result = corpus(args.output, args.receipt)
    print(result.resolve())


if __name__ == '__main__':
    main()
