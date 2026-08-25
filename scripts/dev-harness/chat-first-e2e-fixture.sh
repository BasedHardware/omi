#!/usr/bin/env bash
set -euo pipefail

# Drive the Chat-first E2E fixture through a real Firebase Auth emulator token.
# This is intentionally a local-harness command, never an authentication bypass.
# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
cd "$(dirname "$0")/../.."

ACTION="${1:?usage: chat-first-e2e-fixture.sh <prepare|snapshot|advance> <fixture-case> [seconds]}"
FIXTURE_CASE="${2:?usage: chat-first-e2e-fixture.sh <prepare|snapshot|advance> <fixture-case> [seconds]}"
SECONDS="${3:-86400}"

PYTHON_BIN="${PYTHON:-backend/venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" - "$ACTION" "$FIXTURE_CASE" "$SECONDS" <<'PY'
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from dev_harness import config, safety
from dev_harness.cli import _current_scenario_manifest, _scenario_users_from_seed_manifest

action, fixture_case, raw_seconds = sys.argv[1:]
valid_actions = {'prepare', 'snapshot', 'advance'}
valid_cases = {'enabled', 'question', 'out_of_cohort', 'unreachable_control', 'cold_start'}
if action not in valid_actions or fixture_case not in valid_cases:
    raise SystemExit(
        'usage: chat-first-e2e-fixture.sh <prepare|snapshot|advance> '
        '<enabled|question|out_of_cohort|unreachable_control|cold_start> [seconds]'
    )
if os.environ.get('OMI_ENV_STAGE') not in {'local', 'offline'}:
    raise SystemExit('Chat-first E2E fixture is local/offline only')

repo = Path.cwd()
cfg = config.load_config(repo, create_layout=False)
if not cfg.layout.sentinel_path.is_file():
    raise SystemExit('Local harness sentinel is missing; run PROVIDER_MODE=offline make dev-up first')
safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=repo, instance=cfg.instance)
if not safety.is_loopback_host(urlparse(cfg.backend_url).netloc):
    raise SystemExit(f'Refusing non-loopback backend URL: {cfg.backend_url}')

scenario = _current_scenario_manifest(cfg)
seeded_users = _scenario_users_from_seed_manifest(cfg)
if not scenario or not seeded_users:
    raise SystemExit('No live memory scenario is seeded; run make seed-memory-scenario SCENARIO=happy_path')

principal = (
    'omi-local-emulator-chat-first-disabled-v1'
    if fixture_case == 'out_of_cohort'
    else 'omi-local-emulator-chat-first-enabled-v1'
)
if principal not in seeded_users:
    raise SystemExit(f'Fixture principal {principal!r} is absent from the seeded scenario')

auth_manifest_path = cfg.layout.state_root / 'manifests' / 'canonical-auth-uids.json'
try:
    auth_manifest = json.loads(auth_manifest_path.read_text(encoding='utf-8'))
    expected_local_id = auth_manifest['users'][principal]
except (OSError, KeyError, TypeError, json.JSONDecodeError):
    raise SystemExit('Live Auth UID manifest is missing; re-run make seed-memory-scenario SCENARIO=happy_path') from None
if not isinstance(expected_local_id, str) or not expected_local_id:
    raise SystemExit('Auth UID manifest contains no fixture Auth emulator identity')

seed_manifests = sorted((cfg.layout.state_root / 'manifests').glob('memory-scenario-*-seed.json'))
if not seed_manifests:
    raise SystemExit('Seed manifest is missing; re-run make seed-memory-scenario SCENARIO=happy_path')
seed_manifest = json.loads(max(seed_manifests, key=lambda path: path.stat().st_mtime).read_text(encoding='utf-8'))
credentials = next(
    (
        op.get('payload')
        for op in seed_manifest.get('operations', [])
        if isinstance(op, dict)
        and op.get('kind') == 'auth'
        and op.get('action') == 'upsert'
        and isinstance(op.get('payload'), dict)
        and op['payload'].get('localId') == principal
    ),
    None,
)
if not isinstance(credentials, dict):
    raise SystemExit(f'Seed manifest has no credentials for {principal!r}')
email, password = credentials.get('email'), credentials.get('password')
if not isinstance(email, str) or not isinstance(password, str):
    raise SystemExit(f'Seed manifest credentials for {principal!r} are invalid')


def request_json(method: str, url: str, payload: dict[str, object] | None = None, token: str | None = None):
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = {'Content-Type': 'application/json'} if body else {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode('utf-8'))


auth_status, auth_body = request_json(
    'POST',
    f'http://{cfg.auth_host}/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=local-dev-harness',
    {'email': email, 'password': password, 'returnSecureToken': True},
)
if auth_status >= 400 or not isinstance(auth_body, dict):
    raise SystemExit(f'Firebase Auth emulator sign-in failed: HTTP {auth_status}')
if auth_body.get('localId') != expected_local_id:
    raise SystemExit('Firebase Auth emulator localId does not match the harness manifest')
token = auth_body.get('idToken')
if not isinstance(token, str) or not token:
    raise SystemExit('Firebase Auth emulator returned no ID token')

if action == 'prepare':
    method, endpoint, payload = 'POST', '/prepare', {'fixture_case': fixture_case}
elif action == 'snapshot':
    method, endpoint, payload = 'GET', '/snapshot', None
else:
    try:
        seconds = int(raw_seconds)
    except ValueError:
        raise SystemExit('advance seconds must be an integer') from None
    if seconds <= 0:
        raise SystemExit('advance seconds must be positive')
    method, endpoint, payload = 'POST', '/advance-clock', {'seconds': seconds}

status, response = request_json(method, f'{cfg.backend_url}/v1/dev-harness/chat-first{endpoint}', payload, token)
if status >= 400:
    raise SystemExit(f'Chat-first fixture {action} failed: HTTP {status}')
if not isinstance(response, dict):
    raise SystemExit('Chat-first fixture returned an invalid response')

# The API intentionally returns only bounded state/counters, never fixture IDs,
# titles, or raw conversation content. Keep command output equally constrained.
print(json.dumps(response, sort_keys=True))
PY
