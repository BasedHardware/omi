"""A loopback stand-in for the hosted diarizer: ``POST /v2/diarization`` and ``POST /v2/embedding``.

Product code reaches speaker models only through ``HOSTED_DIARIZATION_API_URL`` (whole-conversation final pass)
and ``HOSTED_SPEAKER_EMBEDDING_API_URL`` (resolver, live matching, enrollment). Pointing both at this peer runs
every product speaker path unchanged, with answers from **speaker cassettes**:

- ``replay`` (default, CI): answers only from cassettes; a miss is HTTP 409 naming the record command. No
  model, no torch, no network.
- ``record-local``: a miss runs production's diarizer code on this machine's CPU (:mod:`local_worker`, in the
  optional local-models venv) and files the answer as ``source: local``.

A cassette is keyed on the route, the query parameters that change the answer, the pinned model revisions and
the exact request audio bytes, so a model bump or different audio is a miss, never a stale hit. Cassettes for
committed public corpora live in ``speakers/fixtures/cassettes/``; everything else (private audio) under
``<lab root>/speakers/cassettes/``, owner-only.

CPU FP32 is not CUDA BF16 parity: a local cassette is evidence for everything after the model (assignment,
naming, thresholds, persistence), and an approximation of the model's own output.
"""

from __future__ import annotations

import email.parser
import email.policy
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

BACKEND = Path(__file__).resolve().parents[3]
PUBLIC_CASSETTES = Path(__file__).resolve().parent / 'fixtures' / 'cassettes'
PYTHON_ENV = 'OMI_PIPELINE_LAB_LOCAL_SPEAKERS_PYTHON'
FALLBACK_PYTHON_ENV = 'OMI_PIPELINE_LAB_LOCAL_STT_PYTHON'
MODES = ('replay', 'record-local')
INSTALL = (
    'record-local needs the optional local-models venv outside the repository: `uv venv -p python3.11 '
    '<dir>/venv && uv pip install -p <dir>/venv/bin/python -r backend/testing/pipeline_lab/'
    f'requirements-local-speakers.txt`, then `export {PYTHON_ENV}=<dir>/venv/bin/python HF_HOME=<dir>/hf` and a '
    'Hugging Face token that accepted pyannote/speaker-diarization-community-1 (first run only; then '
    'HF_HUB_OFFLINE=1)'
)


class CassetteMiss(LookupError):
    pass


def _source_pin(path: Path, name: str) -> str:
    match = re.search(rf"\b{name}\s*=\s*['\"]([0-9a-f]{{40}})['\"]", path.read_text(encoding='utf-8'))
    if not match:
        raise RuntimeError(f'{name} not found in {path.name}')
    return match.group(1)


def model_pins() -> dict[str, str]:
    """The diarizer's pinned revisions, read from source (importing those modules needs torch)."""
    return {
        'diarization': _source_pin(BACKEND / 'diarizer' / 'final_pass.py', 'MODEL_REVISION'),
        'embedding': _source_pin(BACKEND / 'diarizer' / 'embedding.py', 'revision'),
    }


def cassette_key(route: str, params: dict, body: bytes, pins: dict[str, str]) -> str:
    head = json.dumps({'route': route, 'params': params, 'pins': pins}, sort_keys=True).encode()
    return hashlib.sha256(head + b'\0' + hashlib.sha256(body).digest()).hexdigest()


def _route_dir(root: Path, route: str) -> Path:
    return root / route.strip('/').replace('/', '_')


@dataclass
class CassetteStore:
    """Reads committed public cassettes and the private root; writes where it is told."""

    private_root: Optional[Path]
    write_public: bool = False
    public_root: Path = PUBLIC_CASSETTES

    def _path(self, root: Path, route: str, key: str) -> Path:
        return _route_dir(root, route) / key[:2] / f'{key}.json'

    def get(self, route: str, key: str) -> Optional[dict]:
        for root in (self.public_root, self.private_root):
            if root is None:
                continue
            path = self._path(root, route, key)
            if path.is_file():
                return json.loads(path.read_text())
        return None

    def put(self, route: str, key: str, entry: dict) -> Path:
        if self.write_public:
            path = self._path(self.public_root, route, key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n')
            return path
        if self.private_root is None:
            raise RuntimeError('no private cassette root')
        from testing.pipeline_lab.store import atomic_write_json, ensure_private_dir

        path = self._path(self.private_root, route, key)
        ensure_private_dir(path.parent)
        atomic_write_json(path, entry)
        return path


class LocalModels:
    """The local worker process: started on the first miss, kept for the peer's lifetime."""

    def __init__(self, workdir: Path, python: Optional[str] = None):
        self.python = python or os.environ.get(PYTHON_ENV) or os.environ.get(FALLBACK_PYTHON_ENV)
        self.workdir = workdir
        self.process: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()

    def _start(self) -> subprocess.Popen:
        if not self.python or not Path(self.python).is_file():
            raise RuntimeError(INSTALL)
        env = {**os.environ, 'OMI_PIPELINE_LAB_SPEAKERS_WORKDIR': str(self.workdir)}
        env.setdefault('HF_HUB_OFFLINE', '1')
        process = subprocess.Popen(
            [self.python, str(Path(__file__).with_name('local_worker.py'))],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=open(self.workdir / 'local_worker.log', 'ab'),
            text=True,
            cwd=str(self.workdir),
            env=env,
        )
        ready = json.loads(process.stdout.readline() or '{}')
        if not ready.get('ready'):
            raise RuntimeError(f'local speaker worker failed to start (see {self.workdir}/local_worker.log)')
        return process

    def run(self, request: dict) -> dict:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self.process = self._start()
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('local speaker worker exited')
        return json.loads(line)

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


@dataclass
class PeerStats:
    calls: list = field(default_factory=list)

    def record(self, route: str, outcome: str, seconds: float, audio_seconds: float) -> None:
        self.calls.append({'route': route, 'outcome': outcome, 'seconds': round(seconds, 3), 'audio': audio_seconds})

    def summary(self) -> dict:
        out: dict[str, dict[str, int]] = {}
        for call in self.calls:
            row = out.setdefault(call['route'], {})
            row[call['outcome']] = row.get(call['outcome'], 0) + 1
        return out


def _multipart_file(content_type: str, body: bytes) -> bytes:
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b'Content-Type: ' + content_type.encode() + b'\r\n\r\n' + body
    )
    for part in message.iter_parts():
        if part.get_param('name', header='content-disposition') == 'file':
            return part.get_payload(decode=True) or b''
    raise ValueError('multipart upload has no file part')


