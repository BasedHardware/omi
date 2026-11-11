#!/usr/bin/env python3
"""Counts-only entrypoint for the isolated repair CronJob and its row children."""

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
from utils.observability.firestore_probe_export import CHILD_FD_ENV, terminal_probe_totals, repair_probe_server


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
            repair_probe_server() if not sys.argv[1:] and repair.config.enabled() else nullcontext()
        ):
            try:
                if sys.argv[1:] == ['--row']:
                    payload = json.loads(sys.stdin.buffer.read(8193))

                    def checkpoint(value):
                        output.write(json.dumps(value, separators=(',', ':')) + '\n')
                        output.flush()

                    checkpoint(repair.row_main(payload, progress=checkpoint))
                elif not sys.argv[1:]:
                    try:
                        from utils import record_projection_rebuild

                        report = record_projection_rebuild.run_job()
                        if report['outcome'] != 'disabled':
                            emit(report)
                    except Exception as error:
                        emit(failure('record_projection_rebuild', error))
                    emit(repair.run(progress=emit))
                else:
                    raise ValueError('invalid arguments')
            except BaseException as error:
                emit(failure('record_seal_repair', error))
                return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
