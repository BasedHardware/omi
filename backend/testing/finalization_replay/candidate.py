"""Loopback adapter for the Go conformance port, backed by the Firestore emulator."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from selectors import DefaultSelector, EVENT_READ
import subprocess
from threading import Lock, Thread
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from testing.finalization_replay.corpus import pack
from testing.finalization_replay.metrics import suspend_meter
from testing.finalization_replay.providers import response


@contextmanager
def _isolated_libpq_environment():
    saved = {name: value for name, value in os.environ.items() if name.startswith('PG')}
    try:
        for name in saved:
            os.environ.pop(name, None)
        yield
    finally:
        os.environ.update(saved)


def _connect_loopback(connect, dsn):
    parsed = urlsplit(dsn)
    if parsed.hostname != '127.0.0.1' or not parsed.port:
        raise ValueError('replay database connection must target loopback')
    with _isolated_libpq_environment():
        return connect(
            dsn,
            autocommit=True,
            connect_timeout=5,
            host='127.0.0.1',
            hostaddr='127.0.0.1',
            port=parsed.port,
        )


@contextmanager
def replay_database(dsn):
    from psycopg import connect, sql

    parsed = urlsplit(dsn)
    if (
        parsed.scheme != 'postgres'
        or parsed.hostname != '127.0.0.1'
        or not parsed.port
        or parsed.query != 'sslmode=disable'
        or parsed.fragment
        or not re.fullmatch(r'/[a-zA-Z0-9_]+', parsed.path)
        or not parsed.username
        or ',' in parsed.netloc
    ):
        raise ValueError('replay requires a loopback TEST_DATABASE_URL with sslmode=disable')
    database = f'replay_{uuid4().hex}'
    connection_context = _connect_loopback(connect, dsn)
    with connection_context as connection:
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        try:
            yield urlunsplit(parsed._replace(path=f'/{database}'))
        finally:
            connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))


def _document(state):
    data = state.conversation.get().to_dict()
    if data is None:
        return None
    # jobd's wire encodes a stored Firestore bytes field as {"base64": ...}.
    doc = pack(data)
    segments = doc.get('transcript_segments')
    if isinstance(segments, dict) and segments.keys() == {'$bytes'}:
        doc['transcript_segments'] = {'base64': segments['$bytes']}
    return doc | {'version': state.version}


def _bound(state, body):
    doc = state.conversation.get().to_dict() or {}
    return (
        (body['uid'], body['subject_id']) == (state.uid, state.cid)
        and doc.get('finalization_job_id') == body['job_id']
        and doc.get('finalization_revision') == body['revision']
        and doc.get('fanout_state') == 'claimed'
        and not doc.get('discarded')
    )


def _request(method, url, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    request = Request(url, data=body, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def _wait(proc, url, done):
    deadline = monotonic() + 60
    while monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('jobd exited during replay')
        try:
            code, body = _request('GET', url)
            if done(code, body):
                return body
        except URLError:
            pass
        sleep(0.05)
    raise TimeoutError('jobd did not reach expected state')


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass

    def _reply(self, status, data):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self):
        length = int(self.headers['Content-Length'])
        if not 0 < length <= 2 * 1024 * 1024:
            raise ValueError('invalid stub request size')
        return json.loads(self.rfile.read(length))

    def _dispatch(self):
        try:
            with self.server.lock:
                status, result = self._route()
        except Exception as error:
            self.server.errors.append(type(error).__name__)
            status, result = 500, {'code': 'replay_adapter_error'}
        self._reply(status, result)

    do_GET = do_PATCH = do_POST = do_PUT = do_DELETE = _dispatch

    def _route(self):
        state = self.server.state
        parts = self.path.strip('/').split('/')
        match self.command, parts:
            case 'GET', ['accounts', uid] if uid == state.uid:
                row = state.user.get().to_dict()
                return 200, {
                    'min_words': state.case.get('min_words', 1),
                    'apps': state.apps,
                    'own_key': row['byok']['active'],
                }
            case ('GET' | 'PATCH'), ['conversations', uid, cid] if (uid, cid) == (state.uid, state.cid):
                return self._conversation(state)
            case 'POST', ['llm', 'notes' | 'memories' as step]:
                request = self._body()
                if (request['uid'], request['subject_id']) == (state.uid, state.cid):
                    feature = 'conv-structure' if step == 'notes' else 'memory-l1'
                    fixture = response(state, feature)
                    if step == 'notes':
                        result = {field: fixture[field] for field in ('title', 'overview')}
                    else:
                        result = {'contents': [item['text'] for item in fixture['items']]}
                    state.record_provider_call(feature, request.get('input', ''), result)
                    return 200, result
            case 'PUT', ['vectors', uid, cid] if (uid, cid) == (state.uid, state.cid):
                body = self._body()
                if not _bound(state, body):
                    return 409, {'code': 'fenced'}
                state.vector(cid)
                state.effects['conformance_vector_payload'] = {'overview': body['overview']}
                return 200, {}
            case 'PUT', ['memories', uid, memory_id] if uid == state.uid:
                body = self._body()
                if not _bound(state, body):
                    return 409, {'code': 'fenced'}
                state.memory(memory_id, body['content'], body['data_protection_level'])
                return 200, {}
            case 'POST', ['apps', app] if app in state.apps:
                body = self._body()
                if _bound(state, body):
                    state.webhook(app, self.headers.get('X-Omi-Idempotency-Key'), body)
                    if app == state.case.get('unavailable_app'):
                        return 503, {'code': 'fixture_unavailable'}
                    return 200, {}
                return 409, {'code': 'fenced'}
            case 'DELETE', ['accounts', uid, 'data'] if uid == state.uid:
                state.client.recursive_delete(state.user)
                if state.user.get().exists:
                    raise RuntimeError('Go replay erase left a user document')
                return 200, {}
        raise ValueError('unexpected jobd stub request')

    def _conversation(self, state):
        if self.command == 'GET' and state.case.get('delete_before_worker_read'):
            reads = state.case.get('_go_conversation_reads', 0) + 1
            state.case['_go_conversation_reads'] = reads
            if reads > 1 and not state.case.get('_go_conversation_deleted'):
                state.case['_go_conversation_deleted'] = True
                state.conversation.delete()
                return 404, {'code': 'not_found'}
        doc = _document(state)
        if doc is None:
            return 404, {'code': 'not_found'}
        if self.command == 'GET':
            return 200, doc
        patch = self._body()
        if patch['expected_version'] != state.version:
            return 409, {'code': 'version_conflict'}
        from google.cloud.firestore import DELETE_FIELD

        state.conversation.update(
            {key: DELETE_FIELD if value is None else value for key, value in patch['patch'].items()}
        )
        state.version += 1
        return 200, _document(state)


@contextmanager
def _stub(state):
    with ThreadingHTTPServer(('127.0.0.1', 0), _Handler) as server:
        server.errors = []
        server.lock = Lock()
        server.state = state
        worker = Thread(target=server.serve_forever)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', server.errors
        finally:
            server.shutdown()
            worker.join()


def _admit(proc, url, state, database):
    from psycopg import connect

    path = f'{url}/v1/conversations/{state.cid}/end'
    request = {
        'uid': state.uid,
        'revision': state.case.get('revision', 1),
        'trigger': state.case.get('trigger', 'capture_end'),
        'end_reason': state.case.get('end_reason', 'user_stop'),
    }
    status, body = _request('POST', path, request)
    if status != 202:
        reason = body['error']
        if status >= 500 or reason == 'invalid_request':
            raise RuntimeError('Go admission failed')
        return (
            'terminal'
            if reason in {'conversation_completed', 'conversation_failed', 'conversation_discarded'}
            else reason
        )
    job_id = body['job_id']
    if state.case.get('repeat') and _request('POST', path, request) != (202, body):
        raise RuntimeError('Go duplicate admitted a different job')
    job = _wait(
        proc,
        f'{url}/v1/jobs/{job_id}',
        lambda code, job: (code == 200 and job['state'] in {'completed', 'parked', 'blocked_byok'}),
    )
    own_key = job['state'] == 'blocked_byok'
    state.admitted = {'job_id': job_id, 'fanout_key': job['fanout_key'], 'own_key': own_key}
    if own_key:
        job_url = f'{url}/v1/jobs/{job_id}'
        status, _ = _request('POST', f'{job_url}/resume', headers={'X-Omi-Vendor-Key': 'replay-only-vendor-key'})
        if status != 202:
            raise RuntimeError('Go BYOK resume rejected')
        job = _wait(proc, job_url, lambda code, result: code == 200 and result['state'] in {'completed', 'parked'})
    state.go_evidence['job'] = {
        'state': job['state'],
        'reason': job.get('reason'),
        'outcome': job.get('outcome'),
    }
    with _connect_loopback(connect, database) as connection, connection.cursor() as cursor:
        cursor.execute('SELECT meta FROM queue_jobs WHERE job_key = %s', (job_id,))
        metadata = cursor.fetchone()
    if metadata is None:
        raise RuntimeError('Go replay job row disappeared before observation')
    state.go_evidence['job']['metadata'] = metadata[0]
    state.queue_fanout_key = job['fanout_key']
    if state.case.get('erase_after'):
        with suspend_meter():
            state.capture_before_erasure()
        status, _ = _request('POST', f'{url}/v1/users/{state.uid}/erase')
        if status != 200:
            raise RuntimeError('Go replay erase was refused')
        user_document_absent = not state.user.get().exists
        if not user_document_absent:
            raise RuntimeError('Go replay erase left the owner document')
        with _connect_loopback(connect, database) as connection, connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM queue_jobs WHERE uid = %s', (state.uid,))
            jobs_for_uid = cursor.fetchone()[0]
            cursor.execute('SELECT count(*) FROM queue_tenants WHERE uid = %s', (state.uid,))
            tenants_for_uid = cursor.fetchone()[0]
        erasure = {
            'user_document_absent': user_document_absent,
            'conversation_absent': not state.conversation.get().exists,
            'jobs_for_uid': jobs_for_uid,
            'tenants_for_uid': tenants_for_uid,
        }
        state.go_evidence['erasure'] = erasure
        state.effects['erasure'] = erasure
    if job.get('outcome') == 'fenced':
        return 'fenced'
    if job['state'] == 'completed' and (state.conversation.get().to_dict() or {}).get('discarded'):
        return 'discarded'
    return job['state']


def _listener_url(proc):
    with DefaultSelector() as selector:
        selector.register(proc.stdout, EVENT_READ)
        if not selector.select(timeout=60):
            raise TimeoutError('jobd did not announce its loopback listener')
        address = proc.stdout.readline(64).decode('ascii').strip()
    if not re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{0,4}', address):
        raise RuntimeError('jobd did not bind an ephemeral loopback listener')
    return f'http://{address}'


def run_candidate(state, jobd: Path, database: str, key: str):
    with _stub(state) as (stub, errors):
        env = {
            'DATABASE_URL': database,
            'STUB_URL': stub,
            'ENCRYPTION_SECRET': key,
            'JOBD_REPLAY_LISTEN': '1',
            'WORKERS': '1',
            'BACKOFF_BASE_MS': '20',
            'BUDGET_REQUEUE_SECONDS': '0',
            'MAX_ATTEMPTS': '1' if state.case.get('final_attempt') else '5',
        }
        # jobd uses database/HTTP wire observations; never pass host credentials or proxies.
        with subprocess.Popen(
            [str(jobd), 'serve'],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as proc:
            try:
                url = _listener_url(proc)
                _wait(proc, f'{url}/healthz', lambda code, _body: code == 200)
                status = _admit(proc, url, state, database)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        if errors:
            raise RuntimeError('Go Firestore stub request failed')
        return status


def migrate(jobd: Path, database: str):
    subprocess.run(
        [str(jobd), 'migrate'],
        env={'DATABASE_URL': database},
        check=True,
        timeout=25,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
