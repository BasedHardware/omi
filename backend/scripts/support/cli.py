"""Read-only support CLI.

The credential is the support person's own Omi Firebase session, obtained by
Google sign-in in a localhost browser. It is not a GCP key and not ADMIN_KEY.
A supportData/{uid} document is still required on the server; this CLI cannot
create one.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SESSION_PATH = Path.home() / '.config' / 'omi-support' / 'session.json'
DEFAULT_BASE_URL = 'https://api.omi.me'
LOGIN_TIMEOUT_SECONDS = 300


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def public_firebase_config() -> dict[str, str]:
    override = os.environ.get('OMI_SUPPORT_FIREBASE_API_KEY', '').strip()
    values_path = repo_root() / 'config' / 'public-build-values.json'
    values: dict[str, Any] = {}
    if values_path.is_file():
        document = json.loads(values_path.read_text())
        values = document['environments']['prod']['values']
    api_key = override or str(values.get('NEXT_PUBLIC_FIREBASE_API_KEY') or '')
    if not api_key:
        raise SystemExit('Missing public Firebase web API key. Set OMI_SUPPORT_FIREBASE_API_KEY.')
    return {
        'apiKey': api_key,
        'authDomain': str(values.get('NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN') or 'based-hardware.firebaseapp.com'),
        'projectId': str(values.get('NEXT_PUBLIC_FIREBASE_PROJECT_ID') or 'based-hardware'),
    }


def load_session() -> dict[str, Any]:
    if not SESSION_PATH.is_file():
        raise SystemExit(f'Not signed in. Run: {invocation()} login')
    return json.loads(SESSION_PATH.read_text())


def save_session(session: dict[str, Any]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(session, indent=2) + '\n'
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(SESSION_PATH, flags, 0o600)
    try:
        os.write(descriptor, payload.encode())
    finally:
        os.close(descriptor)
    os.chmod(SESSION_PATH, 0o600)


def invocation() -> str:
    return 'scripts/omi-support'


def token_claims(id_token: str) -> dict[str, Any]:
    payload = id_token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    if not isinstance(claims, dict) or not claims.get('user_id') and not claims.get('sub'):
        raise SystemExit('Firebase token did not include a user id')
    return claims


def refresh_id_token(session: dict[str, Any], config: dict[str, str]) -> str:
    body = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': session['refresh_token']}).encode()
    request = urllib.request.Request(
        f"https://securetoken.googleapis.com/v1/token?key={config['apiKey']}",
        data=body,
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            refreshed = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        exc.read()
        raise SystemExit(f'Sign-in expired. Run {invocation()} login again. ({exc.code})') from None
    if not isinstance(refreshed, dict) or not refreshed.get('id_token'):
        raise SystemExit('Firebase token refresh returned no id token')
    if refreshed.get('refresh_token'):
        session['refresh_token'] = refreshed['refresh_token']
        save_session(session)
    return str(refreshed['id_token'])


def api_get(path: str, params: dict[str, str], id_token: str, base_url: str) -> tuple[int, dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f'{base_url.rstrip("/")}{path}?{query}',
        headers={'Authorization': f'Bearer {id_token}', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {'detail': 'Support API request failed'}
        return exc.code, payload if isinstance(payload, dict) else {'detail': 'Support API request failed'}


def explain_denial(status: int, payload: dict[str, Any], claims: dict[str, Any]) -> None:
    uid = str(claims.get('user_id') or claims.get('sub'))
    email = claims.get('email') or '(no email on token)'
    if status == 401:
        raise SystemExit(f'Session rejected. Run {invocation()} login again.')
    if status == 403:
        raise SystemExit(
            f'Signed in as {email} uid {uid}, but supportData/{uid} is missing, expired, or not role support:read.\n'
            'An operator with Firestore write creates that document. This CLI cannot grant it.'
        )
    if status == 404:
        raise SystemExit(str(payload.get('detail') or 'Account not found'))
    detail = payload.get('detail') or 'Support request failed'
    raise SystemExit(f'{status}: {detail}')


def print_lookup(payload: dict[str, Any]) -> None:
    fields = (
        'email',
        'uid',
        'plan',
        'last_active_at',
        'last_active_platform',
        'transcription_seconds_used',
        'transcription_seconds_limit',
        'transcription_seconds_remaining',
        'fair_use_stage',
    )
    for field in fields:
        print(f'{field}: {payload.get(field)}')


def print_trace(payload: dict[str, Any]) -> None:
    print(f"email: {payload.get('email')}")
    print(f"uid: {payload.get('uid')}")
    print(f"from: {payload.get('from')}")
    print(f"to: {payload.get('to')}")
    print(f"truncated: {payload.get('truncated')}")
    rows = payload.get('rows') or []
    if not rows:
        print('rows: none in this window. A missing row does not prove where the recording was lost.')
        return
    for row in rows:
        print(
            ' '.join(
                [
                    f"id={row.get('conversation_id')}",
                    f"started={row.get('started_at')}",
                    f"status={row.get('status')}",
                    f"captured={row.get('captured')}",
                    f"synced={row.get('synced')}",
                    f"processed={row.get('processed')}",
                    f"saved={row.get('saved')}",
                    f"discarded={row.get('discarded')}",
                    f"deleted={row.get('deleted')}",
                    f"failed={row.get('failed')}",
                    f"stage={row.get('failure_stage')}",
                    f"audio={row.get('audio_present')}",
                    f"transcript={row.get('has_transcript')}",
                ]
            )
        )


def command_login(args: argparse.Namespace) -> None:
    config = public_firebase_config()
    state = secrets.token_urlsafe(32)
    received: dict[str, Any] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            if urllib.parse.urlparse(self.path).path != '/':
                self.send_error(404)
                return
            page = login_page(config, state).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self) -> None:  # noqa: N802
            if urllib.parse.urlparse(self.path).path != '/callback':
                self.send_error(404)
                return
            length = int(self.headers.get('Content-Length') or '0')
            if length <= 0 or length > 20000:
                self.send_error(400)
                return
            try:
                body = json.loads(self.rfile.read(length).decode())
            except json.JSONDecodeError:
                self.send_error(400)
                return
            if not isinstance(body, dict) or body.get('state') != state or not body.get('refresh_token'):
                self.send_error(403)
                return
            received['refresh_token'] = body['refresh_token']
            self.send_response(204)
            self.end_headers()
            done.set()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{port}/'
    print(f'Opening {url}')
    print('Sign in with the support person\'s Omi account, not the customer\'s.')
    webbrowser.open(url)
    if not done.wait(LOGIN_TIMEOUT_SECONDS):
        server.shutdown()
        raise SystemExit('Login timed out before Google sign-in completed.')
    server.shutdown()
    save_session(
        {
            'refresh_token': received['refresh_token'],
            'api_base': args.base_url,
            'project_id': config['projectId'],
        }
    )
    print(f'Saved session to {SESSION_PATH}')
    print(f'Next: {invocation()} whoami')


def login_page(config: dict[str, str], state: str) -> str:
    encoded = json.dumps(
        {'apiKey': config['apiKey'], 'authDomain': config['authDomain'], 'projectId': config['projectId']}
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Omi support sign-in</title>
  <script src="https://www.gstatic.com/firebasejs/9.6.1/firebase-app-compat.js"></script>
  <script src="https://www.gstatic.com/firebasejs/9.6.1/firebase-auth-compat.js"></script>
</head>
<body>
  <p>Sign in with the support person's Omi Google account. Do not use the customer's account.</p>
  <button id="signin" type="button">Sign in with Google</button>
  <p id="status"></p>
  <script>
    const firebaseConfig = {encoded};
    const state = {json.dumps(state)};
    firebase.initializeApp(firebaseConfig);
    const status = document.getElementById('status');
    async function finish(result) {{
      if (!result || !result.user) return;
      const refreshToken = result.user.refreshToken;
      const response = await fetch('/callback', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{state, refresh_token: refreshToken}})
      }});
      if (!response.ok) {{
        status.textContent = 'The local CLI rejected the sign-in. Close this window and try again.';
        return;
      }}
      status.textContent = 'Signed in. You can close this window.';
    }}
    document.getElementById('signin').addEventListener('click', async () => {{
      status.textContent = 'Waiting for Google…';
      try {{
        const provider = new firebase.auth.GoogleAuthProvider();
        provider.setCustomParameters({{prompt: 'select_account'}});
        await finish(await firebase.auth().signInWithPopup(provider));
      }} catch (error) {{
        status.textContent = error && error.message ? error.message : 'Sign-in failed';
      }}
    }});
  </script>
</body>
</html>
"""