class SpeakerPeer:
    """Serve the hosted diarizer's routes on loopback. ``url`` goes into both product URL variables."""

    def __init__(
        self,
        mode: str = 'replay',
        *,
        store: Optional[CassetteStore] = None,
        workdir: Optional[Path] = None,
        local: Optional[Any] = None,
    ):
        if mode not in MODES:
            raise ValueError(f'speaker peer mode must be one of {MODES}')
        self.mode = mode
        self.pins = model_pins()
        if store is None or workdir is None:
            from testing.pipeline_lab.scenario.paths import private_lab_root
            from testing.pipeline_lab.store import ensure_private_dir

            root = ensure_private_dir(private_lab_root() / 'speakers')
            store = store or CassetteStore(ensure_private_dir(root / 'cassettes'))
            workdir = workdir or ensure_private_dir(ensure_private_dir(private_lab_root() / 'tmp') / 'speakers')
        self.store = store
        self.workdir = workdir
        self.local = local if local is not None else (LocalModels(workdir) if mode == 'record-local' else None)
        self.stats = PeerStats()
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    # ---- answering -------------------------------------------------------------------------------

    def answer(self, route: str, params: dict, body: bytes, content_type: str) -> tuple[int, Any]:
        started = time.monotonic()
        if route == '/v2/embedding':
            audio = _multipart_file(content_type, body) if content_type.startswith('multipart/') else body
            request_params: dict = {}
            seconds = max(0.0, (len(audio) - 44) / 32000)
        elif route == '/v2/diarization':
            audio = body
            request_params = {k: int(v) for k, v in params.items() if k in ('min_speakers', 'max_speakers')}
            request_params['content_type'] = content_type or 'audio/pcm'
            seconds = len(audio) / 32000
        else:
            return 404, {'detail': 'not a diarizer route'}
        key = cassette_key(route, request_params, audio, self.pins)
        hit = self.store.get(route, key)
        if hit is not None:
            self.stats.record(route, 'hit', time.monotonic() - started, seconds)
            return int(hit.get('status', 200)), hit['body']
        if self.mode == 'replay':
            self.stats.record(route, 'miss', time.monotonic() - started, seconds)
            return 409, {'detail': f'speaker cassette miss ({route}); record it with --speakers record-local'}
        from testing.pipeline_lab.store import atomic_write_bytes

        work = self.workdir / f'req-{key[:16]}.{"wav" if route == "/v2/embedding" else "bin"}'
        atomic_write_bytes(work, audio)
        try:
            reply = self.local.run(
                {
                    'op': route.rsplit('/', 1)[-1],
                    'path': str(work),
                    'content_type': request_params.get('content_type'),
                    'min_speakers': request_params.get('min_speakers'),
                    'max_speakers': request_params.get('max_speakers'),
                }
            )
        finally:
            work.unlink(missing_ok=True)
        status = 200 if reply.get('ok') else int(reply.get('status') or 500)
        response = reply['body'] if reply.get('ok') else {'detail': reply.get('detail')}
        if status in (200, 422):  # deterministic answers (422: audio too short) are worth keeping
            self.store.put(
                route,
                key,
                {
                    'route': route,
                    'params': request_params,
                    'pins': self.pins,
                    'source': 'local',
                    'device': 'cpu-fp32',
                    'audio_sha256': hashlib.sha256(audio).hexdigest(),
                    'audio_seconds': round(seconds, 3),
                    'status': status,
                    'body': response,
                },
            )
        self.stats.record(route, 'recorded' if status in (200, 422) else 'error', time.monotonic() - started, seconds)
        return status, response

    # ---- serving ---------------------------------------------------------------------------------

    def start(self) -> 'SpeakerPeer':
        peer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (http.server API)
                parsed = urlparse(self.path)
                length = int(self.headers.get('Content-Length') or 0)
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    body = bytearray()
                    while True:
                        size = int(self.rfile.readline().strip() or b'0', 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        body.extend(self.rfile.read(size))
                        self.rfile.readline()
                    body = bytes(body)
                else:
                    body = self.rfile.read(length)
                params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
                try:
                    status, payload = peer.answer(
                        parsed.path, params, body, (self.headers.get('Content-Type') or '').strip()
                    )
                except Exception as error:
                    status, payload = 500, {'detail': f'{type(error).__name__}: {error}'[:300]}
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name='speaker-peer', daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        if self.server is None:
            raise RuntimeError('peer not started')
        host, port = self.server.server_address[:2]
        return f'http://{host}:{port}'

    def env(self) -> dict[str, str]:
        """The product environment that routes every speaker model call to this peer."""
        return {'HOSTED_DIARIZATION_API_URL': self.url, 'HOSTED_SPEAKER_EMBEDDING_API_URL': self.url}

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.local is not None:
            self.local.close()

    def __enter__(self) -> 'SpeakerPeer':
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()
