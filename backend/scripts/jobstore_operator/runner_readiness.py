# LIFECYCLE: permanent
"""Fixed metadata-only probe with bounded, stage-specific failure receipts."""

import hashlib
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import google.auth
from google.auth.compute_engine.credentials import Credentials
import psycopg

SOURCE = '97074e78defa1a84b9d39c021e28aa70cf4f2e4e'
TARGET = ('jobstore_prod', 'batch-pipeline-worker@based-hardware.iam', '172.25.29.2')
INDEXES = ['jobs_due_leased_c', 'jobs_due_result_c', 'jobs_due_retry_c']
READINESS_SECONDS = 50
HEAD_SECONDS = 5
STATUS_SECONDS = 30
FAILURE_CLASSES = frozenset(
    {
        'TimeoutExpired',
        'TimeoutError',
        'CalledProcessError',
        'ValueError',
        'RuntimeError',
        'OSError',
        'FileNotFoundError',
        'PermissionError',
        'ConnectionError',
        'DefaultCredentialsError',
        'RefreshError',
        'OperationalError',
        'InterfaceError',
        'ProgrammingError',
    }
)


def failure_class(error):
    name = type(error).__name__
    return name if name in FAILURE_CLASSES else 'UnexpectedFailure'


def failure_fields(stage, error, started):
    return {
        'failure_class': failure_class(error),
        'failure_stage': stage,
        'failure_stage_elapsed_ms': max(0, round((time.monotonic() - started) * 1000)),
    }


class SourceFailure(Exception):
    def __init__(self, fields):
        super().__init__('SOURCE_VERIFICATION_FAILED')
        self.fields = fields


