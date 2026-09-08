#!/usr/bin/env python3
"""Mint an ephemeral Firebase ID token for a release probe.

The script reads the existing Firebase web API key from Secret Manager and
creates a five-minute custom token for the fixed non-human release-probe UID.
It can either sign remotely with the authenticated deploy identity or sign
locally with an explicit mode-0600 service-account credential. The local path
rejects a signer from a different Firebase project before using its key. The
caller separately names the expected Firebase auth project, and the exchanged
ID token must match that audience and issuer.

The script never prints a credential, request body, response body, or upstream
error body. The ID token is written only to a mode-0600 file owned by the
current runner process; platforms that cannot enforce that mode fail before
creating the output file.
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
import tempfile
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
MAX_SIGNER_CREDENTIAL_BYTES = 65536
FIREBASE_PROJECT_ID_PATTERN = re.compile(r'^[a-z][a-z0-9-]{4,62}$')


class ProbeTokenError(RuntimeError):
    def __init__(self, stage: str, error_class: str = 'operation_failed'):
        super().__init__(stage)
        self.stage = stage
        self.error_class = error_class


def _run_gcloud(args: Sequence[str], *, stage: str) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ProbeTokenError(stage, 'tool_unavailable') from error
    except subprocess.CalledProcessError as error:
        raise ProbeTokenError(stage, 'command_failed') from error
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


def _validated_service_account(account: str, stage: str) -> str:
    if '\n' in account or '@' not in account or not account.endswith('.gserviceaccount.com') or len(account) > 320:
        raise ProbeTokenError(stage)
    return account


def _active_service_account() -> str:
    account = _run_gcloud(
        ['gcloud', 'auth', 'list', '--filter=status:ACTIVE', '--format=value(account)'],
        stage='service_account',
    )
    return _validated_service_account(account, 'service_account')


def _access_token() -> str:
    try:
        token = _run_gcloud(['gcloud', 'auth', 'application-default', 'print-access-token'], stage='access_token')
    except ProbeTokenError:
        token = _run_gcloud(['gcloud', 'auth', 'print-access-token'], stage='access_token')
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise ProbeTokenError('access_token')
    return token


def _http_error_class(status: int) -> str:
    if status == 401:
        return 'authentication_failed'
    if status == 403:
        return 'permission_denied'
    if status == 404:
        return 'resource_not_found'
    if status == 429:
        return 'rate_limited'
    if 500 <= status <= 599:
        return 'upstream_unavailable'
    return 'upstream_rejected'


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
                raise ProbeTokenError(stage, _http_error_class(int(response.status)))
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        raise ProbeTokenError(stage, _http_error_class(int(error.code))) from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise ProbeTokenError(stage, 'transport_error') from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeTokenError(stage, 'invalid_response') from error
    if not isinstance(payload, dict):
        raise ProbeTokenError(stage, 'invalid_response')
    return payload


def _custom_token_claims(service_account: str) -> dict[str, Any]:
    now = int(time.time())
    return {
        'iss': service_account,
        'sub': service_account,
        'aud': CUSTOM_TOKEN_AUDIENCE,
        'iat': now,
        'exp': now + CUSTOM_TOKEN_TTL_SECONDS,
        'uid': PROBE_UID,
        'claims': {'release_probe': True},
    }


def _signed_custom_token(service_account: str, access_token: str) -> str:
    claims = _custom_token_claims(service_account)
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
        raise ProbeTokenError('custom_token_signing', 'invalid_response')
    return signed_jwt


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _read_signer_credentials(path: Path, firebase_project: str) -> tuple[str, str, str]:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = -1
    payload: dict[str, Any] = {}
    try:
        descriptor = os.open(path, flags)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or stat.S_IMODE(file_stat.st_mode) & 0o077:
            raise ProbeTokenError('signer_credentials', 'unsafe_permissions')
        raw = os.read(descriptor, MAX_SIGNER_CREDENTIAL_BYTES + 1)
        if not raw or len(raw) > MAX_SIGNER_CREDENTIAL_BYTES:
            raise ProbeTokenError('signer_credentials', 'invalid_credentials')
        try:
            payload = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProbeTokenError('signer_credentials', 'invalid_credentials') from error
        if not isinstance(payload, dict):
            raise ProbeTokenError('signer_credentials', 'invalid_credentials')
        service_account = payload.get('client_email')
        signer_project = payload.get('project_id')
        private_key_id = payload.get('private_key_id')
        private_key = payload.get('private_key')
        expected_suffix = f'@{firebase_project}.iam.gserviceaccount.com'
        if signer_project != firebase_project:
            raise ProbeTokenError('signer_credentials', 'project_mismatch')
        if (
            payload.get('type') != 'service_account'
            or not isinstance(service_account, str)
            or not service_account.endswith(expected_suffix)
            or not isinstance(private_key_id, str)
            or not private_key_id
            or not isinstance(private_key, str)
            or not private_key.startswith('-----BEGIN PRIVATE KEY-----')
        ):
            raise ProbeTokenError('signer_credentials', 'invalid_credentials')
        return service_account, private_key_id, private_key
    except OSError as error:
        raise ProbeTokenError('signer_credentials', 'credential_unavailable') from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        payload.clear()


def _signed_custom_token_locally(credentials_path: Path, firebase_project: str) -> str:
    service_account = ''
    private_key_id = ''
    private_key = ''
    key_path = ''
    descriptor = -1
    claims: dict[str, Any] = {}
    header: dict[str, str] = {}
    try:
        service_account, private_key_id, private_key = _read_signer_credentials(credentials_path, firebase_project)
        claims = _custom_token_claims(service_account)
        header = {'alg': 'RS256', 'kid': private_key_id, 'typ': 'JWT'}
        signing_input = (
            f'{_base64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))}.'
            f'{_base64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))}'
        )
        fchmod = getattr(os, 'fchmod', None)
        if not callable(fchmod):
            raise ProbeTokenError('custom_token_signing', 'credential_unavailable')
        try:
            descriptor, key_path = tempfile.mkstemp(
                prefix='omi-firebase-probe-signer-',
                dir=os.environ.get('RUNNER_TEMP'),
            )
            try:
                fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    descriptor = -1
                    handle.write(private_key)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        except OSError as error:
            raise ProbeTokenError('custom_token_signing', 'credential_unavailable') from error
        try:
            completed = subprocess.run(
                ['openssl', 'dgst', '-sha256', '-sign', key_path],
                input=signing_input.encode('ascii'),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise ProbeTokenError('custom_token_signing', 'tool_unavailable') from error
        except subprocess.CalledProcessError as error:
            raise ProbeTokenError('custom_token_signing', 'local_signing_failed') from error
        signed_jwt = f'{signing_input}.{_base64url(completed.stdout)}'
        if len(signed_jwt) > MAX_TOKEN_CHARS:
            raise ProbeTokenError('custom_token_signing', 'invalid_response')
        return signed_jwt
    finally:
        if key_path:
            try:
                os.unlink(key_path)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise ProbeTokenError('custom_token_signing', 'credential_cleanup_failed') from error
        service_account = ''
        private_key_id = ''
        private_key = ''
        claims.clear()
        header.clear()


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
        raise ProbeTokenError('firebase_token_exchange', 'invalid_response')
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


def mint_probe_token(
    secret_project: str,
    firebase_project: str,
    *,
    signer_credentials_file: Path | None = None,
    signer_service_account: str | None = None,
) -> str:
    firebase_api_key = ''
    service_account = ''
    access_token = ''
    custom_token = ''
    id_token = ''
    try:
        firebase_api_key = _access_secret(secret_project)
        if signer_credentials_file is None:
            # Identity Toolkit only accepts a custom token whose signer is
            # authorized for the Firebase project. The development backend
            # authenticates against production Firebase, so a development
            # deploy identity cannot sign for it -- that is why the manual
            # development lane failed at custom_token_signing. Naming the
            # Firebase project's own signer and impersonating it (requires
            # roles/iam.serviceAccountTokenCreator on that account) resolves
            # the mismatch without moving the runtime off production auth.
            service_account = (
                _validated_service_account(signer_service_account, 'signer_service_account')
                if signer_service_account
                else _active_service_account()
            )
            access_token = _access_token()
            custom_token = _signed_custom_token(service_account, access_token)
        else:
            custom_token = _signed_custom_token_locally(signer_credentials_file, firebase_project)
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
    fchmod = getattr(os, 'fchmod', None)
    if not callable(fchmod):
        raise ProbeTokenError('token_output')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ProbeTokenError('token_output')
            fchmod(descriptor, 0o600)
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
    parser.add_argument('--signer-credentials-file', type=Path)
    parser.add_argument(
        '--signer-service-account',
        help=(
            'Service account to sign the custom token as, via IAM signJwt. '
            'Use when the Firebase auth project differs from the deploy identity project.'
        ),
    )
    parser.add_argument('--token-output', required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    token = ''
    try:
        if not FIREBASE_PROJECT_ID_PATTERN.fullmatch(args.firebase_project):
            raise ProbeTokenError('firebase_project')
        if args.signer_credentials_file is not None and args.signer_service_account:
            raise ProbeTokenError('signer_service_account')
        token = mint_probe_token(
            args.secret_project,
            args.firebase_project,
            signer_credentials_file=args.signer_credentials_file,
            signer_service_account=args.signer_service_account,
        )
        write_token(args.token_output, token)
    except ProbeTokenError as error:
        print(
            json.dumps(
                {
                    'suite': 'omi_firebase_release_probe_token',
                    'stage': error.stage,
                    'error_class': error.error_class,
                    'status': 'FAIL',
                }
            )
        )
        return 1
    finally:
        token = ''
    print(json.dumps({'suite': 'omi_firebase_release_probe_token', 'status': 'PASS'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
