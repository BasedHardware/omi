#!/usr/bin/env python3
"""Unattended CV1 app-only bench cycle: admit, flash, verify, boot-check, restore.

The driver owns every safety decision, and an adapter only performs device steps.
This file ships a simulated adapter alone, so `dry-run` never touches hardware.
A live adapter stays in the private bench profile and needs its own release.
"""
import argparse
import json
import re
from pathlib import Path
import sys

from artifact_preflight import digest as digest_bytes, hex_bytes, strict_json
from bench import Busy, Lease, save, utc
from job_dry_run import plan

PAGE = 0x1000
# Application pages only. MCUboot, settings, littlefs, UICR, network and external
# flash addresses are never here, so no job or manifest can authorize them.
APP_PAGES = range(0x10000, 0xf6000, PAGE)
MIN_UPTIME_SECONDS = 30


class CheckSkipped(RuntimeError):
    """A post-boot check could not run; its reason must survive in the report."""


class StageFailed(RuntimeError):
    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def pages(memory):
    return sorted({address - address % PAGE for address in memory})


def need(condition, code, detail=''):
    if not condition:
        raise StageFailed(code, detail)


def erase_list(candidate, restore):
    """Compute the one page list for both directions, before the first erase."""
    selected = sorted(set(pages(candidate)) | set(pages(restore)))
    need(selected, 'empty_page_list')
    outside = [hex(page) for page in selected if page not in APP_PAGES]
    need(not outside, 'page_outside_app_range', ','.join(outside))
    return selected


def pages_match(adapter, memory, selected):
    """Compare whole pages, so a page that failed to erase can't pass as restored."""
    for page in selected:
        data = adapter.read(page, page + PAGE)
        if len(data) != PAGE or any(memory.get(page + i, 0xff) != data[i] for i in range(PAGE)):
            return False
    return True


