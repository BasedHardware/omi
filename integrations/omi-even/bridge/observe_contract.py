#!/usr/bin/env python3
"""Capture the Even Realities "Add Agent" HTTP contract from real hardware.

Even publishes no specification for the custom-agent endpoint. Everything known
about it is reverse-engineered from blog posts, so this logs exactly what the
device sends before any real endpoint is written against it.

It answers with a well-formed OpenAI chat-completion, so a single spoken query
verifies both directions at once: the log shows what the glasses send, and the
display shows whether our response shape is one the glasses can render.

Zero dependencies -- stdlib only, so it runs before the bridge venv exists.

    python3 observe_contract.py [--port 8788]

Then register the URL in the Even app (Add Agent) and speak one question.
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG_PATH = Path(__file__).with_name('add-agent-capture.log')

# Long enough to be unmistakable on the 576x288 display, short enough to fit.
REPLY_TEXT = 'omi bridge online. Contract captured -- check the Mac.'


def _record(entry: dict) -> None:
    """Write one captured request to stdout and the log file."""
    rendered = json.dumps(entry, indent=2, ensure_ascii=False)
    print(f'\n=== {entry["method"]} {entry["path"]} @ {entry["received_at"]} ===')
    print(rendered, flush=True)
    with LOG_PATH.open('a', encoding='utf-8') as fh:
        fh.write(rendered + '\n---\n')


class CaptureHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'omi-even-observe/0'

    def _capture(self) -> None:
        # Read the body strictly by Content-Length; a short read would hang and
        # the glasses would report a timeout rather than a contract mismatch.
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b''

        try:
            body = json.loads(raw.decode('utf-8')) if raw else None
            body_parse_error = None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            body = raw.decode('utf-8', errors='replace')
            body_parse_error = str(exc)

        _record(
            {
                'received_at': datetime.now(timezone.utc).isoformat(),
                'method': self.command,
                'path': self.path,
                'client': self.client_address[0],
                'http_version': self.request_version,
                # Header order and exact casing matter when reverse-engineering.
                'headers': [[k, v] for k, v in self.headers.items()],
                'body_bytes': len(raw),
                'body': body,
                'body_parse_error': body_parse_error,
            }
        )

        self._respond_openai()

    def _respond_openai(self) -> None:
        payload = json.dumps(
            {
                'id': f'chatcmpl-{uuid.uuid4().hex[:24]}',
                'object': 'chat.completion',
                'created': int(time.time()),
                'model': 'omi',
                'choices': [
                    {
                        'index': 0,
                        'message': {'role': 'assistant', 'content': REPLY_TEXT},
                        'finish_reason': 'stop',
                    }
                ],
                'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
            }
        ).encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # Every verb routes to the same capture -- we do not yet know which the
    # device uses, and an unhandled verb would look like a network failure.
    do_GET = _capture
    do_POST = _capture
    do_PUT = _capture
    do_PATCH = _capture
    do_DELETE = _capture

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib naming
        self._capture()

    def log_message(self, fmt: str, *args) -> None:
        """Silence the default access log; _record is the real output."""
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8788)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), CaptureHandler)
    print(f'Listening on {args.host}:{args.port} -- logging to {LOG_PATH}')
    print('Register this URL in the Even app (Add Agent), then speak a question.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
