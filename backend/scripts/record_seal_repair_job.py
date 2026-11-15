#!/usr/bin/env python3
"""Counts-only entrypoint for the isolated repair CronJob and its row children."""

import time

PROCESS_STARTED = time.monotonic()

import socket
import json
import traceback
import re
import logging
import os
from pathlib import Path
import signal
import sys
from contextlib import nullcontext

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omi_logging import configure_logging

configure_logging('record-seal-repair', default_format='json')

from utils.batch_pipeline import record_seal_cluster_repair as repair
from utils.observability.firestore_probe_export import (
    CHILD_FD_ENV,
    terminal_probe_totals,
    repair_probe_server,
    record_repair_run_outcome,
)


def emit(payload):
    logger = logging.getLogger('record-seal-repair')
    level = (
        logging.ERROR
        if payload.get('outcome') == 'error'
        else (
            logging.WARNING
            if payload.get('outcome') == 'capacity_exceeded'
            or payload.get('event') in {'record_seal_repair_row', 'record_seal_repair'}
            else logging.INFO
        )
    )
    record = logger.makeRecord(
        logger.name, level, '', 0, json.dumps(payload, sort_keys=True, allow_nan=False), (), None
    )
    logger.handle(record)


_SAFE_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}')
_SAFE_FILE = re.compile(r'[a-z0-9_]{1,64}\.py')
_KNOWN_MODULES = (
    'builtins',
    'asyncio',
    'concurrent',
    'json',
    'ssl',
    'socket',
    'subprocess',
    'google',
    'grpc',
    'firebase_admin',
    'requests',
    'urllib3',
    'httpx',
    'redis',
    'utils',
    'database',
    'config',
    'models',
    'routers',
    'scripts',
)
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _exception_type(error):
    cls = type(error)
    module = (getattr(cls, '__module__', '') or '').split('.', 1)[0]
    name = getattr(cls, '__name__', '')
    return name if module in _KNOWN_MODULES and _SAFE_NAME.fullmatch(name or '') else 'other'


def _error_site(error):
    """Innermost first-party frame as file.py:line, only for a real file inside the backend tree."""
    try:
        frames = traceback.extract_tb(error.__traceback__)
    except Exception:
        return ''
    for frame in reversed(frames):
        path = os.path.realpath(frame.filename or '')
        if not path.startswith(_BACKEND_ROOT + os.sep) or 'site-packages' in path or not os.path.isfile(path):
            continue
        base = os.path.basename(path)
        if _SAFE_FILE.fullmatch(base) and isinstance(frame.lineno, int):
            return f'{base}:{frame.lineno}'
    return ''


def failure(event, error):
    """Error payload: a known exception class and a first-party file:line, never the message (may hold user ids)."""
    payload = {'event': event, 'outcome': 'error'}
    try:
        payload['exception_type'] = _exception_type(error)
        site = _error_site(error)
        if site:
            payload['error_site'] = site
    except Exception:
        pass
    return payload


def partition_arguments(argv):
    """Cron arguments only; no serving runtime env or policy flag is introduced."""
    if not argv:
        return 0, 1
    if len(argv) != 4 or argv[0] != '--shards' or argv[2] != '--shard-index-file':
        raise ValueError('invalid arguments')
    count = int(argv[1])
    index = int(Path(argv[3]).read_text().strip())
    repair.validate_partition(index, count)
    return index, count


def process_deadline(started, hostname, wall_now, monotonic_now):
    """Bound imports, cold scheduling/image pull, all phases and cleanup.

    The standard Job name contains its scheduled Unix minute. Indexed pods use
    the stable hostname <job>-<index>; ordinary pods use <job>-<random>. Also
    accept an Indexed pod's metadata name, <job>-<index>-<random>. This clock is
    earlier than Job creation, so it conservatively includes scale-up waits.
    """
    deadline = started + 1560  # At least 120s before the hard Job ceiling.
    match = re.fullmatch(r'record-seal-repair-(\d{8,})-(?:\d+|(?:\d+-)?[a-z0-9]{5})', hostname)
    if match:
        scheduled = int(match.group(1)) * 60
        if scheduled > wall_now + 60:
            raise ValueError('invalid scheduled repair clock')
        deadline = min(deadline, monotonic_now + scheduled + 1680 - 60 - wall_now)
    elif os.environ.get('KUBERNETES_SERVICE_HOST'):
        raise ValueError('unrecognized scheduled repair identity')
    return deadline


PROJECTION_PREPASS_SHARD = 0