def verify_source(root, deadline):
    """Full tracked AND untracked cleanliness, never an index-only substitute."""
    stage, started = 'source_root', time.monotonic()
    try:
        if root.is_symlink() or not root.is_dir() or (root / '.git').is_symlink() or not (root / '.git').is_dir():
            raise ValueError('STANDALONE_SOURCE')
        for stage, args, cap in (
            ('source_head', ['rev-parse', 'HEAD'], HEAD_SECONDS),
            ('source_clean', ['status', '--porcelain', '--untracked-files=all'], STATUS_SECONDS),
        ):
            started = time.monotonic()
            remaining = deadline - started
            if remaining <= 0:
                raise TimeoutError()
            output = subprocess.check_output(
                ['git', '-C', str(root), *args],
                timeout=min(cap, remaining),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if (stage == 'source_head' and output != SOURCE) or (stage == 'source_clean' and output):
                raise ValueError('SOURCE')
    except Exception as error:
        raise SourceFailure(failure_fields(stage, error, started)) from None


def read_metadata(connect, expected):
    report = {'result': 'HOLD', 'customer_rows_read': False, 'state_initialized': False, 'write_attempted': False}
    conn = None
    stage, started = 'connect', time.monotonic()
    try:
        conn = connect()
        stage, started = 'transaction', time.monotonic()
        conn.execute('BEGIN READ ONLY')
        conn.execute("SET LOCAL statement_timeout = '5s'")
        stage, started = 'identity', time.monotonic()
        identity = conn.execute('SELECT current_database(), current_user, host(inet_server_addr())').fetchone()
        if tuple(identity) != TARGET:
            raise ValueError('IDENTITY')
        stage, started = 'tls', time.monotonic()
        if conn.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone() != (True,):
            raise ValueError('TLS')
        stage, started = 'migrations', time.monotonic()
        exists = conn.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL").fetchone()[0]
        actual = (
            conn.execute('SELECT version,name,checksum FROM public.schema_migrations ORDER BY version').fetchall()
            if exists
            else []
        )
        if [list(r) for r in actual] != expected:
            raise ValueError('SCHEMA_VECTOR')
        stage, started = 'indexes', time.monotonic()
        indexes = conn.execute(
            "SELECT c.relname,i.indisready,i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname",
            (INDEXES,),
        ).fetchall()
        if [list(r) for r in indexes] != [[n, True, True] for n in INDEXES]:
            raise ValueError('INDEXES')
        report.update(
            result='METADATA_READY_ONLY',
            session=list(TARGET),
            tls=True,
            migrations=expected,
            indexes=[list(r) for r in indexes],
        )
    except Exception as error:
        report.update(result='HOLD', **failure_fields(stage, error, started))
    finally:
        if conn is not None:
            started = time.monotonic()
            try:
                conn.execute('ROLLBACK')
                report['rollback'] = True
            except Exception as error:
                report.update(result='HOLD', **failure_fields('rollback', error, started), rollback=False)
            started = time.monotonic()
            try:
                conn.close()
            except Exception as error:
                report.update(result='HOLD', **failure_fields('close', error, started))
    if report['result'] == 'HOLD':
        return {
            key: report[key]
            for key in (
                'result',
                'failure_class',
                'failure_stage',
                'failure_stage_elapsed_ms',
                'write_attempted',
                'state_initialized',
                'customer_rows_read',
            )
        }
    return report


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    def alarm(*_):
        raise TimeoutError()

    signal.signal(signal.SIGALRM, alarm)
    deadline = time.monotonic() + READINESS_SECONDS
    signal.alarm(READINESS_SECONDS)
    stage, started = 'workload_binding', time.monotonic()
    try:
        root = Path('/opt/omi')
        if os.getuid() != 1000 or socket.gethostname() != 'jobstore-reconcile-0':
            raise ValueError('WORKLOAD_BINDING')
        verify_source(root, deadline)
        stage, started = 'supervisor', time.monotonic()
        supervisor_sha = hashlib.sha256(Path('/opt/runner/supervisor.py').read_bytes()).hexdigest()
        if supervisor_sha != '1b6a0a1ed5ca8dbc7f8087ae51441539a8aa9b4f4da2171932e2f08af9de699f':
            raise ValueError('SUPERVISOR')
        stage, started = 'credential_environment', time.monotonic()
        if (
            any(
                os.getenv(k)
                for k in (
                    'GOOGLE_APPLICATION_CREDENTIALS',
                    'CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE',
                    'GOOGLE_OAUTH_ACCESS_TOKEN',
                )
            )
            or (Path.home() / '.config/gcloud/application_default_credentials.json').exists()
        ):
            raise ValueError('WORKLOAD_ADC_ONLY')
        stage, started = 'credentials', time.monotonic()
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/sqlservice.login'])
        if not isinstance(credentials, Credentials):
            raise ValueError('WORKLOAD_ADC_TYPE')
        stage, started = 'driver', time.monotonic()
        if sys.version.split()[0] != '3.11.15' or psycopg.__version__ != '3.2.10':
            raise ValueError('DRIVER')
        stage, started = 'source_vector', time.monotonic()
        connection = load_module('pinned_readiness_connection', root / 'backend/database/jobstore/connection.py')
        migrate = load_module('pinned_readiness_migrate', root / 'backend/database/jobstore/migrate.py')
        expected = [[m.version, m.name, m.checksum] for m in migrate.load()]
        if [r[0] for r in expected] != list(range(1, 9)):
            raise ValueError('SOURCE_VECTOR')
        report = read_metadata(connection.iam_connector(TARGET[2], TARGET[0], TARGET[1]), expected)
        if report['result'] == 'METADATA_READY_ONLY':
            report.update(
                source_sha=SOURCE,
                supervisor_sha256=supervisor_sha,
                python=sys.version.split()[0],
                psycopg=psycopg.__version__,
            )
    except Exception as error:
        fields = error.fields if isinstance(error, SourceFailure) else failure_fields(stage, error, started)
        report = {
            'result': 'HOLD',
            **fields,
            'write_attempted': False,
            'state_initialized': False,
            'customer_rows_read': False,
        }
    finally:
        signal.alarm(0)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['result'] == 'METADATA_READY_ONLY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
