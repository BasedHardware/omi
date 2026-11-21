# LIFECYCLE: permanent
"""Bounded staging-only control-plane proof for sync pull workers.

Plan is credential-free. Run writes synthetic, audio-free fixtures only. It
does not measure transcription quality, provider cost, or deployed GPU work.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import uuid


class ProbeRefused(RuntimeError):
    pass


def validate_configuration(env: dict[str, str], target: str) -> None:
    from utils.staging_fence import assert_staging_isolation

    if env.get('OMI_DEPLOYMENT') != 'staging' or env.get('OMI_ENV_STAGE') != 'prod':
        raise ProbeRefused('isolated staging deployment required')
    assert_staging_isolation(env)
    parsed = urlsplit(target)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or 'staging' not in parsed.hostname
        or not parsed.hostname.endswith('.run.app')
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        raise ProbeRefused('staging run.app service base required')
    if env.get('SYNC_BACKFILL_WORKER_API_URL') != target or env.get('SYNC_BACKFILL_WORKER_AUDIENCE') != target:
        raise ProbeRefused('target must match configured worker service and audience')
    required = {
        'SYNC_BACKFILL_UID_SEQUENCER': 'on',
        'SYNC_LEDGER_FENCE_MODE': 'active',
        'SYNC_BACKFILL_WORKER_PERCENT': '100',
        'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
        'SYNC_TASKS_PROJECT': 'based-hardware-dev',
    }
    if any(env.get(key) != value for key, value in required.items()):
        raise ProbeRefused('staging pilot flags must be explicitly configured')
    # Cloud Tasks has production defaults: require every fallback binding,
    # rather than letting a missing staging env select one of those defaults.
    for key in ('SYNC_TASKS_HANDLER_URL', 'SYNC_BACKFILL_TASKS_HANDLER_URL'):
        handler = urlsplit(env.get(key, ''))
        if not handler.hostname or 'staging' not in handler.hostname or handler.scheme != 'https':
            raise ProbeRefused('explicit staging task handlers required')
    for handler_key, audience_key in (
        ('SYNC_TASKS_HANDLER_URL', 'SYNC_TASKS_OIDC_AUDIENCE'),
        ('SYNC_BACKFILL_TASKS_HANDLER_URL', 'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE'),
    ):
        if env.get(handler_key) != env.get(audience_key):
            raise ProbeRefused('task audience must match its staging handler')
    for key in ('SYNC_TASKS_LOCATION', 'REDIS_DB_HOST', 'REDIS_DB_PORT', 'BUCKET_TEMPORAL_SYNC_LOCAL'):
        if not env.get(key):
            raise ProbeRefused('explicit staging data and queue bindings required')
    for key in ('SYNC_TASKS_QUEUE', 'SYNC_BACKFILL_TASKS_QUEUE'):
        if not env.get(key, '').startswith('staging-'):
            raise ProbeRefused('explicit staging queues required')
    if not env.get('SYNC_TASKS_INVOKER_SA', '').endswith('@based-hardware-dev.iam.gserviceaccount.com'):
        raise ProbeRefused('staging task invoker required')


def private_token(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ProbeRefused('token file must be owner-only')
    token = path.read_text().strip()
    if not token or len(token) > 16384:
        raise ProbeRefused('invalid token file')
    return token


def wait_until(check, seconds: float, *, deadline: float):
    bound = min(deadline, time.monotonic() + seconds)
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() >= bound:
            raise ProbeRefused('probe deadline expired')
        time.sleep(min(2, max(0, bound - time.monotonic())))


def seed():
    from database import sync_backfill_sequencer as registry, sync_jobs
    from utils.cloud_tasks import SYNC_JOB_TASK_PAYLOAD_KEYS

    # Fresh synthetic account per case; never inspect or reuse a real account.
    uid, job_id = 'syncsplit-synthetic-' + uuid.uuid4().hex, 'syncsplit-' + uuid.uuid4().hex
    sync_jobs.create_sync_job(uid, 1, 0, job_id, lane='backfill', dispatch_mode='sequenced', ledger_fence_mode='active')
    payload = {key: None for key in SYNC_JOB_TASK_PAYLOAD_KEYS}
    payload.update(
        schema_version=1,
        uid=uid,
        job_id=job_id,
        lane='backfill',
        ledger_fence_mode='active',
        source='omi',
        should_lock=False,
        enqueued_at=time.time(),
        # Deliberately absent source: fallback must dispose it before
        # decode/provider work. No speech or audio custody is created.
        raw_blob_paths=[f'syncing/{uid}/{job_id}/missing-synthetic.bin'],
    )
    registry.register_job(uid, job_id, payload, None)
    claim = registry.claim_next(uid)
    if not claim or claim['payload'].get('worker_eligible') is not True:
        raise ProbeRefused('fixture was not worker eligible')
    return claim


def enqueue_fixture(claim: dict) -> None:
    from utils.cloud_tasks import enqueue_sync_job

    enqueue_sync_job(
        {**claim['payload'], 'sequencer_epoch': claim['epoch']},
        dispatch_attempt=claim.get('dispatch_attempt', 0),
        schedule_at=claim.get('worker_fallback_at'),
    )


class Probe:
    def __init__(self, target: str, token_file: Path):
        import httpx

        self.http = httpx.Client(timeout=20, follow_redirects=False)
        self.target, self.token_file = target, token_file
        self.deadline = time.monotonic() + 3000
        self.passed: list[str] = []

    def rpc(self, operation: str, body: dict | None = None) -> dict:
        response = self.http.post(
            f'{self.target}/v2/sync-jobs/{operation}',
            headers={'Authorization': 'Bearer ' + private_token(self.token_file)},
            json={'stage': 'prod', **(body or {})},
        )
        response.raise_for_status()
        return response.json()

    def claim(self, fixture: dict) -> dict:
        # The route's candidate cursor wraps on an empty page, so one poll can miss a head
        # whose random uid sorts before the cursor. Real workers poll; so does this.
        lease = wait_until(lambda: self.rpc('claim').get('lease'), 20, deadline=self.deadline)
        if lease['payload']['job_id'] != fixture['job_id']:
            raise ProbeRefused('claim mismatch; staging window must exclude other pullers and fixtures')
        return {'uid': fixture['uid'], 'job_id': fixture['job_id'], 'epoch': fixture['epoch'], 'token': lease['token']}

    def terminal_fixture(self, fixture: dict, status: str) -> None:
        from database import sync_jobs

        token = sync_jobs.try_acquire_sync_job_run_lock(fixture['job_id'])
        if not token:
            raise ProbeRefused('synthetic terminal fixture is run-locked')
        try:
            mutation = sync_jobs.fenced_update_sync_job(
                fixture['job_id'], token, {'status': status}, allowed_current_statuses={'queued', 'processing'}
            )
            if not mutation.applied:
                raise ProbeRefused('synthetic terminal fence refused')
        finally:
            sync_jobs.release_job_run_lock(fixture['job_id'], token)

    def rpc_cases(self) -> None:
        from database import sync_backfill_sequencer as registry

        fixture = seed()
        identity = self.claim(fixture)
        if not self.rpc('heartbeat', identity).get('accepted'):
            raise ProbeRefused('heartbeat refused')
        self.passed.extend(['claim', 'heartbeat'])
        if self.rpc('claim').get('lease') is not None:
            raise ProbeRefused('duplicate claim accepted')
        if registry.begin_job(fixture['uid'], fixture['job_id'], fixture['epoch']) is not None:
            raise ProbeRefused('fallback began while worker owned the epoch')
        self.passed.append('duplicate-claim')
        if self.rpc('complete', identity).get('accepted'):
            raise ProbeRefused('nonterminal completion accepted')
        self.terminal_fixture(fixture, 'completed')
        if not self.rpc('complete', identity).get('accepted') or self.rpc('heartbeat', identity).get('accepted'):
            raise ProbeRefused('terminal completion fence failed')
        self.passed.append('complete')
        fixture = seed()
        identity = self.claim(fixture)
        if not self.rpc('fail', identity).get('accepted') or self.rpc('heartbeat', identity).get('accepted'):
            raise ProbeRefused('failure handoff fence failed')
        self.terminal_fixture(fixture, 'failed')
        registry.finish_job(fixture['uid'], fixture['job_id'], fixture['epoch'] + 1, 'synthetic_probe')
        self.passed.append('fail')

    def terminal_fallback(self, fixture: dict):
        from database import sync_jobs

        job = sync_jobs.get_sync_job(fixture['job_id'])
        if job and job.get('status') in sync_jobs.TERMINAL_STATUSES:
            if job.get('status') != 'failed' or job.get('reason_code') != 'sync_staged_audio_expired':
                raise ProbeRefused('fallback did not produce the expected synthetic missing-source disposition')
            return True
        return False

    def no_worker_case(self) -> None:
        fixture = seed()
        enqueue_fixture(fixture)
        wait_until(lambda: self.terminal_fallback(fixture), 720, deadline=self.deadline)
        self.passed.append('no-worker-cloud-tasks-fallback')

    def death_case(self) -> None:
        from database import sync_backfill_sequencer as registry, sync_jobs

        fixture = seed()
        identity = self.claim(fixture)
        with tempfile.TemporaryDirectory(prefix='syncsplit-death-') as temp:
            ready = Path(temp) / 'ready'
            process = subprocess.Popen(
                [
                    sys.executable,
                    '-m',
                    'scripts.staging.syncsplit',
                    '_lease-child',
                    '--target',
                    self.target,
                    '--job-id',
                    fixture['job_id'],
                    '--ready',
                    str(ready),
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:

                def child_ready():
                    if process.poll() is not None:
                        raise ProbeRefused('lease child failed before acquiring Redis')
                    return ready.exists()

                wait_until(child_ready, 20, deadline=self.deadline)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
        competing = sync_jobs.try_acquire_sync_job_run_lock(fixture['job_id'])
        if competing:
            sync_jobs.release_job_run_lock(fixture['job_id'], competing)
        if self.rpc('fail', identity).get('accepted') or competing:
            raise ProbeRefused('worker death released the Redis silence fence early')
        enqueue_fixture(fixture)
        # Wait the REAL 1800s silence window. Never shorten either lease to
        # make the probe faster. Then exercise the existing redrive primitive.
        wait_until(
            lambda: not sync_jobs.sync_job_run_lock_present(fixture['job_id']),
            registry.LEASE_SECONDS + 120,
            deadline=self.deadline,
        )
        replacement = registry.redrive_job(fixture['uid'], fixture['job_id'], fixture['epoch'])
        if replacement:
            enqueue_fixture(replacement)
        wait_until(lambda: self.terminal_fallback(fixture), 360, deadline=self.deadline)
        if self.rpc('heartbeat', identity).get('accepted'):
            raise ProbeRefused('dead worker revived after fallback')
        self.passed.append('worker-death-unchanged-ttl-fallback')

    def fleet_case(self) -> dict:
        from database import sync_backfill_sequencer as registry, sync_jobs

        if any(registry.worker_candidates()):
            raise ProbeRefused('staging window has pre-existing worker-eligible heads')
        fixture = seed()
        enqueue_fixture(fixture)
        wait_until(lambda: self.terminal_fallback(fixture), 720, deadline=self.deadline)
        job = sync_jobs.get_sync_job(fixture['job_id'])
        if not job or job.get('execution_drive') != 'pull':
            raise ProbeRefused('installed worker did not reach fenced job execution')
        return {
            'result': 'PASS',
            'layer': 'staging-installed-worker-synthetic-no-audio',
            'passed': ['installed-worker-execution-and-fallback'],
            'fleet_execution': 'PASS',
            'speech_parity': 'NOT_RUN',
            'cost': 'NOT_MEASURED',
        }

    def run(self) -> dict:
        from database import sync_backfill_sequencer as registry

        try:
            if any(registry.worker_candidates()):
                raise ProbeRefused('staging window has pre-existing worker-eligible heads')
            self.rpc_cases()
            self.no_worker_case()
            self.death_case()
            return {
                'result': 'PASS',
                'layer': 'staging-control-plane-synthetic-no-audio',
                'passed': self.passed,
                'lease_seconds': registry.LEASE_SECONDS,
                'speech_parity': 'NOT_RUN',
                'cost': 'NOT_MEASURED',
                'fleet_execution': 'NOT_RUN',
            }
        finally:
            self.http.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'run', 'fleet', '_lease-child'])
    parser.add_argument('--target', default='')
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--job-id', default='')
    parser.add_argument('--ready', type=Path)
    args = parser.parse_args()
    if args.mode == 'plan':
        print(
            json.dumps(
                {
                    'cases': [
                        'claim',
                        'heartbeat',
                        'complete',
                        'fail',
                        'duplicate-claim',
                        'worker-death-unchanged-ttl-fallback',
                        'no-worker-cloud-tasks-fallback',
                    ],
                    'max_seconds': 3000,
                    'writes': 'isolated staging synthetic job fixtures only',
                    'speech_parity': 'NOT_RUN',
                    'cost': 'NOT_MEASURED',
                    'fleet_execution': 'NOT_RUN',
                }
            )
        )
        return 0
    # Dependencies sometimes log document paths. This CLI emits only its own
    # aggregate receipt; serving-side staging logs retain their normal policy.
    logging.disable(logging.CRITICAL)
    probe = None
    try:
        validate_configuration(dict(os.environ), args.target)
        if args.mode == '_lease-child':
            if not args.job_id.startswith('syncsplit-') or args.ready is None:
                raise ProbeRefused('synthetic lease child identity required')
            from database import sync_jobs

            if not sync_jobs.try_acquire_sync_job_run_lock(args.job_id):
                raise ProbeRefused('lease child could not acquire Redis')
            args.ready.write_text('ready')
            signal.alarm(30)
            while True:
                signal.pause()
        if args.token_file is None:
            raise ProbeRefused('private OIDC token file required')
        private_token(args.token_file)
        probe = Probe(args.target, args.token_file)
        if args.mode == 'fleet':
            try:
                receipt = probe.fleet_case()
            finally:
                probe.http.close()
        else:
            receipt = probe.run()
        print(json.dumps(receipt))
        return 0
    except ProbeRefused as error:
        print(
            json.dumps(
                {
                    'result': 'FAIL',
                    'reason': str(error),
                    'exception_type': 'ProbeRefused',
                    'passed': probe.passed if probe else [],
                    'speech_parity': 'NOT_RUN',
                    'cost': 'NOT_MEASURED',
                    'fleet_execution': 'NOT_RUN',
                }
            )
        )
        return 1
    except Exception as error:
        print(
            json.dumps(
                {
                    'result': 'FAIL',
                    'exception_type': type(error).__name__,
                    'speech_parity': 'NOT_RUN',
                    'cost': 'NOT_MEASURED',
                    'fleet_execution': 'NOT_RUN',
                }
            )
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
