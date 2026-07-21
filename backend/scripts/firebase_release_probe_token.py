#!/usr/bin/env python3
"""Mint an ephemeral Firebase ID token for the transcription release probe.

The script uses the already authenticated deploy identity. It reads the existing
Firebase web API key from Secret Manager, remotely signs a five-minute Firebase
custom token for the fixed non-human release-probe UID, then exchanges it for a
Firebase ID token. The caller separately names the expected Firebase auth
project; the script rejects a mismatched token audience or issuer. It never
prints a credential, request body, response body, or upstream error body. The
ID token is written only to a mode-0600 file owned by the current runner
process.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Sequence

FIREBASE_API_KEY_SECRET = 'FIREBASE_API_KEY'
PROBE_UID = 'omi-release-probe'
CUSTOM_TOKEN_AUDIENCE = 'https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit'
IAM_CREDENTIALS_URL = 'https://iamcredentials.googleapis.com/v1'
IDENTITY_TOOLKIT_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken'
CUSTOM_TOKEN_TTL_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 30
MAX_TOKEN_CHARS = 8192
FIREBASE_PROJECT_ID_PATTERN = re.compile(r'^[a-z][a-z0-9-]{4,62}$')


class ProbeTokenError(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


def _run_gcloud(args: Sequence[str], *, stage: str) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProbeTokenError(stage) from error
    return completed.stdout.strip()


def _access_secret(project: str) -> str:
    value = _run_gcloud(
        [
            'gcloud',
            'secrets',
            'versions',
            'access',
            'latest',
            f'--secret={FIREBASE_API_KEY_SECRET}',
            f'--project={project}',
        ],
        stage='secret_access',
    )
    if not value:
        raise ProbeTokenError('secret_access')
    return value


def _active_service_account() -> str:
    account = _run_gcloud(
        ['gcloud', 'auth', 'list', '--filter=status:ACTIVE', '--format=value(account)'],
        stage='service_account',
    )
    if '\n' in account or '@' not in account or not account.endswith('.gserviceaccount.com') or len(account) > 320:
        raise ProbeTokenError('service_account')
    return account


def _access_token() -> str:
    try:
        token = _run_gcloud(['gcloud', 'auth', 'application-default', 'print-access-token'], stage='access_token')
    except ProbeTokenError:
        token = _run_gcloud(['gcloud', 'auth', 'print-access-token'], stage='access_token')
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise ProbeTokenError('access_token')
    return token


def _request_json(
    url: str,
    *,
    body: dict[str, Any],
    access_token: str | None,
    stage: str,
) -> dict[str, Any]:
    headers = {'Content-Type': 'application/json'}
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(',', ':')).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if int(response.status) != 200:
                raise ProbeTokenError(stage)
            payload = json.loads(response.read().decode('utf-8'))
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ProbeTokenError(stage) from error
    if not isinstance(payload, dict):
        raise ProbeTokenError(stage)
    return payload


def _signed_custom_token(service_account: str, access_token: str) -> str:
    now = int(time.time())
    claims = {
        'iss': service_account,
        'sub': service_account,
        'aud': CUSTOM_TOKEN_AUDIENCE,
        'iat': now,
        'exp': now + CUSTOM_TOKEN_TTL_SECONDS,
        'uid': PROBE_UID,
        # Firebase custom-token developer claims are top-level JWT payload
        # entries, not nested under a generic "claims" key.
        'release_probe': True,
    }
    quoted_account = urllib.parse.quote(service_account, safe='')
    payload = _request_json(
        f'{IAM_CREDENTIALS_URL}/projects/-/serviceAccounts/{quoted_account}:signJwt',
        body={'payload': json.dumps(claims, separators=(',', ':'), sort_keys=True)},
        access_token=access_token,
        stage='custom_token_signing',
    )
    signed_jwt = payload.get('signedJwt')
    payload.clear()
    if not isinstance(signed_jwt, str) or not signed_jwt or len(signed_jwt) > MAX_TOKEN_CHARS:
        raise ProbeTokenError('custom_token_signing')
    return signed_jwt


def _exchange_custom_token(custom_token: str, firebase_api_key: str) -> str:
    url = f'{IDENTITY_TOOLKIT_URL}?key={urllib.parse.quote(firebase_api_key, safe="")}'
    payload = _request_json(
        url,
        body={'token': custom_token, 'returnSecureToken': True},
        access_token=None,
        stage='firebase_token_exchange',
    )
    id_token = payload.get('idToken')
    payload.clear()
    if not isinstance(id_token, str) or not id_token or len(id_token) > MAX_TOKEN_CHARS:
        raise ProbeTokenError('firebase_token_exchange')
    return id_token


def _validate_firebase_id_token_claims(id_token: str, firebase_project: str) -> None:
    """Assert the exchanged token is for the backend's Firebase auth project.

    This is intentionally an unverified claim check: the target backend still
    verifies the token signature before authorizing the probe. Its purpose here
    is to fail before a deployment probe when the Secret Manager project or
    deploy identity is accidentally paired with a Firebase API key for a
    different auth project.
    """
    token_parts = id_token.split('.')
    if len(token_parts) != 3 or not token_parts[1] or len(token_parts[1]) > MAX_TOKEN_CHARS:
        raise ProbeTokenError('firebase_token_claims')
    try:
        padded_claims = token_parts[1] + '=' * (-len(token_parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded_claims.encode('ascii')).decode('utf-8'))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise ProbeTokenError('firebase_token_claims') from None
    if not isinstance(claims, dict):
        raise ProbeTokenError('firebase_token_claims')
    try:
        valid = (
            claims.get('aud') == firebase_project
            and claims.get('iss') == f'https://securetoken.google.com/{firebase_project}'
            and claims.get('sub') == PROBE_UID
        )
    finally:
        claims.clear()
    if not valid:
        raise ProbeTokenError('firebase_token_claims')


def mint_probe_token(secret_project: str, firebase_project: str) -> str:
    firebase_api_key = ''
    service_account = ''
    access_token = ''
    custom_token = ''
    id_token = ''
    try:
        firebase_api_key = _access_secret(secret_project)
        service_account = _active_service_account()
        access_token = _access_token()
        custom_token = _signed_custom_token(service_account, access_token)
        id_token = _exchange_custom_token(custom_token, firebase_api_key)
        _validate_firebase_id_token_claims(id_token, firebase_project)
        return id_token
    finally:
        firebase_api_key = ''
        service_account = ''
        access_token = ''
        custom_token = ''
        id_token = ''


def write_token(path: Path, token: str) -> None:
    if not path.parent.is_dir() or not token or len(token) > MAX_TOKEN_CHARS:
        raise ProbeTokenError('token_output')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ProbeTokenError('token_output')
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                descriptor = -1
                handle.write(token)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except (OSError, ProbeTokenError) as error:
        if isinstance(error, ProbeTokenError):
            raise
        raise ProbeTokenError('token_output') from error


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secret-project', required=True)
    parser.add_argument('--firebase-project', required=True)
    parser.add_argument('--token-output', required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    token = ''
    try:
        if not FIREBASE_PROJECT_ID_PATTERN.fullmatch(args.firebase_project):
            raise ProbeTokenError('firebase_project')
        token = mint_probe_token(args.secret_project, args.firebase_project)
        write_token(args.token_output, token)
    except ProbeTokenError as error:
        print(json.dumps({'suite': 'omi_firebase_release_probe_token', 'stage': error.stage, 'status': 'FAIL'}))
        return 1
    finally:
        token = ''
    print(json.dumps({'suite': 'omi_firebase_release_probe_token', 'status': 'PASS'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
