#!/usr/bin/env python3
"""Capture and recreate the legacy sync Cloud Tasks queues (contract (h) rollback).

Deleting the legacy queues is the last reversible step after the deletion PRs
(h, "Reversibility window"). This script is the way back:

    capture   read each queue's live config into a spec file (before deletion)
    recreate  create missing queues / update existing ones from a spec file
    verify    compare live configs with a spec file

Only rate limits, retry config and logging sampling are captured: no tasks,
no task names, no payloads. ``recreate`` is a dry run unless ``--apply``.

Tiers: ``capture``/``verify`` need ``cloudtasks.queues.get`` (``ro-prod`` lacks
it; use ``prod-operator`` read-only, or ``dev-operator`` for staging).
``recreate --apply`` needs queue create/update: ``dev-operator`` on staging; in
prod it is the lead's action under David's authorization.

Rehearsal (M2, staging): capture -> delete (lead) -> recreate --apply -> verify.

After recreating queues, the legacy services and scheduler job come back by
redeploying the previous image (the train that preceded the deletion PR) and
``scripts/scheduler_reconcile.py --apply --jobs sync-backfill-uid-sequencer``
from that image's ``deploy/scheduler/jobs.yaml``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Optional

QUEUES = ('sync-jobs', 'sync-jobs-fresh', 'sync-backfill', 'sync-backfill-fresh')
ENVIRONMENTS = {'prod': ('based-hardware', 'us-central1'), 'staging': ('based-hardware-dev', 'us-central1')}
SPEC_VERSION = 1


def _gcloud(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['gcloud', *args], capture_output=True, text=True, timeout=120, check=check)


def _queue_name(env: str, queue: str) -> str:
    """Staging queues carry a ``staging-`` prefix (contract (i)); prod names are unchanged."""
    return queue if env == 'prod' else f'staging-{queue}'


def describe(env: str, queue: str) -> Optional[dict[str, Any]]:
    project, location = ENVIRONMENTS[env]
    result = _gcloud(
        ['tasks', 'queues', 'describe', _queue_name(env, queue), f'--project={project}', f'--location={location}']
        + ['--format=json'],
        check=False,
    )
    if result.returncode != 0:
        if 'NOT_FOUND' in result.stderr:
            return None
        raise RuntimeError(f'describe {queue}: {result.stderr.strip().splitlines()[-1] if result.stderr else "failed"}')
    return json.loads(result.stdout)


def spec_from_live(live: dict[str, Any]) -> dict[str, Any]:
    rate = live.get('rateLimits') or {}
    retry = live.get('retryConfig') or {}
    logging_config = live.get('stackdriverLoggingConfig') or {}
    return {
        'max_concurrent_dispatches': rate.get('maxConcurrentDispatches'),
        'max_dispatches_per_second': rate.get('maxDispatchesPerSecond'),
        'max_attempts': retry.get('maxAttempts'),
        'max_retry_duration': retry.get('maxRetryDuration'),
        'min_backoff': retry.get('minBackoff'),
        'max_backoff': retry.get('maxBackoff'),
        'max_doublings': retry.get('maxDoublings'),
        'log_sampling_ratio': logging_config.get('samplingRatio'),
        'state': live.get('state'),
    }


def flags_from_spec(spec: dict[str, Any]) -> list[str]:
    mapping = (
        ('max_concurrent_dispatches', '--max-concurrent-dispatches'),
        ('max_dispatches_per_second', '--max-dispatches-per-second'),
        ('max_attempts', '--max-attempts'),
        ('max_retry_duration', '--max-retry-duration'),
        ('min_backoff', '--min-backoff'),
        ('max_backoff', '--max-backoff'),
        ('max_doublings', '--max-doublings'),
        ('log_sampling_ratio', '--log-sampling-ratio'),
    )
    flags = []
    for key, flag in mapping:
        value = spec.get(key)
        if value is not None:
            flags.append(f'{flag}={value}')
    return flags


def capture(env: str, path: str) -> int:
    specs: dict[str, Any] = {}
    for queue in QUEUES:
        live = describe(env, queue)
        specs[queue] = None if live is None else spec_from_live(live)
    document = {'spec_version': SPEC_VERSION, 'env': env, 'queues': specs}
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(
        json.dumps(
            {
                'captured': sorted(q for q, s in specs.items() if s),
                'absent': sorted(q for q, s in specs.items() if not s),
            }
        )
    )
    return 0


def _load(path: str, env: str) -> dict[str, Any]:
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
    if document.get('spec_version') != SPEC_VERSION or document.get('env') != env:
        raise SystemExit(f'spec {path} is not a v{SPEC_VERSION} spec for env={env}')
    return document['queues']


def recreate(env: str, path: str, apply: bool) -> int:
    project, location = ENVIRONMENTS[env]
    planned = []
    for queue, spec in _load(path, env).items():
        if queue not in QUEUES or not spec:
            continue
        operation = 'update' if describe(env, queue) is not None else 'create'
        command = ['tasks', 'queues', operation, _queue_name(env, queue), f'--project={project}']
        command += [f'--location={location}', *flags_from_spec(spec)]
        planned.append(command)
        print(('APPLY ' if apply else 'DRY-RUN ') + 'gcloud ' + ' '.join(command))
        # ``queues update`` never changes state: restore it explicitly, both
        # ways, so a rollback onto a paused queue resumes it (M1 review L10-5).
        state_verb = {'PAUSED': 'pause', 'RUNNING': 'resume'}.get(spec.get('state'))
        state_command = (
            ['tasks', 'queues', state_verb, _queue_name(env, queue), f'--project={project}', f'--location={location}']
            if state_verb
            else None
        )
        if state_command:
            planned.append(state_command)
            print(('APPLY ' if apply else 'DRY-RUN ') + 'gcloud ' + ' '.join(state_command))
        if apply:
            _gcloud(command)
            if state_command:
                _gcloud(state_command)
    return 0 if planned else 1


def verify(env: str, path: str) -> int:
    drift = {}
    for queue, spec in _load(path, env).items():
        if not spec:
            continue
        live = describe(env, queue)
        actual = None if live is None else spec_from_live(live)
        if actual != spec:
            drift[queue] = {'expected': spec, 'actual': actual}
    print(json.dumps({'verdict': 'MATCH' if not drift else 'DRIFT', 'drift': drift}, sort_keys=True))
    return 0 if not drift else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('capture', 'recreate', 'verify'))
    parser.add_argument('--env', choices=sorted(ENVIRONMENTS), required=True)
    parser.add_argument('--spec', required=True, help='spec JSON path (written by capture)')
    parser.add_argument('--apply', action='store_true', help='recreate only: run the gcloud commands')
    args = parser.parse_args(argv)
    if not os.environ.get('GCP_AGENT_TIER'):
        print('source ~/.local/bin/gcp-agent-env.sh <tier> first', file=sys.stderr)
        return 2
    if args.command == 'capture':
        return capture(args.env, args.spec)
    if args.command == 'recreate':
        return recreate(args.env, args.spec, args.apply)
    return verify(args.env, args.spec)


if __name__ == '__main__':
    sys.exit(main())
