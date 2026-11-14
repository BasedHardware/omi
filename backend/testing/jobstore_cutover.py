"""Local-only dark source qualification; every unproved scenario fails closed.

`all` is deliberately NOT a readiness certificate while missing integration is
listed in its receipt. `corrected-w4` exercises the accepted typed units query,
not the historical document mirror. Neither command provisions or uses staging.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

MISSING = [
    'all-writer runtime FS mutation binding and native/partial/coalesced/recovery cross-store cohort integration',
    'production runner/funding/failover qualification and outbox/vector/push FenceTicket wiring/H-25',
    'real C4 GCS terminal-session adapter (local registry custody test is not a sink proof)',
    'complete original lifetime/journal/cold-copy purge and per-record final custody retirement (generation-pinned objects/original FS source, staging census and destructive PG artifact-mirror barriers are partial; unique intake/staging and real C4/late-copy proof remain)',
    'complete reverse cohorts/cold-to-serving conversion, final parity certificate and certified reverse-open edge (ordinary typed conditional cold sink/erasure is partial)',
    'process-kill/restart coverage at every cross-store commit gap, not exception-only rollback',
    'every G2 section 5.2 row/lettered subrow and complete P21-P25 qualification',
    'default-off runtime factory integration, metrics, residue runner and production scheduling of drain/janitor/restore adapters',
]


def local_only():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('loopback Firestore emulator required; no cloud fallback')
    if os.environ.get('OMI_TEST_POSTGRES_IAM') or os.environ.get('OMI_TEST_POSTGRES_ALLOW_REMOTE') == '1':
        raise RuntimeError('remote PostgreSQL forbidden in this local harness')
    dsn = os.environ.get('OMI_TEST_POSTGRES_DSN', '')
    if dsn:
        from psycopg.conninfo import conninfo_to_dict

        host = conninfo_to_dict(dsn).get('host', '')
        if host not in {'127.0.0.1', 'localhost', '::1'} and not host.startswith('/'):
            raise RuntimeError('explicit local PostgreSQL DSN required')


def corrected_w4(args):
    import testing.pipeline_sim._env  # noqa: F401 -- hermetic import constants, not a CustomerData simulator
    from database.jobstore.connection import Pool
    from database.jobstore.authority import transition
    from database.jobstore.units import Units
    from database.privacy_fence import Fence, owner_key
    from testing.store_fixtures import postgres_connect, _emulator_client, ClientCustomerData

    pool = Pool('', size=args.pool, connect=postgres_connect())
    client = _emulator_client()
    customer = ClientCustomerData(client)
    fence = Fence(pool)
    ns = 'batch_pipeline_test_' + uuid4().hex
    rng = random.Random(args.seed)
    with pool.connection() as conn, conn.transaction():
        conn.execute('INSERT INTO queue_authority(namespace) VALUES (%s)', (ns,))
        transition(conn, ns, 'FS_OPEN', 0, 'FS_CLOSING')
        transition(conn, ns, 'FS_CLOSING', 1, 'BOTH_CLOSED')
        ticket = transition(conn, ns, 'BOTH_CLOSED', 2, 'PG_OPEN')
    store = Units(pool, fence, ticket)
    began = time.monotonic()
    try:
        for index in range(args.owners):
            uid = f'w4-{ns}-{index}'
            customer.add_user(uid)
            customer.add_conversation(uid, 'recording')
            owner = owner_key(uid)

            # Policy inputs are synthetic and explicit: alternation fixes class,
            # owner_turn is the round + a stable per-owner rotation. This is a
            # bounded index/locking workload, not a final admission policy.
            def persist(conn, admission):
                for job in range(args.jobs):
                    store.admit(
                        conn,
                        f'{index}-{job}',
                        owner,
                        str(index),
                        admission,
                        capture_at=100 + job,
                        units_total=args.jobs,
                        custody_deadline=10000,
                        fresh=job % 2 == 0,
                        owner_turn=job * args.owners + index,
                        now=100,
                    )

            fence.admit_from_authority(client, uid, ['recording'], persist)
        generated = args.owners * args.jobs
        settled = 0
        pulls = []
        while settled < generated and time.monotonic() - began < args.seconds:
            started = time.monotonic()
            claimed = store.claim(20, now=200, lease_seconds=120, backlog_share=10)
            pulls.append(time.monotonic() - started)
            if not claimed:
                break
            rng.shuffle(claimed)
            for unit in claimed:
                settled += int(
                    store.settle(unit['unit_id'], unit['attempt_token'], 'result_ready', None, now=201, partial_wait=60)
                )
        with pool.connection() as conn:
            wrong = conn.execute(
                'SELECT count(*) FROM recordings WHERE namespace=%s AND units_final<>units_total', (ns,)
            ).fetchone()[0]
            armed = conn.execute('SELECT count(*) FROM outbox WHERE namespace=%s', (ns,)).fetchone()[0]
        return {
            'schema': 'D4/W4 corrected units/recordings/budgets; class smallint 0/1',
            'workload_basis': 'SCA-1890 corrected 01a1d4e4; bounded typed provider query, no staging-sizing certification',
            'owners': args.owners,
            'jobs_per_owner': args.jobs,
            'generated': generated,
            'settled': settled,
            'recording_counter_mismatches': wrong,
            'armed_projection_rows': armed,
            'pull_p95_ms': sorted(pulls)[min(len(pulls) - 1, int(len(pulls) * 0.95))] * 1000 if pulls else None,
            'elapsed_seconds': time.monotonic() - began,
            'passed': settled == generated and wrong == 0 and armed == args.owners,
            'missing': [
                'fleet concurrency/budget reservation chunks and final owner_turn/class admission policy',
                *MISSING,
            ],
        }
    finally:
        pool.close()
        client.close()


def races(args):
    xml_path = Path(args.receipt).with_suffix('.junit.xml')
    command = [
        sys.executable,
        '-m',
        'pytest',
        '-m',
        'integration',
        '-ra',
        '-q',
        'tests/integration/test_privacy_fence_postgres.py',
        'tests/integration/test_privacy_lifecycle_postgres.py',
        'tests/integration/test_jobstore_authority_postgres.py',
        'tests/integration/test_jobstore_sql_boundary.py',
        'tests/integration/test_jobstore_handoff.py',
        'tests/integration/test_jobstore_provider_handoff.py',
        'tests/integration/test_jobstore_provider_projection.py',
        'tests/integration/test_jobstore_provider_effect.py',
        'tests/integration/test_jobstore_retained_copies.py',
        'tests/integration/test_jobstore_original_copies.py',
        'tests/integration/test_jobstore_original_metadata_crashes.py',
        'tests/integration/test_jobstore_cold_sink.py',
        'tests/integration/test_jobstore_cold_crashes.py',
        'tests/integration/test_jobstore_staging_copies.py',
        'tests/integration/test_pipeline_ledger_firestore.py',
        'tests/integration/test_conversation_batch_purge_emulator.py::test_p24_real_purge_erases_ledger_and_stale_observers_stay_fenced',
        '--junitxml',
        str(xml_path),
    ]
    result = subprocess.run(command, env={**os.environ, 'OMI_REQUIRE_STORE_BACKENDS': 'all'}, check=False)
    suites = ET.parse(xml_path).getroot().findall('testsuite') if xml_path.exists() else []
    counts = {key: sum(int(s.get(key, '0')) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    return {
        'command': command,
        'suite_returncode': result.returncode,
        'counts': counts,
        'passed': False,
        'primitive_suite_passed': result.returncode == 0 and counts['skipped'] == 0,
        'missing': MISSING,
        'certificate': None,
        'note': 'Fail closed: primitive tests do not qualify complete cutover/reverse/erasure.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['all', 'corrected-w4'], default='all')
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--owners', type=int, default=20)
    parser.add_argument('--jobs', type=int, default=10)
    parser.add_argument('--pool', type=int, default=2)
    parser.add_argument('--seconds', type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.owners <= 200 or not 1 <= args.jobs <= 10 or not 1 <= args.seconds <= 120:
        parser.error('local workload bound: owners 1..200, jobs 1..10, seconds 1..120')
    source_root = Path(__file__).resolve().parents[2]
    changes = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=normal', '--', 'backend', '.github', 'scripts'],
        cwd=source_root,
        text=True,
    ).splitlines()
    receipt = {
        'scenario': args.scenario,
        'seed': args.seed,
        'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'source_dirty': bool(changes),
        'source_changes': changes,
    }
    try:
        local_only()
        receipt.update(corrected_w4(args) if args.scenario == 'corrected-w4' else races(args))
    except Exception as error:
        receipt.update(passed=False, error=type(error).__name__, detail=str(error), missing=MISSING)
    Path(args.receipt).write_text(json.dumps(receipt, indent=2) + '\n')
    return 0 if receipt.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