class Run:
    def __init__(self, adapter, jobs, profile, contract, pins, folder, checks=()):
        self.adapter = adapter
        self.jobs = jobs
        self.profile = profile
        self.contract = contract
        self.protected = pins['protected_sha256']
        self.restore_sha256 = pins['restore_image_sha256']
        self.folder = Path(folder)
        self.stages = []
        self.images = {}
        self.erase = []
        self.checks = checks

    def stage(self, name, action):
        """Record each stage once. Retries do not exist, including for restore."""
        entry = {'stage': name, 'started_at': utc()}
        self.stages.append(entry)
        try:
            entry['receipt'] = action() or {}
            entry['result'] = 'passed'
        except CheckSkipped as failure:
            entry.update(result='skipped', reason=str(failure))
        except StageFailed as failure:
            entry.update(result='failed', code=failure.code, detail=str(failure))
            raise
        except Exception as failure:
            # A device step that errors may have done part of its work.
            entry.update(result='uncertain', code='adapter_error', detail=repr(failure))
            raise StageFailed('adapter_error', repr(failure)) from failure
        finally:
            entry['finished_at'] = utc()
        return entry['result']

    def admit(self):
        """Offline, so a bad job is refused before any device access."""
        receipts = {}
        for role, job in self.jobs.items():
            result = plan(job, self.profile, self.contract)
            artifact_errors = (result['artifact_preflight'] or {}).get('errors', [])
            need(result['plan_valid'], 'job_rejected',
                 f"{role}: {result['errors']} {[error['code'] for error in artifact_errors]}")
            need(result['artifact_preflight']['validated_operation'] == 'reviewed_swd_app_only',
                 'loop_is_app_only', role)
            # Reread only what plan() approved, so a replaced job or manifest is refused.
            job_bytes = Path(job).read_bytes()
            need(digest_bytes(job_bytes) == result['job_sha256'], 'job_changed', role)
            manifest_path = Path(job).parent / strict_json(job_bytes)['artifact_manifest']
            manifest_bytes = manifest_path.read_bytes()
            need(digest_bytes(manifest_bytes) == result['artifact_preflight']['manifest_sha256'],
                 'manifest_changed', role)
            image = strict_json(manifest_bytes)['images'][0]
            # Later stages use these bytes, so a swapped file cannot reach the device.
            data = (manifest_path.parent / image['file']).read_bytes()
            need(digest_bytes(data) == image['sha256'], 'image_hash_mismatch', role)
            (self.folder / f'{role}.hex').write_bytes(data)
            self.images[role] = {'data': data, 'sha256': image['sha256'], 'memory': hex_bytes(data)}
            receipts[role] = {'job_sha256': result['job_sha256'], 'image_sha256': image['sha256']}
        need(self.images['restore']['sha256'] == self.restore_sha256, 'restore_image_not_pinned')
        self.erase = erase_list(self.images['candidate']['memory'], self.images['restore']['memory'])
        self.identity_pin = strict_json(Path(self.profile).read_bytes())['external_target_identity_sha256']
        receipts['erase_pages'] = [hex(page) for page in self.erase]
        return receipts

    def check_protected(self):
        observed = self.adapter.protected_hashes()
        need(observed == self.protected, 'protected_region_changed')
        return observed

    def identity(self):
        observed = self.adapter.identity()
        need(observed.get('external_target_identity_sha256') == self.identity_pin, 'identity_mismatch')
        return observed

    def baseline(self):
        protected = self.check_protected()
        # Whole pages, because restore leaves every byte the image doesn't define erased.
        need(pages_match(self.adapter, self.images['restore']['memory'], self.erase), 'app_not_at_baseline')
        return protected

    def write(self, role):
        image = self.images[role]
        self.identity()
        self.adapter.erase(self.erase)
        self.identity()
        self.adapter.program(image['data'])
        return {'image_sha256': image['sha256'], 'erased_pages': len(self.erase)}

    def verify(self, role):
        need(pages_match(self.adapter, self.images[role]['memory'], self.erase), 'readback_mismatch', role)
        return {'image_sha256': self.images[role]['sha256'], 'protected': self.check_protected()}

    def boot_check(self):
        self.adapter.reset()
        first = self.adapter.tick()
        self.adapter.wait(MIN_UPTIME_SECONDS)
        second = self.adapter.tick()
        need(second['uptime_seconds'] >= first['uptime_seconds'] + MIN_UPTIME_SECONDS, 'uptime_not_advancing')
        need(second['reset_cause'] == first['reset_cause'], 'unexpected_reset')
        return {'first': first, 'second': second}

    def restore(self):
        self.stage('restore_write', lambda: self.write('restore'))
        self.stage('restore_verify', lambda: self.verify('restore'))
        self.stage('restore_boot_check', self.boot_check)

    @staticmethod
    def check(action):
        try:
            receipt = action()
        except (KeyboardInterrupt, SystemExit) as failure:
            raise StageFailed('check_interrupted', type(failure).__name__) from failure
        need(isinstance(receipt, dict), 'invalid_check_result')
        result = receipt.get('result')
        need(result in ('passed', 'failed', 'skipped'), 'invalid_check_result')
        if result == 'skipped':
            need(isinstance(receipt.get('reason'), str) and bool(receipt['reason'].strip()),
                 'missing_skip_reason')
            raise CheckSkipped(receipt['reason'])
        need(result == 'passed', 'check_failed', str(receipt.get('reason', '')))
        return receipt

    def execute(self):
        """Return (result, lease_clean). Restore is the only path out once a write begins."""
        try:
            self.stage('admit', self.admit)
            self.stage('identity', self.identity)
        except StageFailed:
            return 'rejected_device_untouched', True
        try:
            self.stage('baseline_check', self.baseline)
        except StageFailed:
            return 'unexpected_device_state', False
        failed = False
        skipped = False
        try:
            self.stage('flash_candidate', lambda: self.write('candidate'))
            self.stage('verify_candidate', lambda: self.verify('candidate'))
            self.stage('boot_check', self.boot_check)
            for name, action in self.checks:
                skipped |= self.stage(name, lambda: self.check(action)) == 'skipped'
        except StageFailed:
            failed = True
        try:
            self.restore()
        except StageFailed:
            return 'restore_failed_needs_owner', False
        if failed:
            return 'candidate_failed_restored', False
        return ('candidate_incomplete_restored' if skipped else 'candidate_passed_restored'), True