def signed_in_token(args: argparse.Namespace) -> tuple[str, dict[str, Any], dict[str, str]]:
    session = load_session()
    config = public_firebase_config()
    id_token = refresh_id_token(session, config)
    return id_token, token_claims(id_token), config


def command_whoami(args: argparse.Namespace) -> None:
    _, claims, _ = signed_in_token(args)
    print(f"uid: {claims.get('user_id') or claims.get('sub')}")
    print(f"email: {claims.get('email')}")
    print(f"api: {args.base_url}")


def command_logout(_: argparse.Namespace) -> None:
    if SESSION_PATH.is_file():
        SESSION_PATH.unlink()
    print('Signed out.')


def command_lookup(args: argparse.Namespace) -> None:
    id_token, claims, _ = signed_in_token(args)
    status, payload = api_get('/v1/support/lookup', {'email': args.email}, id_token, args.base_url)
    if status != 200:
        explain_denial(status, payload, claims)
    print_lookup(payload)


def command_trace(args: argparse.Namespace) -> None:
    id_token, claims, _ = signed_in_token(args)
    status, payload = api_get(
        '/v1/support/trace',
        {'email': args.email, 'from': args.window_from, 'to': args.window_to},
        id_token,
        args.base_url,
    )
    if status != 200:
        explain_denial(status, payload, claims)
    print_trace(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='omi-support', description='Read-only Omi support lookup. No GCP credentials.'
    )
    parser.add_argument('--base-url', default=os.environ.get('OMI_SUPPORT_API_BASE', DEFAULT_BASE_URL))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('login', help='Sign in with the support person\'s Omi Google account')
    sub.add_parser('whoami', help='Print the signed-in Firebase uid')
    sub.add_parser('logout', help='Delete the local session')
    lookup = sub.add_parser('lookup', help='Account summary for one exact email')
    lookup.add_argument('email')
    trace = sub.add_parser('trace', help='Recording lifecycle for one email and a time window')
    trace.add_argument('email')
    trace.add_argument('--from', dest='window_from', required=True)
    trace.add_argument('--to', dest='window_to', required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    {
        'login': command_login,
        'whoami': command_whoami,
        'logout': command_logout,
        'lookup': command_lookup,
        'trace': command_trace,
    }[args.command](args)


if __name__ == '__main__':
    main()
