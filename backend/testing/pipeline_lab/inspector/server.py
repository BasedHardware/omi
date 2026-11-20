"""Stdlib HTTP server for the pipeline-lab inspector: JSON API, audio with Range, verdict writes, static UI.

Binds loopback only. Reach it from other devices with ``tailscale serve`` (never funnel); requests that
arrive through a proxy must carry a ``Tailscale-User-Login`` on the ``--allow-login`` list. Read-only
over the run store; the only write is an append to ``$OMI_PIPELINE_LAB_VERDICTS/verdicts.jsonl``.

    python -m testing.pipeline_lab.inspector.server [--root DIR] [--verdicts DIR] [--port 8765]

Routes (all JSON unless noted):
    GET  /api/runs                                   runs, newest first, with status counts
    GET  /api/runs/<run>                             day overview: header, timeline rows, conversation list
    GET  /api/runs/<run>/day                         day panel: daily summary pair, goals, memory delta, push log
    GET  /api/runs/<run>/conversations/<id>          replay conversation + production twin + diff-ready pairs
    GET  /api/runs/<run>/production/<id>             a production conversation the replay is missing
    GET  /api/runs/<run>/llm_calls[?conversation_id=]
    GET  /api/days/<day>/baseline                    the raw production baseline for the day
    GET  /api/verdicts[?run_id&day_id&item_kind&mark&history=1]
    GET  /api/verdicts/export[?...]                  latest verdicts as JSONL (download)
    POST /api/verdicts                               {run_id, conversation_id, item_kind, item_key, mark, note}
    GET  /audio/<day>/<clip_id>                      audio bytes, HTTP Range supported
    GET  /, /static/<file>                           the UI
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from testing.pipeline_lab.inspector import views
from testing.pipeline_lab.inspector.reader import BadRequest, NotFound, Reader, safe_id

ROOT_ENV = 'OMI_PIPELINE_LAB_ROOT'
VERDICTS_ENV = 'OMI_PIPELINE_LAB_VERDICTS'
LOGINS_ENV = 'OMI_PIPELINE_LAB_ALLOWED_LOGINS'
DEFAULT_ROOT = '/Volumes/Ephemeral/pipeline-lab'
DEFAULT_VERDICTS = '~/.local/share/pipeline-lab/verdicts'
DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).resolve().parent / 'static'
STATIC_NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,63}\.(?:html|css|js|svg)')
MAX_BODY = 64 * 1024
CHUNK = 256 * 1024
LOOPBACK_NAMES = {'localhost', '127.0.0.1', '::1'}
PROXY_HEADERS = ('Tailscale-User-Login', 'X-Forwarded-For', 'X-Forwarded-Host', 'Forwarded')
CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.wav': 'audio/wav',
    '.m4a': 'audio/mp4',
    '.mp4': 'audio/mp4',
    '.aac': 'audio/aac',
    '.mp3': 'audio/mpeg',
    '.ogg': 'audio/ogg',
    '.opus': 'audio/ogg',
    '.flac': 'audio/flac',
    '.webm': 'audio/webm',
}
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "media-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


_RANGE = re.compile(r'bytes=(\d{0,19})-(\d{0,19})', re.IGNORECASE)  # matched after whitespace is removed


def parse_range(header: Optional[str], size: int) -> Optional[tuple[int, int]]:
    """``(start, end)`` inclusive for one ``bytes=`` range; ``None`` = serve whole; ``ValueError`` = 416.

    Malformed, multi-range and non-byte headers are ignored (RFC 9110 14.2 allows serving the whole).
    """
    compact = ''.join((header or '')[:200].split())  # bounded input, no backtracking over spaces
    match = _RANGE.fullmatch(compact)
    if not match:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:
        length = int(last)
        if length == 0 or size == 0:
            raise ValueError('unsatisfiable suffix range')
        return max(0, size - length), size - 1
    start = int(first)
    if last and int(last) < start:
        return None  # syntactically invalid: ignore the header
    if start >= size:
        raise ValueError('unsatisfiable range')
    end = int(last) if last else size - 1
    return start, min(end, size - 1)


def _host_name(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith('['):
        return host[1:].split(']', 1)[0]
    return host.rsplit(':', 1)[0] if host.count(':') == 1 else host


def _is_loopback(name: str) -> bool:
    if name in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


class InspectorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        reader: Reader,
        *,
        allowed_hosts: Iterable[str] = (),
        allowed_logins: Iterable[str] = (),
        static_dir: Path = STATIC_DIR,
        quiet: bool = True,
    ):
        host = address[0]
        if not _is_loopback(host):
            raise ValueError('the inspector binds loopback only; use tailscale serve to reach it from other devices')
        self.reader = reader
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.allowed_logins = {login.strip().lower() for login in allowed_logins if login.strip()}
        self.static_dir = static_dir
        self.quiet = quiet
        super().__init__(address, InspectorHandler)


class InspectorHandler(BaseHTTPRequestHandler):
    server: InspectorServer
    server_version = 'pipeline-lab-inspector'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    # ---- plumbing

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature from BaseHTTPRequestHandler
        if not self.server.quiet:
            sys.stderr.write('inspector: ' + (format % args) + '\n')

    def _headers(self, status: int, content_type: str, length: int, extra: Optional[dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _send(self, status: int, body: bytes, content_type: str, extra: Optional[dict[str, str]] = None) -> None:
        self._headers(status, content_type, len(body), extra)
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _json(self, value: Any, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self._send(status, body, 'application/json; charset=utf-8')

    def _error(self, status: int, message: str) -> None:
        self._json({'error': message}, status)

    # ---- access policy

    def _proxied(self) -> bool:
        if any(self.headers.get(name) for name in PROXY_HEADERS):
            return True
        return not _is_loopback(_host_name(self.headers.get('Host') or ''))

    def _allowed(self) -> Optional[tuple[int, str]]:
        """``None`` when the request may proceed, else ``(status, reason)``."""
        host = _host_name(self.headers.get('Host') or '')
        if not (_is_loopback(host) or host.endswith('.ts.net') or host in self.server.allowed_hosts):
            return HTTPStatus.MISDIRECTED_REQUEST, 'unexpected Host header'
        if self._proxied():
            login = (self.headers.get('Tailscale-User-Login') or '').strip().lower()
            if not login or login not in self.server.allowed_logins:
                return HTTPStatus.FORBIDDEN, f'proxied requests need a Tailscale login listed in {LOGINS_ENV}'
        return None

    def _reviewer(self) -> Optional[str]:
        login = (self.headers.get('Tailscale-User-Login') or '').strip()
        return login or None

    # ---- verbs

    def do_HEAD(self) -> None:  # noqa: N802 - http.server naming
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        denied = self._allowed()
        if denied:
            return self._error(*denied)
        parts = urlsplit(self.path)
        try:
            segments = [unquote(s) for s in parts.path.split('/') if s]
        except Exception:  # noqa: BLE001 - undecodable path
            return self._error(400, 'bad path')
        query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        try:
            self._route_get(segments, query)
        except NotFound as exc:
            self._error(404, str(exc) or 'not found')
        except BadRequest as exc:
            self._error(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _route_get(self, seg: list[str], query: dict[str, str]) -> None:
        reader = self.server.reader
        if not seg or seg == ['index.html']:
            return self._static('index.html')
        head = seg[0]
        if head == 'static' and len(seg) == 2:
            return self._static(seg[1])
        if head == 'audio' and len(seg) == 3:
            return self._audio(seg[1], seg[2])
        if head != 'api' or len(seg) < 2:
            raise NotFound('not found')
        rest = seg[1:]
        if rest == ['runs']:
            return self._json({'runs': views.runs_list(reader)})
        if rest[0] == 'runs' and len(rest) >= 2:
            run_id = safe_id(rest[1], 'run id')
            tail = rest[2:]
            if not tail:
                return self._json(views.run_overview(reader, run_id))
            if tail == ['day']:
                return self._json(views.day_panel(reader, run_id))
            if tail == ['llm_calls']:
                return self._json({'calls': views.llm_calls(reader, run_id, query.get('conversation_id'))})
            if len(tail) == 2 and tail[0] == 'conversations':
                return self._json(views.conversation_detail(reader, run_id, safe_id(tail[1])))
            if len(tail) == 2 and tail[0] == 'production':
                return self._json(views.production_detail(reader, run_id, safe_id(tail[1])))
        if rest[0] == 'days' and len(rest) == 3 and rest[2] == 'baseline':
            return self._json(views.baseline_view(reader, rest[1]))
        if rest[0] == 'verdicts' and len(rest) <= 2:
            filters = {k: query.get(k) for k in ('run_id', 'day_id', 'item_kind', 'mark', 'conversation_id')}
            rows = reader.verdicts(latest=query.get('history') != '1', **filters)
            rows.sort(key=lambda r: r.get('at') or '', reverse=True)
            if rest == ['verdicts']:
                return self._json({'verdicts': [views.with_open_link(reader, r) for r in rows]})
            if rest[1] == 'export':
                body = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows).encode('utf-8')
                return self._send(
                    200,
                    body,
                    'application/x-ndjson; charset=utf-8',
                    {'Content-Disposition': 'attachment; filename="verdicts.jsonl"'},
                )
        raise NotFound('not found')

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self.close_connection = True  # a refused write may leave its body unread; never reuse that stream
        denied = self._allowed()
        if denied:
            return self._error(*denied)
        if urlsplit(self.path).path != '/api/verdicts':
            return self._error(404, 'not found')
        origin = self.headers.get('Origin')
        if origin:
            origin_host = _host_name(urlsplit(origin).netloc)
            if origin_host != _host_name(self.headers.get('Host') or ''):
                return self._error(403, 'cross-origin write refused')
        if (self.headers.get('Sec-Fetch-Site') or 'same-origin') not in ('same-origin', 'none'):
            return self._error(403, 'cross-site write refused')
        if not (self.headers.get('Content-Type') or '').startswith('application/json'):
            return self._error(415, 'expected application/json')
        try:
            length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            return self._error(400, 'bad Content-Length')
        if length <= 0 or length > MAX_BODY:
            return self._error(413, 'body too large or empty')
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            row = views.build_verdict(self.server.reader, payload, reviewer=self._reviewer())
            self.server.reader.append_verdict(row)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._error(400, 'invalid JSON')
        except BadRequest as exc:
            return self._error(400, str(exc))
        except NotFound as exc:
            return self._error(404, str(exc) or 'not found')
        self._json({'verdict': row}, 201)

    # ---- files

    def _static(self, name: str) -> None:
        if len(name) > 72 or not STATIC_NAME.fullmatch(name):
            raise NotFound('not found')
        path = self.server.static_dir / name
        if not path.is_file():
            raise NotFound('not found')
        self._send(200, path.read_bytes(), CONTENT_TYPES[path.suffix])

    def _audio(self, day_id: str, clip_id: str) -> None:
        path, _entry = self.server.reader.audio_file(day_id, clip_id)
        size = path.stat().st_size
        content_type = CONTENT_TYPES.get(path.suffix.lower(), 'application/octet-stream')
        try:
            window = parse_range(self.headers.get('Range'), size)
        except ValueError:
            return self._send(416, b'', 'text/plain', {'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
        start, end = window if window else (0, size - 1)
        length = max(0, end - start + 1)
        extra = {'Accept-Ranges': 'bytes'}
        if window:
            extra['Content-Range'] = f'bytes {start}-{end}/{size}'
        self._headers(206 if window else 200, content_type, length, extra)
        if self.command == 'HEAD' or length == 0:
            return
        with path.open('rb') as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def make_server(
    root: Path,
    verdicts_root: Path,
    *,
    host: str = '127.0.0.1',
    port: int = 0,
    allowed_hosts: Iterable[str] = (),
    allowed_logins: Iterable[str] = (),
    quiet: bool = True,
) -> InspectorServer:
    return InspectorServer(
        (host, port),
        Reader(root, verdicts_root),
        allowed_hosts=allowed_hosts,
        allowed_logins=allowed_logins,
        quiet=quiet,
    )


def serve_in_thread(server: InspectorServer) -> Callable[[], None]:
    """Start ``server`` on a daemon thread; returns a stop function (used by tests)."""
    thread = threading.Thread(target=server.serve_forever, name='inspector', daemon=True)
    thread.start()

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return stop


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Serve the pipeline-lab inspector on loopback.')
    parser.add_argument('--root', default=os.environ.get(ROOT_ENV) or DEFAULT_ROOT)
    parser.add_argument('--verdicts', default=os.environ.get(VERDICTS_ENV) or DEFAULT_VERDICTS)
    parser.add_argument('--host', default='127.0.0.1', help='loopback address to bind')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='0 picks a free port')
    parser.add_argument('--allow-host', action='append', default=[], help='extra Host header to accept')
    parser.add_argument(
        '--allow-login',
        action='append',
        default=[login for login in (os.environ.get(LOGINS_ENV) or '').split(',') if login.strip()],
        help=f'Tailscale login allowed through tailscale serve (also {LOGINS_ENV}, comma-separated)',
    )
    parser.add_argument('--verbose', action='store_true', help='log requests to stderr')
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser()
    if not root.is_dir():
        parser.error('store root does not exist (set --root or OMI_PIPELINE_LAB_ROOT)')
    try:
        server = make_server(
            root,
            Path(args.verdicts).expanduser(),
            host=args.host,
            port=args.port,
            allowed_hosts=args.allow_host,
            allowed_logins=args.allow_login,
            quiet=not args.verbose,
        )
    except ValueError as exc:
        parser.error(str(exc))
    host, port = server.server_address[:2]
    print(json.dumps({'url': f'http://{host}:{port}/', 'pid': os.getpid()}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