def run(adapter, jobs, profile, contract, pins, bench_dir, output, owner='bench_loop', checks=()):
    """Exit the lease as idle only with restoration proof or an untouched device."""
    # Hooks are trusted controller code, not job-supplied commands.
    checks = list(checks)
    names = [name for name, action in checks]
    reserved = {'admit', 'identity', 'baseline_check', 'flash_candidate', 'verify_candidate',
                'boot_check', 'restore_write', 'restore_verify', 'restore_boot_check'}
    if (any(
            not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name)
            or name in reserved or not callable(action) for name, action in checks)
            or len(set(names)) != len(names)):
        raise ValueError('checks require unique non-reserved names and callable actions')
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    with Lease(bench_dir, owner) as lease:
        cycle = Run(adapter, jobs, profile, contract, pins, folder, checks)
        result, clean = cycle.execute()
        observed = {s['stage']: {k: v for k, v in s.items()
                                if k in ('result', 'reason', 'code', 'detail')}
                    for s in cycle.stages if s['stage'] in names}
        summary = {'schema': 1, 'layer': adapter.layer, 'result': result, 'lease_clean': clean,
                   'hardware_exercised': adapter.layer != 'simulated', 'stages': cycle.stages,
                   'checks_ran': [s['stage'] for s in cycle.stages if s['stage'] in names],
                   'checks': [{'name': name, **observed.get(name, {'result': 'not_run'})}
                              for name in names],
                   'finished_at': utc(), 'release_authorized': False}
        save(folder / 'summary.json', summary, exclusive=True)
        lease.clean = clean
    return summary


class SimulatedBench:
    """In-memory device for the driver's paths. `fail` names the steps that go wrong."""
    layer = 'simulated'

    def __init__(self, identity, protected, app, fail=()):
        self.identity_sha256 = identity
        self.protected = dict(protected)
        self.memory = dict(app)
        self.fail = set(fail)
        self.calls = []
        self.uptime = 0
        self.programs = 0

    def step(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise OSError('simulated failure: ' + name)

    def identity(self):
        self.step('identity')
        return {'external_target_identity_sha256': self.identity_sha256}

    def protected_hashes(self):
        self.step('protected_hashes')
        return dict(self.protected)

    def read(self, start, end):
        self.step('read')
        return bytes(self.memory.get(address, 0xff) for address in range(start, end))

    def erase(self, selected):
        self.step('erase')
        if 'erase_noop' in self.fail:
            return
        for page in selected:
            for address in range(page, page + PAGE):
                self.memory.pop(address, None)

    def program(self, data):
        self.programs += 1
        self.step('program')
        image = sorted(hex_bytes(data).items())
        if f'partial{self.programs}' in self.fail:
            self.memory.update(image[:len(image) // 2])
            raise OSError('simulated failure during write')
        if f'program{self.programs}' in self.fail:
            raise OSError('simulated failure before write')
        self.memory.update(image)

    def reset(self):
        self.step('reset')
        self.uptime = 0

    def tick(self):
        self.step('tick')
        return {'uptime_seconds': self.uptime, 'reset_cause': 0}

    def wait(self, seconds):
        self.calls.append('wait')
        if 'stuck' not in self.fail:
            self.uptime += seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['dry-run'])
    parser.add_argument('--candidate-job', required=True)
    parser.add_argument('--restore-job', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--pins', required=True, help='JSON with protected_sha256 and restore_image_sha256')
    parser.add_argument('--bench-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        pins = strict_json(Path(args.pins).read_bytes())
        restore = strict_json(Path(args.restore_job).read_bytes())
        manifest = Path(args.restore_job).parent / restore['artifact_manifest']
        image = strict_json(manifest.read_bytes())['images'][0]
        app = hex_bytes((manifest.parent / image['file']).read_bytes())
        identity = strict_json(Path(args.profile).read_bytes())['external_target_identity_sha256']
        adapter = SimulatedBench(identity, pins['protected_sha256'], app)
        summary = run(adapter, {'candidate': args.candidate_job, 'restore': args.restore_job},
                      args.profile, args.contract, pins, args.bench_dir, args.output)
    except (Busy, OSError, ValueError, KeyError, TypeError, IndexError) as failure:
        print(json.dumps({'result': 'refused', 'detail': str(failure), 'hardware_exercised': False}))
        return 2
    print(json.dumps(summary, indent=2))
    return 0 if summary['result'] == 'candidate_passed_restored' else 1


if __name__ == '__main__':
    sys.exit(main())