def run_summary(report, *, shard, shards, phase='overall', exit_code=0):
    """One terminal outcome per coordinator, also durable when the final scrape is missed.

    Phase is the primary unfinished phase, not a promise that every sampled row
    was sealable. Refused proofs remain refused and are never counted as seals.
    """
    prepass = report.get('projection_prepass', {}).get('outcome')
    if report.get('outcome') == 'overlap_refused':
        phase = 'setup'
    elif report.get('cursor_checkpoint_outcome') == 'budget_exhausted':
        phase = 'checkpoint'
    elif any(report.get('dispositions', {}).get(reason, 0) for reason in ('budget_exhausted', 'deferred')):
        phase = 'rows'
    elif report.get('work_incomplete') or exit_code or report.get('outcome') == 'overlap_refused':
        pass
    elif prepass in {'budget_exhausted', 'not_started', 'error'}:
        phase = 'prepass'
    else:
        phase = 'overall'
    incomplete = (
        phase != 'overall'
        or exit_code != 0
        or report.get('work_incomplete', False)
        or report.get('outcome') in {'budget_exhausted', 'overlap_refused'}
    )
    report.update(
        repair_run_summary=1,
        run_outcome='incomplete' if incomplete else 'complete',
        run_phase=phase,
        shard=shard,
        shards=shards,
        exit_code=exit_code,
    )
    if incomplete:
        report['work_incomplete'] = True
    record_repair_run_outcome(report['run_outcome'], phase)
    emit(report)


def main():
    def terminate(*_):
        # Unwind the coordinator's finally block and reap all children.
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, terminate)
    # Keep only our aggregate handler/IPC on an explicit output fd. Suppress
    # native diagnostics for the whole lifetime, including SDK background threads.
    with os.fdopen(os.dup(1), 'w') as output:
        configure_logging('record-seal-repair', default_format='json', stdout=output, stderr=output)
        # Flush while the explicit aggregate logging fd is still open.
        with terminal_probe_totals(
            'record-seal-repair', fd=os.environ.get(CHILD_FD_ENV), log_empty=False
        ), repair.silent_dependencies(), (
            repair_probe_server() if sys.argv[1:] != ['--row'] and repair.config.enabled() else nullcontext()
        ):
            projection_report = {}
            phase = 'setup'
            shard, shards = None, None

            def set_phase(value):
                nonlocal phase
                phase = value

            try:
                if sys.argv[1:] == ['--row']:
                    payload = json.loads(sys.stdin.buffer.read(8193))

                    def checkpoint(value):
                        output.write(json.dumps(value, separators=(',', ':')) + '\n')
                        output.flush()

                    checkpoint(repair.row_main(payload, progress=checkpoint))
                else:
                    shard, shards = partition_arguments(sys.argv[1:])
                    deadline = process_deadline(PROCESS_STARTED, socket.gethostname(), time.time(), time.monotonic())

                    from utils.batch_pipeline.record_seal_budget import BudgetExhausted, SweepBudget

                    outer_budget = SweepBudget(max(0, deadline - time.monotonic()))

                    def projection():
                        nonlocal phase
                        if shard != PROJECTION_PREPASS_SHARD:
                            return
                        phase = 'prepass'
                        try:
                            from utils import record_projection_rebuild

                            remaining = deadline - time.monotonic() - 30
                            outer_budget.check()
                            if remaining <= 0:
                                projection_report.update(event='record_projection_rebuild', outcome='not_started')
                            else:
                                # One local timer: run_job retains completed counts on cancellation.
                                projection_report.update(record_projection_rebuild.run_job(seconds=min(60, remaining)))
                        except BudgetExhausted:
                            projection_report.update(event='record_projection_rebuild', outcome='budget_exhausted')
                        except Exception as error:
                            projection_report.update(failure('record_projection_rebuild', error))
                        # An expired process budget is never mistaken for local truncation.
                        outer_budget.check()
                        if projection_report.get('outcome') != 'disabled':
                            emit(projection_report)
                        phase = 'discovery'

                    with outer_budget.interrupt_io():
                        report = repair.run(
                            progress=emit,
                            deadline=deadline,
                            before=projection,
                            phase_progress=set_phase,
                            **({'shard': shard, 'shards': shards} if shards > 1 else {}),
                        )
                        if projection_report and projection_report.get('outcome') != 'disabled':
                            report['projection_prepass'] = projection_report
                            report['projection_prepass_budget_exhausted'] = int(
                                projection_report.get('outcome') == 'budget_exhausted'
                            )
                    run_summary(report, shard=shard, shards=shards)

            except repair.BudgetExhausted:
                # Cancellation is incomplete work, not a shard failure or a successful seal.
                report = {
                    'event': 'record_seal_repair',
                    'outcome': 'budget_exhausted',
                    'work_incomplete': True,
                    'phase': phase,
                }
                if projection_report and projection_report.get('outcome') != 'disabled':
                    report['projection_prepass'] = projection_report
                    report['projection_prepass_budget_exhausted'] = int(
                        projection_report.get('outcome') == 'budget_exhausted'
                    )
                if sys.argv[1:] == ['--row']:
                    emit(report)
                else:
                    run_summary(report, shard=shard, shards=shards, phase=phase)
                return 0

            except BaseException as error:
                report = failure('record_seal_repair', error)
                if sys.argv[1:] == ['--row']:
                    emit(report)
                else:
                    run_summary(report, shard=shard, shards=shards, phase=phase, exit_code=1)
                return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
